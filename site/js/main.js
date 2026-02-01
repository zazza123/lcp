/**
 * LCP Website - Main JavaScript
 */

// Load components and initialize
document.addEventListener('DOMContentLoaded', async () => {
  await loadComponents();
  initHeader();
  initAnimations();
  initMobileMenu();
  initCopyButtons();
  initJsonViewer();
  highlightCurrentPage();
});

/**
 * Load header and footer components
 */
async function loadComponents() {
  const headerPlaceholder = document.getElementById('header-placeholder');
  const footerPlaceholder = document.getElementById('footer-placeholder');

  const loadComponent = async (placeholder, path) => {
    if (!placeholder) return;
    try {
      const response = await fetch(path);
      if (response.ok) {
        placeholder.outerHTML = await response.text();
      }
    } catch (e) {
      console.warn(`Failed to load component: ${path}`);
    }
  };

  await Promise.all([
    loadComponent(headerPlaceholder, 'components/header.html'),
    loadComponent(footerPlaceholder, 'components/footer.html'),
  ]);
}

/**
 * Highlight current page in navigation
 */
function highlightCurrentPage() {
  const currentPage = window.location.pathname.split('/').pop().replace('.html', '') || 'index';
  const navLinks = document.querySelectorAll('.nav__link[data-page]');
  
  navLinks.forEach(link => {
    if (link.dataset.page === currentPage) {
      link.classList.add('nav__link--active');
    }
  });
}

/**
 * Header scroll behavior
 */
function initHeader() {
  const header = document.querySelector('.header');
  if (!header) return;

  const handleScroll = () => {
    if (window.scrollY > 20) {
      header.classList.add('header--scrolled');
    } else {
      header.classList.remove('header--scrolled');
    }
  };

  window.addEventListener('scroll', handleScroll, { passive: true });
  handleScroll();
}

/**
 * Scroll animations (AOS-like)
 */
function initAnimations() {
  const elements = document.querySelectorAll('[data-animate]');
  if (!elements.length) return;

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    },
    {
      threshold: 0.1,
      rootMargin: '0px 0px -50px 0px',
    }
  );

  elements.forEach((el) => observer.observe(el));
}

/**
 * Mobile menu toggle
 */
function initMobileMenu() {
  const toggle = document.querySelector('.mobile-toggle');
  const nav = document.querySelector('.header__nav');
  if (!toggle || !nav) return;

  toggle.addEventListener('click', () => {
    nav.classList.toggle('header__nav--open');
    toggle.setAttribute(
      'aria-expanded',
      nav.classList.contains('header__nav--open')
    );
  });

  // Close on link click
  nav.querySelectorAll('.nav__link').forEach((link) => {
    link.addEventListener('click', () => {
      nav.classList.remove('header__nav--open');
      toggle.setAttribute('aria-expanded', 'false');
    });
  });
}

/**
 * Copy to clipboard buttons
 */
