"""DocGenAgent - orchestrator for AI documentation generation."""

from __future__ import annotations

import ast
import asyncio
import json
from collections import defaultdict
from pathlib import Path

from .hierarchy import ModuleTree, SymbolNode, build_context, build_hierarchy
from .models import DocGenConfig, DocGenResult, HierarchicalConfig, SymbolResult, TokenUsage
from .prompts import build_system_prompt, build_user_prompt, build_user_prompt_hierarchical
from .provider import LLMProvider
from .writer import inject_docstrings_batch


class DocGenAgent:
    """Agent that generates docstrings for undocumented Python symbols.

    Args:
        provider: LLM provider to use for generating docstrings.
        config: Configuration for the generation run.
    """

    def __init__(
        self,
        provider: LLMProvider,
        config: DocGenConfig | None = None,
    ) -> None:
        self._provider = provider
        self._config = config or DocGenConfig()

    def run(self, coverage_input: str | dict) -> DocGenResult:
        """Execute the documentation generation.

        Args:
            coverage_input: Path to coverage JSON file or parsed dict.

        Returns:
            DocGenResult with statistics and per-symbol results.
        """
        coverage_data = self._load_coverage(coverage_input)
        undocumented = coverage_data.get("undocumented", [])

        # Filter by kinds if configured
        symbols = self._filter_symbols(undocumented)

        if not symbols:
            return DocGenResult(
                symbols_processed=0,
                symbols_updated=0,
                symbols_skipped=0,
                symbols_failed=0,
                total_usage=TokenUsage(),
                results=[],
            )

        # Group symbols by source_file
        by_file: dict[str, list[tuple[int, dict]]] = defaultdict(list)
        no_file: list[tuple[int, dict]] = []

        for idx, sym in enumerate(symbols):
            source_file = sym.get("source_file")
            if source_file:
                by_file[source_file].append((idx, sym))
            else:
                no_file.append((idx, sym))

        # Process symbols and collect results
        all_results: list[SymbolResult] = [None] * len(symbols)  # type: ignore[list-item]
        total_usage = TokenUsage()

        # Process each file group
        for source_file, file_symbols in by_file.items():
            file_injections: list[tuple[int, str, str, str, SymbolResult]] = []

            for idx, sym in file_symbols:
                result = self._process_symbol(sym, source_file)
                all_results[idx] = result
                if result.usage:
                    total_usage = total_usage + result.usage

                if result.status in ("updated", "dry_run") and result.docstring:
                    file_injections.append(
                        (idx, sym.get("kind", ""), sym.get("entity", ""), result.docstring, result)
                    )

            # Batch write docstrings for this file
            if file_injections and not self._config.dry_run:
                injections = [
                    (kind, entity, docstring)
                    for _, kind, entity, docstring, _ in file_injections
                ]
                write_results = inject_docstrings_batch(source_file, injections)

                for i, success in enumerate(write_results):
                    _, _, _, _, sym_result = file_injections[i]
                    if not success:
                        sym_result.status = "skipped"

        # Process symbols without source files
        for idx, sym in no_file:
            result = SymbolResult(
                symbol_id=f"{sym.get('module', '')}:{sym.get('entity', '')}",
                kind=sym.get("kind", ""),
                source_file=None,
                status="skipped",
                error="No source file available",
            )
            all_results[idx] = result

        # Aggregate stats
        updated = sum(1 for r in all_results if r.status == "updated")
        skipped = sum(1 for r in all_results if r.status == "skipped")
        failed = sum(1 for r in all_results if r.status == "failed")
        dry_run_count = sum(1 for r in all_results if r.status == "dry_run")

        return DocGenResult(
            symbols_processed=len(symbols),
            symbols_updated=updated + dry_run_count,
            symbols_skipped=skipped,
            symbols_failed=failed,
            total_usage=total_usage,
            results=all_results,
        )

    def _load_coverage(self, coverage_input: str | dict) -> dict:
        """Load coverage data from a file path or dict."""
        if isinstance(coverage_input, dict):
            return coverage_input

        path = Path(coverage_input)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _filter_symbols(self, undocumented: list[dict]) -> list[dict]:
        """Filter symbols based on config.kinds."""
        if not self._config.kinds:
            return undocumented

        return [s for s in undocumented if s.get("kind") in self._config.kinds]

    def _read_source_context(
        self, source_file: str, kind: str, entity: str
    ) -> str:
        """Read the source code context for a symbol.

        Args:
            source_file: Path to the source file.
            kind: Symbol kind.
            entity: Entity name.

        Returns:
            Source code string for the symbol.
        """
        try:
            source = Path(source_file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return ""

        source_lines = source.splitlines()

        if kind == "module":
            # Return first ~30 lines for module context
            return "\n".join(source_lines[:30])

        # Find the node
        node = self._find_source_node(tree, kind, entity)
        if node is None:
            return ""

        start = node.lineno - 1
        end = getattr(node, "end_lineno", start + 1)
        # Limit to 50 lines of context
        end = min(end, start + 50)

        return "\n".join(source_lines[start:end])

    def _find_source_node(
        self, tree: ast.Module, kind: str, entity: str
    ) -> ast.AST | None:
        """Find an AST node by kind and entity name."""
        if "#" in entity:
            class_name, method_name = entity.split("#", 1)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if item.name == method_name:
                                return item
            return None

        for node in ast.iter_child_nodes(tree):
            if kind == "class" and isinstance(node, ast.ClassDef) and node.name == entity:
                return node
            if kind == "function" and isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                if node.name == entity:
                    return node

        return None

    def _generate_docstring(
        self, symbol: dict, source_context: str
    ) -> tuple[str, TokenUsage]:
        """Call the LLM to generate a docstring.

        Args:
            symbol: Symbol dict from coverage data.
            source_context: Source code context.

        Returns:
            Tuple of (docstring_text, token_usage).
        """
        system = build_system_prompt(
            docstring_style=self._config.docstring_style,
            description=self._config.description,
        )
        prompt = build_user_prompt(
            kind=symbol.get("kind", ""),
            module=symbol.get("module", ""),
            entity=symbol.get("entity", ""),
            source_context=source_context,
        )

        response = self._provider.generate(system, prompt)
        return response.content.strip(), response.usage

    def _process_symbol(self, symbol: dict, source_file: str) -> SymbolResult:
        """Process a single symbol: read context, generate docstring.

        Args:
            symbol: Symbol dict from coverage data.
            source_file: Path to source file.

        Returns:
            SymbolResult for this symbol.
        """
        symbol_id = f"{symbol.get('module', '')}:{symbol.get('entity', '')}"
        kind = symbol.get("kind", "")

        try:
            source_context = self._read_source_context(
                source_file, kind, symbol.get("entity", "")
            )

            if not source_context:
                return SymbolResult(
                    symbol_id=symbol_id,
                    kind=kind,
                    source_file=source_file,
                    status="skipped",
                    error="Could not read source context",
                )

            docstring, usage = self._generate_docstring(symbol, source_context)

            if not docstring:
                return SymbolResult(
                    symbol_id=symbol_id,
                    kind=kind,
                    source_file=source_file,
                    status="skipped",
                    usage=usage,
                    error="LLM returned empty docstring",
                )

            status = "dry_run" if self._config.dry_run else "updated"

            return SymbolResult(
                symbol_id=symbol_id,
                kind=kind,
                source_file=source_file,
                status=status,
                docstring=docstring,
                usage=usage,
            )

        except Exception as e:
            return SymbolResult(
                symbol_id=symbol_id,
                kind=kind,
                source_file=source_file,
                status="failed",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Hierarchical async engine
    # ------------------------------------------------------------------

    def run_sync(self, coverage_input: str | dict) -> DocGenResult:
        """Dispatch to flat run() or hierarchical run_async().

        Args:
            coverage_input: Path to coverage JSON file or parsed dict.

        Returns:
            DocGenResult with statistics and per-symbol results.
        """
        if not isinstance(self._config, HierarchicalConfig) or self._config.flat_mode:
            return self.run(coverage_input)
        return asyncio.run(self.run_async(coverage_input))

    async def run_async(self, coverage_input: str | dict) -> DocGenResult:
        """Execute hierarchical bottom-up documentation generation.

        Processes symbols level-by-level (leaves first, then classes,
        then modules), using asyncio.gather with a semaphore for
        concurrency control.

        Args:
            coverage_input: Path to coverage JSON file or parsed dict.

        Returns:
            DocGenResult with statistics and per-symbol results.
        """
        coverage_data = self._load_coverage(coverage_input)
        undocumented = coverage_data.get("undocumented", [])

        # Filter by kinds if configured
        symbols = self._filter_symbols(undocumented)

        if not symbols:
            return DocGenResult(
                symbols_processed=0,
                symbols_updated=0,
                symbols_skipped=0,
                symbols_failed=0,
                total_usage=TokenUsage(),
                results=[],
            )

        # Build hierarchy
        trees = build_hierarchy(symbols)

        config = self._config
        assert isinstance(config, HierarchicalConfig)
        sem = asyncio.Semaphore(config.max_workers)

        all_results: list[SymbolResult] = []
        total_usage = TokenUsage()

        # Process level by level: 0 (leaves) -> 1 (classes) -> 2 (modules)
        for level in (0, 1, 2):
            # Collect all pending nodes at this level from all trees
            level_nodes: list[tuple[SymbolNode, ModuleTree]] = []
            for tree in trees.values():
                for node in tree.levels.get(level, []):
                    if node.status == "pending":
                        level_nodes.append((node, tree))

            if not level_nodes:
                continue

            # Process all nodes at this level concurrently
            coros = [
                self._process_node(node, tree, sem)
                for node, tree in level_nodes
            ]
            results = await asyncio.gather(*coros, return_exceptions=True)

            # Collect results and update node status/docstring
            for i, result in enumerate(results):
                node, _tree = level_nodes[i]
                if isinstance(result, Exception):
                    sym_result = SymbolResult(
                        symbol_id=node.symbol_id,
                        kind=node.kind,
                        source_file=node.symbol.get("source_file"),
                        status="failed",
                        error=str(result),
                    )
                    node.status = "failed"
                else:
                    sym_result = result
                    node.status = sym_result.status
                    if sym_result.docstring:
                        node.docstring = sym_result.docstring

                all_results.append(sym_result)
                if sym_result.usage:
                    total_usage = total_usage + sym_result.usage

            # Propagate failures to next level
            self._propagate_failures(trees, level, config.failure_threshold)

        # Collect skipped nodes from propagation (nodes that were pending
        # but got marked as skipped by _propagate_failures)
        for tree in trees.values():
            for level_nodes_list in tree.levels.values():
                for node in level_nodes_list:
                    if node.status == "skipped":
                        # Check if already in results
                        existing_ids = {r.symbol_id for r in all_results}
                        if node.symbol_id not in existing_ids:
                            all_results.append(SymbolResult(
                                symbol_id=node.symbol_id,
                                kind=node.kind,
                                source_file=node.symbol.get("source_file"),
                                status="skipped",
                                error="Skipped due to child failure propagation",
                            ))

        # Batch write results if not dry_run
        if not config.dry_run:
            self._write_results(all_results)

        # Aggregate stats
        updated = sum(1 for r in all_results if r.status == "updated")
        skipped = sum(1 for r in all_results if r.status == "skipped")
        failed = sum(1 for r in all_results if r.status == "failed")
        dry_run_count = sum(1 for r in all_results if r.status == "dry_run")

        return DocGenResult(
            symbols_processed=len(all_results),
            symbols_updated=updated + dry_run_count,
            symbols_skipped=skipped,
            symbols_failed=failed,
            total_usage=total_usage,
            results=all_results,
        )

    async def _process_node(
        self,
        node: SymbolNode,
        tree: ModuleTree,
        semaphore: asyncio.Semaphore,
    ) -> SymbolResult:
        """Process a single SymbolNode asynchronously.

        Args:
            node: The symbol node to process.
            tree: The module tree containing this node.
            semaphore: Semaphore for concurrency control.

        Returns:
            SymbolResult for this node.
        """
        async with semaphore:
            context = build_context(node, tree)
            if not context:
                return SymbolResult(
                    symbol_id=node.symbol_id,
                    kind=node.kind,
                    source_file=node.symbol.get("source_file"),
                    status="skipped",
                    error="Could not build context",
                )

            system = build_system_prompt(
                docstring_style=self._config.docstring_style,
                description=self._config.description,
            )
            prompt = build_user_prompt_hierarchical(node, context)
            response = await self._provider.agenerate(system, prompt)

            docstring = response.content.strip()
            if not docstring:
                return SymbolResult(
                    symbol_id=node.symbol_id,
                    kind=node.kind,
                    source_file=node.symbol.get("source_file"),
                    status="skipped",
                    usage=response.usage,
                    error="LLM returned empty docstring",
                )

            status = "dry_run" if self._config.dry_run else "updated"
            return SymbolResult(
                symbol_id=node.symbol_id,
                kind=node.kind,
                source_file=node.symbol.get("source_file"),
                status=status,
                docstring=docstring,
                usage=response.usage,
            )

    def _propagate_failures(
        self,
        trees: dict[str, ModuleTree],
        completed_level: int,
        threshold: float,
    ) -> None:
        """Mark parent nodes as skipped if too many children failed.

        After processing a level, check the next level's nodes. If a
        parent's children have a failure ratio >= threshold, skip it.

        Args:
            trees: All module trees.
            completed_level: The level that was just processed.
            threshold: Failure ratio threshold (0.0 to 1.0).
        """
        next_level = completed_level + 1
        for tree in trees.values():
            for parent in tree.levels.get(next_level, []):
                if parent.status != "pending":
                    continue
                children = parent.children
                if not children:
                    continue
                failed = sum(1 for c in children if c.status == "failed")
                if failed / len(children) >= threshold:
                    parent.status = "skipped"

    def _write_results(self, results: list[SymbolResult]) -> None:
        """Batch write all generated docstrings grouped by file.

        Args:
            results: List of SymbolResult from the async run.
        """
        by_file: dict[str, list[SymbolResult]] = defaultdict(list)
        for r in results:
            if r.status == "updated" and r.docstring and r.source_file:
                by_file[r.source_file].append(r)

        for source_file, file_results in by_file.items():
            injections: list[tuple[str, str, str]] = []
            for r in file_results:
                # Extract entity from symbol_id (format: "module:entity")
                entity = r.symbol_id.split(":", 1)[-1]
                injections.append((r.kind, entity, r.docstring))

            write_results = inject_docstrings_batch(source_file, injections)

            for i, success in enumerate(write_results):
                if not success:
                    file_results[i].status = "skipped"
