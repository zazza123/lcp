"""CLI for lcp-python-sdk."""

from __future__ import annotations

import sys

import click

from .generator import generate_lcp
from .mcp_server import run_server as run_mcp_server
from .scanner import scan_package
from .validator import LCPValidationError, validate_document


@click.group()
@click.version_option(version="0.1.0", prog_name="lcp-python")
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
def scan(
    package: str,
    output: str | None,
    include_private: bool,
    no_recursive: bool,
    validate: bool,
    indent: int,
):
    """Scan a Python package and generate an LCP file.

    PACKAGE is the name of an installed Python package to scan.

    Examples:

        lcp-python scan requests -o requests.lcp.json

        lcp-python scan numpy --include-private

        lcp-python scan mypackage --no-validate
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
        click.echo(f"Generating LCP document...", err=True)
        lcp_doc = generate_lcp(scanned)

        # Validate if requested
        if validate:
            click.echo("Validating against LCP schema...", err=True)
            try:
                from .validator import validate_or_raise

                validate_or_raise(lcp_doc)
                click.echo("✓ Validation passed", err=True)
            except LCPValidationError as e:
                click.echo(f"✗ Validation failed:\n{e}", err=True)
                sys.exit(1)

        # Output
        json_output = lcp_doc.to_json(indent=indent)

        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(json_output)
            click.echo(f"✓ Written to {output}", err=True)
            click.echo(f"  {len(lcp_doc.symbols)} symbols exported", err=True)
        else:
            click.echo(json_output)

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

        lcp-python serve requests.lcp.json

        lcp-python serve numpy.lcp.json --name numpy-docs
    """
    try:
        run_mcp_server(manifest, name=name)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
