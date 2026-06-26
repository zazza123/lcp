"""CLI for lcp."""

from __future__ import annotations

import sys

import click

from .coverage import generate_coverage, generate_coverage_from_scanned
from .generator import generate_lcp
from .mcp_server import run_server as run_mcp_server
from .mcp_server import run_universal_server, _DEFAULT_REGISTRY_URL
from .publish import PublishError, _DEFAULT_REGISTRY_REPO, publish_manifest
from .scanner import scan_package
from .validator import LCPValidationError


@click.group()
@click.version_option(version="0.1.0", prog_name="lcp")
def main():
    """LCP Python SDK - Generate Library Context Protocol files from Python packages."""
    pass


@main.command()
@click.argument("package")
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    help="Output file path. If not specified, prints to stdout.",
)
@click.option(
    "--include-private",
    is_flag=True,
    default=False,
    help="Include private symbols (starting with _).",
)
@click.option(
    "--no-recursive",
    is_flag=True,
    default=False,
    help="Don't scan submodules recursively.",
)
@click.option(
    "--validate/--no-validate",
    default=True,
    help="Validate output against LCP schema (default: enabled).",
)
@click.option(
    "--indent",
    type=int,
    default=2,
    help="JSON indentation (default: 2).",
)
@click.option(
    "--coverage",
    type=click.Path(),
    default=None,
    help="Also generate a documentation coverage report to this path.",
)
def scan(
    package: str,
    output: str | None,
    include_private: bool,
    no_recursive: bool,
    validate: bool,
    indent: int,
    coverage: str | None,
):
    """Scan a Python package and generate an LCP file.

    PACKAGE is the name of an installed Python package to scan.

    Examples:

        lcp scan requests -o requests.lcp.json

        lcp scan numpy --include-private

        lcp scan mypackage --no-validate
    """
    try:
        # Scan the package
        click.echo(f"Scanning package: {package}...", err=True)
        scanned = scan_package(
            package,
            include_private=include_private,
            recursive=not no_recursive,
        )

        # Generate LCP
        click.echo("Generating LCP document...", err=True)
        lcp_doc = generate_lcp(scanned)

        # Validate if requested
        if validate:
            click.echo("Validating against LCP schema...", err=True)
            try:
                from .validator import validate_or_raise

                validate_or_raise(lcp_doc)
                click.echo("Validation passed", err=True)
            except LCPValidationError as e:
                click.echo(f"Validation failed:\n{e}", err=True)
                sys.exit(1)

        # Output
        json_output = lcp_doc.to_json(indent=indent)

        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(json_output)
            click.echo(f"Written to {output}", err=True)
            click.echo(f"  {len(lcp_doc.symbols)} symbols exported", err=True)
        else:
            click.echo(json_output)

        # Generate coverage report if requested
        if coverage:
            click.echo("Generating coverage report...", err=True)
            coverage_report = generate_coverage_from_scanned(scanned)
            coverage_report.to_file(coverage)
            click.echo(f"Coverage report written to {coverage}", err=True)
            click.echo(
                f"  Coverage: {coverage_report.summary.coverage_percent:.1f}% "
                f"({coverage_report.summary.documented}/{coverage_report.summary.total_symbols} symbols)",
                err=True,
            )

    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("package")
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    help="Output file path. If not specified, prints to stdout.",
)
@click.option(
    "--format",
    type=click.Choice(["json", "markdown"]),
    default="json",
    help="Output format (default: json).",
)
@click.option(
    "--include-private",
    is_flag=True,
    default=False,
    help="Include private symbols (starting with _).",
)
@click.option(
    "--no-recursive",
    is_flag=True,
    default=False,
    help="Don't scan submodules recursively.",
)
def coverage(
    package: str,
    output: str | None,
    format: str,
    include_private: bool,
    no_recursive: bool,
):
    """Generate documentation coverage report for a Python package.

    PACKAGE is the name of an installed Python package to analyze.

    Examples:

        lcp coverage requests -o coverage.json

        lcp coverage numpy -o coverage.md --format markdown

        lcp coverage mypackage --include-private
    """
    try:
        click.echo(f"Analyzing package: {package}...", err=True)
        report = generate_coverage(
            package,
            include_private=include_private,
            recursive=not no_recursive,
        )

        # Determine output format
        if output:
            # Infer format from extension if not specified explicitly
            if format == "json" and output.endswith(".md"):
                format = "markdown"
            report.to_file(output, format=format)
            click.echo(f"Written to {output}", err=True)
        else:
            content = report.to_markdown() if format == "markdown" else report.to_json()
            click.echo(content)

        click.echo(
            f"Coverage: {report.summary.coverage_percent:.1f}% "
            f"({report.summary.documented}/{report.summary.total_symbols} symbols)",
            err=True,
        )

    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("file", type=click.Path(exists=True))
