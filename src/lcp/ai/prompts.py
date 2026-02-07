"""Prompt templates for AI documentation generation."""

from __future__ import annotations


def build_system_prompt(
    docstring_style: str = "google",
    description: str | None = None,
) -> str:
    """Build the system prompt for the documentation agent.

    Args:
        docstring_style: Style of docstring to generate.
        description: Optional user-provided description to guide generation.

    Returns:
        The system prompt string.
    """
    parts = [
        "You are a Python documentation expert. Your task is to generate "
        "high-quality docstrings for Python symbols that lack documentation.",
        "",
        "Rules:",
        f"- Use {docstring_style} style docstrings.",
        "- Return ONLY the docstring text, without triple quotes.",
        "- Do NOT include any explanation or commentary outside the docstring.",
        "- Write a concise summary line first.",
        "- Add an Args section for functions/methods with parameters.",
        "- Add a Returns section if the function/method returns a value.",
        "- Add a Raises section if the function/method raises exceptions.",
        "- For classes, describe the purpose and key attributes.",
        "- For modules, describe the module's purpose.",
        "- Keep descriptions concise but informative.",
        "- Do NOT invent behavior that is not evident from the source code.",
    ]

    if description:
        parts.extend([
            "",
            "Additional context from the user:",
            description,
        ])

    return "\n".join(parts)


def build_user_prompt(
    kind: str,
    module: str,
    entity: str,
    source_context: str,
) -> str:
    """Build the user prompt for a specific symbol.

    Args:
        kind: Symbol kind (module, class, function, method, attribute).
        module: Module path.
        entity: Entity name.
        source_context: Source code context for the symbol.

    Returns:
        The user prompt string.
    """
    parts = [
        f"Generate a docstring for the following {kind}.",
        "",
        f"Module: {module}",
        f"Entity: {entity}",
        "",
        "Source code:",
        "```python",
        source_context,
        "```",
        "",
        "Return ONLY the docstring text, without triple quotes.",
    ]

    return "\n".join(parts)
