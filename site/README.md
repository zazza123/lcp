# LCP Website

Static marketing and documentation site for the Library Context Protocol.

## Structure

```
site/
├── index.html          # Homepage
├── docs.html           # API documentation
├── getting-started.html # Quick start guide
├── mcp.html            # MCP server configuration guide
├── why-lcp.html        # Benefits and use cases
├── components/         # Shared HTML components
│   ├── header.html     # Navigation header
│   └── footer.html     # Site footer
├── css/
│   └── styles.css      # All styles (CSS custom properties)
└── js/
    └── main.js         # Interactive functionality
```

## Local Development

Serve the site using any static file server:

```bash
# Python 3
python -m http.server 8000 --directory site

# Node.js (npx)
npx serve site

# Node.js (http-server)
npx http-server site
```

Then open http://localhost:8000 in your browser.