def validate_cmd(file: str):
    """Validate an LCP file against the schema.

    FILE is the path to an LCP JSON file to validate.
    """
    from .validator import validate_file

    errors = validate_file(file)

    if errors:
        click.echo(f"✗ Validation failed with {len(errors)} error(s):", err=True)
        for error in errors[:20]:
            click.echo(f"  - {error}", err=True)
        if len(errors) > 20:
            click.echo(f"  ... and {len(errors) - 20} more errors", err=True)
        sys.exit(1)
    else:
        click.echo(f"✓ {file} is valid", err=True)


# Alias for validate command
main.add_command(validate_cmd, name="validate")


@main.command()
@click.argument("manifest", type=click.Path(exists=True))
@click.option(
    "--name",
    type=str,
    default=None,
    help="Server name for MCP identification (default: lcp-{library-name}).",
)
def serve(manifest: str, name: str | None):
    """Start an MCP server for an LCP manifest.

    MANIFEST is the path to an LCP JSON file to serve.

    The server uses stdio transport and exposes tools for exploring
    and querying the library's API.

    Examples:

        lcp serve requests.lcp.json

        lcp serve numpy.lcp.json --name numpy-docs
    """
    try:
        run_mcp_server(manifest, name=name)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command("serve-all")
@click.option(
    "--cache-dir",
    type=click.Path(),
    default=None,
    help="Cache directory for LCP manifests (default: ~/.lcp/cache/).",
)
@click.option(
    "--name",
    type=str,
    default="lcp-universal",
    show_default=True,
    help="Server name for MCP identification.",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Disable reading from and writing to the local cache.",
)
@click.option(
    "--registry",
    type=str,
    default=None,
    help=(
        "Base URL of an LCP registry to use as a fallback when local scanning "
        "fails. Manifests are fetched from "
        "{registry}/manifests/{language}/{name}/{version}.lcp.json. "
        f"The official registry is: {_DEFAULT_REGISTRY_URL}"
    ),
)
@click.option(
    "--expose",
    "expose",
    multiple=True,
    help=(
        "Restrict resolve_library to these package names. "
        "Repeat the flag to allow multiple packages. "
        "When omitted, all installed packages are accessible."
    ),
)
@click.option(
    "--preload",
    "preload",
    multiple=True,
    help=(
        "Resolve these packages at startup so they are ready immediately. "
        "Repeat the flag for multiple packages."
    ),
)
def serve_all(
    cache_dir: str | None,
    name: str,
    no_cache: bool,
    registry: str | None,
    expose: tuple[str, ...],
    preload: tuple[str, ...],
):
    """Start a universal MCP server that resolves any installed Python library.

    Unlike `lcp serve`, this command requires no pre-built manifest.  AI agents
    call the `resolve_library` tool to load any pip-installed package on the fly.
    Manifests are cached under ~/.lcp/cache/ by default.

    When local scanning fails, the server can optionally fetch the manifest from
    a remote LCP registry (configured via --registry).  The resolution order is:

    \b
    1. Local cache  (~/.lcp/cache/{name}/{version}.lcp.json)
    2. Live scan    (pip-installed package)
    3. Registry     (HTTP fetch from --registry/manifests/python/{name}/{version}.lcp.json)

    Setup (one-time):

        # Claude Code
        claude mcp add lcp -- lcp serve-all

        # Cursor / Claude Desktop (.cursor/mcp.json or claude_desktop_config.json)
        # { "mcpServers": { "lcp": { "command": "lcp", "args": ["serve-all"] } } }

    Examples:

        lcp serve-all

        lcp serve-all --cache-dir /tmp/lcp-cache

        lcp serve-all --no-cache --name my-lcp

        lcp serve-all --registry https://registry.example.com

        lcp serve-all --expose requests --expose httpx

        lcp serve-all --expose fastapi --preload fastapi
    """
    try:
        run_universal_server(
            name=name,
            cache_dir=cache_dir,
            no_cache=no_cache,
            registry_url=registry,
            expose=list(expose) if expose else None,
            preload=list(preload) if preload else None,
        )
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        import sys

        sys.exit(1)