function initCopyButtons() {
  document.querySelectorAll('.code-block__copy').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const codeBlock = btn.closest('.code-block');
      const code = codeBlock?.querySelector('code');
      if (!code) return;

      try {
        await navigator.clipboard.writeText(code.textContent || '');
        const originalText = btn.innerHTML;
        btn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20,6 9,17 4,12"></polyline>
          </svg>
          Copied!
        `;
        btn.style.color = 'var(--color-success)';

        setTimeout(() => {
          btn.innerHTML = originalText;
          btn.style.color = '';
        }, 2000);
      } catch (err) {
        console.error('Copy failed:', err);
      }
    });
  });
}

/**
 * Interactive JSON Viewer
 */
function initJsonViewer() {
  const viewer = document.querySelector('.json-viewer');
  if (!viewer) return;

  const container = viewer.querySelector('.json-viewer__content');
  const copyBtn = viewer.querySelector('[data-action="copy"]');
  const expandBtn = viewer.querySelector('[data-action="expand"]');
  const collapseBtn = viewer.querySelector('[data-action="collapse"]');

  // Sample LCP document
  const lcpDocument = {
    manifest: {
      schema_version: '1.0',
      library: {
        name: 'requests',
        version: '2.31.0',
        language: 'python',
      },
      distribution: 'pypi',
      license: 'Apache-2.0',
      generation: {
        tool: 'lcp',
        version: '0.1.0',
      },
    },
    symbols: {
      'requests:': {
        kind: 'module',
        module: 'requests',
        semantics: {
          summary: 'Python HTTP for Humans.',
        },
      },
      'requests:get': {
        kind: 'function',
        module: 'requests',
        semantics: {
          summary: 'Sends a GET request.',
          description:
            'Returns a Response object with the server response.',
          examples: [
            {
              code: "requests.get('https://api.github.com')",
            },
          ],
        },
        signatures: [
          {
            params: [
              { name: 'url', type: 'string', required: true },
              { name: 'params', type: 'dict', required: false },
              { name: 'headers', type: 'dict', required: false },
              { name: 'timeout', type: 'float', required: false },
            ],
            returns: 'Response',
          },
        ],
      },
      'requests:post': {
        kind: 'function',
        module: 'requests',
        semantics: {
          summary: 'Sends a POST request.',
        },
        signatures: [
          {
            params: [
              { name: 'url', type: 'string', required: true },
              { name: 'data', type: 'dict', required: false },
              { name: 'json', type: 'dict', required: false },
            ],
            returns: 'Response',
          },
        ],
      },
      'requests:Response': {
        kind: 'class',
        module: 'requests',
        semantics: {
          summary: 'The Response object containing server response.',
        },
      },
      'requests:Response#status_code': {
        kind: 'attribute',
        module: 'requests',
        semantics: {
          summary: 'Integer Code of responded HTTP Status.',
        },
      },
      'requests:Response#json': {
        kind: 'method',
        module: 'requests',
        semantics: {
          summary: 'Returns the json-encoded content of a response.',
        },
        signatures: [
          {
            params: [],
            returns: 'dict',
          },
        ],
      },
    },
  };

  // Annotations for keys
  const annotations = {
    manifest: 'Library metadata',
    symbols: 'API definitions',
    schema_version: 'LCP spec version',
    library: 'Package info',
    kind: 'Symbol type',
    semantics: 'Documentation',
    signatures: 'Call signatures',
    params: 'Parameters',
    returns: 'Return type',
  };

  // Render JSON with interactive nodes
  function renderJson(obj, depth = 0, path = '') {
    const isArray = Array.isArray(obj);
    const entries = isArray
      ? obj.map((v, i) => [i, v])
      : Object.entries(obj);
    const openBracket = isArray ? '[' : '{';
    const closeBracket = isArray ? ']' : '}';

    if (entries.length === 0) {
      return `<span class="json-bracket">${openBracket}${closeBracket}</span>`;
    }

    const nodeId = `node-${path || 'root'}`;
    const isCollapsible = depth < 3;
    const startCollapsed = depth >= 2;

    let html = `<span class="json-node" data-node-id="${nodeId}">`;
    
    if (isCollapsible) {
      html += `<button class="json-node__toggle" data-toggle="${nodeId}" aria-label="Toggle">${
        startCollapsed ? '+' : '−'
      }</button>`;
    }
    
    html += `<span class="json-bracket">${openBracket}</span>`;
    
    if (isCollapsible && startCollapsed) {
      const preview = isArray
        ? `${entries.length} items`
        : Object.keys(obj).slice(0, 3).join(', ') +
          (Object.keys(obj).length > 3 ? '...' : '');
      html += `<span class="json-node__preview"> ${preview} </span>`;
    }
    
    html += `<div class="json-node__content${
      startCollapsed ? ' json-node__content--collapsed' : ''
    }">`;

    entries.forEach(([key, value], idx) => {
      const isLast = idx === entries.length - 1;
      const keyPath = path ? `${path}-${key}` : String(key);

      html += '<div class="json-line">';

      if (!isArray) {
        const annotation = annotations[key];
        html += `<span class="json-key">"${escapeHtml(String(key))}"</span>: `;
        if (annotation) {
          html += `<span class="json-node__annotation">${annotation}</span>`;
        }
      }

      html += renderValue(value, depth + 1, keyPath);

      if (!isLast) {
        html += ',';
      }

      html += '</div>';
    });

    html += '</div>';
    html += `<span class="json-bracket">${closeBracket}</span>`;
    html += '</span>';

    return html;
  }

  function renderValue(value, depth, path) {
    if (value === null) {
      return '<span class="json-null">null</span>';
    }

    switch (typeof value) {
      case 'string':
        return `<span class="json-string">"${escapeHtml(value)}"</span>`;
      case 'number':
        return `<span class="json-number">${value}</span>`;
      case 'boolean':
        return `<span class="json-boolean">${value}</span>`;
      case 'object':
        return renderJson(value, depth, path);
      default:
        return String(value);
    }
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Render initial JSON
  if (container) {
    container.innerHTML = `<pre><code>${renderJson(lcpDocument)}</code></pre>`;

    // Add toggle listeners
    container.addEventListener('click', (e) => {
      const toggle = e.target.closest('.json-node__toggle');
      if (!toggle) return;

      const nodeId = toggle.dataset.toggle;
      const node = container.querySelector(`[data-node-id="${nodeId}"]`);
      if (!node) return;

      const content = node.querySelector('.json-node__content');
      const preview = node.querySelector('.json-node__preview');
      const isCollapsed = content.classList.contains(
        'json-node__content--collapsed'
      );

      content.classList.toggle('json-node__content--collapsed');
      toggle.textContent = isCollapsed ? '−' : '+';

      if (preview) {
        preview.style.display = isCollapsed ? 'none' : 'inline';
      }
    });
  }

  // Copy button
  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(
          JSON.stringify(lcpDocument, null, 2)
        );
        copyBtn.innerHTML = `
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20,6 9,17 4,12"></polyline>
          </svg>
          Copied!
        `;
        setTimeout(() => {
          copyBtn.innerHTML = `
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            Copy
          `;
        }, 2000);
      } catch (err) {
        console.error('Copy failed:', err);
      }
    });
  }

  // Expand/Collapse all
  function toggleAll(expand) {
    const toggles = container.querySelectorAll('.json-node__toggle');
    toggles.forEach((toggle) => {
      const nodeId = toggle.dataset.toggle;
      const node = container.querySelector(`[data-node-id="${nodeId}"]`);
      if (!node) return;

      const content = node.querySelector('.json-node__content');
      const preview = node.querySelector('.json-node__preview');

      if (expand) {
        content.classList.remove('json-node__content--collapsed');
        toggle.textContent = '−';
        if (preview) preview.style.display = 'none';
      } else {
        content.classList.add('json-node__content--collapsed');
        toggle.textContent = '+';
        if (preview) preview.style.display = 'inline';
      }
    });
  }

  if (expandBtn) {
    expandBtn.addEventListener('click', () => toggleAll(true));
  }

  if (collapseBtn) {
    collapseBtn.addEventListener('click', () => toggleAll(false));
  }
}

/**
 * Smooth scroll for anchor links
 */
document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
  anchor.addEventListener('click', (e) => {
    const href = anchor.getAttribute('href');
    if (!href || href === '#') return;

    const target = document.querySelector(href);
    if (target) {
      e.preventDefault();
      const headerHeight =
        document.querySelector('.header')?.offsetHeight || 0;
      const targetPosition =
        target.getBoundingClientRect().top + window.scrollY - headerHeight - 20;

      window.scrollTo({
        top: targetPosition,
        behavior: 'smooth',
      });
    }
  });
});