@main.command()
@click.argument("package")
@click.option(
    "--token",
    type=str,
    default=None,
    envvar=["LCP_GITHUB_TOKEN", "GITHUB_TOKEN"],
    help=(
        "GitHub personal access token with 'repo' or 'public_repo' scope. "
        "Can also be set via LCP_GITHUB_TOKEN or GITHUB_TOKEN env var."
    ),
)
@click.option(
    "--registry-repo",
    type=str,
    default=_DEFAULT_REGISTRY_REPO,
    show_default=True,
    help="Target registry repository in 'owner/name' format.",
)
@click.option(
    "--file",
    "manifest_file",
    type=click.Path(exists=True),
    default=None,
    help="Use an existing LCP JSON file instead of scanning the package.",
)
@click.option(
    "--include-private",
    is_flag=True,
    default=False,
    help="Include private symbols when scanning (starting with _).",
)
@click.option(
    "--no-recursive",
    is_flag=True,
    default=False,
    help="Don't scan submodules recursively.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Generate manifest and show what would be submitted without creating a PR.",
)
def publish(
    package: str,
    token: str | None,
    registry_repo: str,
    manifest_file: str | None,
    include_private: bool,
    no_recursive: bool,
    dry_run: bool,
):
    """Publish an LCP manifest to the registry via GitHub Pull Request.

    PACKAGE is the name of an installed Python package to publish.

    The command scans the package (or uses an existing manifest via --file),
    validates it, then opens a PR to the registry repository.

    Prerequisites:

    \b
    - A GitHub account
    - A personal access token with 'repo' or 'public_repo' scope

    The PR is created with:

    \b
    - Title: [new_manifest] Add <package> v<version> (<language>)
    - Labels: new_manifest, <language>
    - Structured body with package metadata and checklist

    Examples:

        lcp publish requests --token ghp_xxxx

        lcp publish numpy --dry-run

        lcp publish mylib --file mylib.lcp.json --token ghp_xxxx
    """
    try:
        # Step 1: Get or generate the manifest
        if manifest_file:
            click.echo(f"Loading manifest from {manifest_file}...", err=True)
            from json import load as json_load

            with open(manifest_file, encoding="utf-8") as f:
                data = json_load(f)
            from .models import LCPDocument

            lcp_doc = LCPDocument.model_validate(data)
        else:
            click.echo(f"Scanning package: {package}...", err=True)
            scanned = scan_package(
                package,
                include_private=include_private,
                recursive=not no_recursive,
            )

            click.echo("Generating LCP document...", err=True)
            lcp_doc = generate_lcp(scanned)

        # Step 2: Validate
        click.echo("Validating against LCP schema...", err=True)
        try:
            from .validator import validate_or_raise

            validate_or_raise(lcp_doc)
            click.echo("✓ Validation passed", err=True)
        except LCPValidationError as e:
            click.echo(f"✗ Validation failed:\n{e}", err=True)
            sys.exit(1)

        lib = lcp_doc.manifest.library
        manifest_path = (
            f"manifests/{lib.language}/{lib.name}/{lib.version}.lcp.json"
        )
        symbol_count = len(lcp_doc.symbols)

        click.echo(f"Package: {lib.name} v{lib.version} ({lib.language})", err=True)
        click.echo(f"Symbols: {symbol_count}", err=True)
        click.echo(f"Manifest path: {manifest_path}", err=True)

        # Step 3: Dry run or publish
        if dry_run:
            click.echo("", err=True)
            click.echo("DRY RUN: No PR will be created.", err=True)
            click.echo(
                f"  PR title: [new_manifest] Add {lib.name} "
                f"v{lib.version} ({lib.language})",
                err=True,
            )
            click.echo(
                f"  Labels: new_manifest, {lib.language}",
                err=True,
            )
            click.echo(f"  Registry: {registry_repo}", err=True)
            return

        if not token:
            click.echo(
                "Error: GitHub token is required. "
                "Use --token or set LCP_GITHUB_TOKEN / GITHUB_TOKEN env var.",
                err=True,
            )
            sys.exit(1)

        click.echo("", err=True)
        click.echo(f"Publishing to {registry_repo}...", err=True)

        result = publish_manifest(
            lcp_doc,
            token=token,
            registry_repo=registry_repo,
        )

        click.echo("", err=True)
        click.echo("✓ Pull request created successfully!", err=True)
        click.echo(f"  PR: {result.pr_url}", err=True)
        click.echo(f"  Manifest: {result.manifest_path}", err=True)

    except PublishError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("coverage_json", type=click.Path(exists=True))
@click.option(
    "--provider",
    type=click.Choice(["openai", "anthropic"]),
    default="openai",
    help="LLM provider (default: openai).",
)
@click.option(
    "--model",
    type=str,
    default=None,
    help="Model name (default: provider-specific).",
)
@click.option(
    "--api-key",
    type=str,
    default=None,
    help="API key (or use environment variables).",
)
@click.option(
    "--kinds",
    type=str,
    default=None,
    help="Filter by symbol kind, comma-separated (e.g. class,function,method).",
)
@click.option(
    "--description",
    type=str,
    default=None,
    help="Description to guide the AI agent.",
)
@click.option(
    "--reasoning",
    is_flag=True,
    default=False,
    help="Enable reasoning mode for OpenAI models (o1, o3, etc.).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be modified without writing.",
)
@click.option(
    "--workers",
    type=int,
    default=4,
    help="Max concurrent LLM calls (default: 4).",
)
@click.option(
    "--failure-threshold",
    type=float,
    default=0.5,
    help="Failure ratio (0.0-1.0) to skip parent symbols (default: 0.5).",
)
def docgen(
    coverage_json: str,
    provider: str,
    model: str | None,
    api_key: str | None,
    kinds: str | None,
    description: str | None,
    reasoning: bool,
    dry_run: bool,
    workers: int,
    failure_threshold: float,
):
    """Generate docstrings for undocumented symbols using AI.

    COVERAGE_JSON is the path to a coverage report JSON file
    (generated by `lcp coverage`).

    Examples:

        lcp docgen coverage.json --provider openai --dry-run

        lcp docgen coverage.json --provider anthropic --model claude-sonnet-4-20250514

        lcp docgen coverage.json --kinds class,function
    """
    try:
        from .ai import DocGenAgent
        from .ai.models import HierarchicalConfig

        # Build provider
        if provider == "openai":
            from .ai import OpenAIProvider

            kwargs = {}
            if model:
                kwargs["model"] = model
            if api_key:
                kwargs["api_key"] = api_key
            if reasoning:
                kwargs["reasoning"] = True
            llm_provider = OpenAIProvider(**kwargs)
        else:
            from .ai import AnthropicProvider

            kwargs = {}
            if model:
                kwargs["model"] = model
            if api_key:
                kwargs["api_key"] = api_key
            llm_provider = AnthropicProvider(**kwargs)

        # Build config
        parsed_kinds = [k.strip() for k in kinds.split(",")] if kinds else None
        config = HierarchicalConfig(
            kinds=parsed_kinds,
            description=description,
            dry_run=dry_run,
            max_workers=workers,
            failure_threshold=failure_threshold,
        )

        agent = DocGenAgent(provider=llm_provider, config=config)

        click.echo(f"Loading coverage from {coverage_json}...", err=True)
        click.echo(f"Mode: hierarchical (workers={workers})", err=True)
        if dry_run:
            click.echo("DRY RUN: no files will be modified.", err=True)

        result = agent.run_sync(coverage_json)

        # Print per-symbol results
        for r in result.results:
            status_icon = {
                "updated": "+",
                "dry_run": "~",
                "skipped": "-",
                "failed": "!",
            }.get(r.status, "?")
            line = f"  [{status_icon}] {r.symbol_id} ({r.kind}): {r.status}"
            if r.error:
                line += f"  [{r.error}]"
            click.echo(line, err=True)

        # Summary
        click.echo("", err=True)
        click.echo(
            f"Processed: {result.symbols_processed} | "
            f"Updated: {result.symbols_updated} | "
            f"Skipped: {result.symbols_skipped} | "
            f"Failed: {result.symbols_failed}",
            err=True,
        )
        click.echo(
            f"Token usage - "
            f"Input: {result.total_usage.input_tokens} | "
            f"Cache: {result.total_usage.cache_tokens} | "
            f"Output: {result.total_usage.output_tokens}",
            err=True,
        )
        if result.total_usage.reasoning_tokens:
            click.echo(
                f"Reasoning tokens: {result.total_usage.reasoning_tokens}",
                err=True,
            )

    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo(
            "Make sure the AI dependencies are installed: pip install lcp[ai]",
            err=True,
        )
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("old", type=click.Path(exists=True))
@click.argument("new", type=click.Path(exists=True))
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    help="Output file path. If not specified, prints to stdout.",
)
@click.option(
    "--indent",
    type=int,
    default=2,
    help="JSON indentation (default: 2).",
)
@click.option(
    "--update",
    is_flag=True,
    default=False,
    help="Write detected deprecations back into the NEW LCP file.",
)
def diff(old: str, new: str, output: str | None, indent: int, update: bool):
    """Compare two LCP files and detect deprecated symbols.

    OLD is the path to the earlier LCP JSON file.

    NEW is the path to the later LCP JSON file.

    Symbols present in OLD but missing in NEW are reported as removed
    (deprecated).  The output includes generated deprecation entries
    that can be merged into the new manifest.

    With --update the detected deprecations are automatically written
    back into the NEW file.

    Examples:

        lcp diff v1.lcp.json v2.lcp.json

        lcp diff v1.lcp.json v2.lcp.json -o diff.json

        lcp diff v1.lcp.json v2.lcp.json --update
    """
    from .diff import diff_documents, load_lcp_document, update_document

    try:
        click.echo(f"Loading {old}...", err=True)
        old_doc = load_lcp_document(old)

        click.echo(f"Loading {new}...", err=True)
        new_doc = load_lcp_document(new)

        click.echo("Comparing documents...", err=True)
        result = diff_documents(old_doc, new_doc)

        json_output = result.to_json(indent=indent)

        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(json_output)
            click.echo(f"Written to {output}", err=True)
        else:
            click.echo(json_output)

        # Summary
        click.echo(
            f"Diff: {result.library_name} "
            f"{result.old_version} → {result.new_version}",
            err=True,
        )
        click.echo(
            f"  Removed: {len(result.removed)} | Added: {len(result.added)}",
            err=True,
        )

        # Update the new file with deprecations if requested
        if update and result.deprecated:
            updated_doc = update_document(new_doc, result)
            updated_doc.to_file(new, indent=indent)
            click.echo(
                f"  Updated {new} with {len(result.deprecated)} deprecation(s)",
                err=True,
            )

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
