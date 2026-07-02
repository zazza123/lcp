"""Eval case model, YAML loading, and validation against the pinned environment."""

import importlib.metadata
from dataclasses import dataclass
from pathlib import Path

import yaml

from harness import verify

# Distribution name -> import name, where they differ.
_IMPORT_NAMES = {"pyyaml": "yaml"}


class CaseError(Exception):
    """Raised when case files are malformed."""


@dataclass
class EvalCase:
    id: str
    library: str
    version: str
    prompt: str
    required_symbols: list[str]
    forbidden_symbols: list[str]

    @property
    def import_name(self) -> str:
        return _IMPORT_NAMES.get(self.library, self.library)


def load_cases(cases_dir: Path) -> list[EvalCase]:
    """Load all *.yaml case files in cases_dir; raise CaseError if malformed."""
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for path in sorted(Path(cases_dir).glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, list):
            raise CaseError(f"{path}: top level must be a list of cases")
        for raw in data:
            checks = raw.get("checks") or {}
            try:
                case = EvalCase(
                    id=raw["id"],
                    library=raw["library"],
                    version=str(raw["version"]),
                    prompt=str(raw["prompt"]).strip(),
                    required_symbols=list(checks.get("required_symbols") or []),
                    forbidden_symbols=list(checks.get("forbidden_symbols") or []),
                )
            except KeyError as exc:
                raise CaseError(f"{path}: case missing key {exc}") from exc
            if case.id in seen:
                raise CaseError(f"{path}: duplicate case id {case.id!r}")
            seen.add(case.id)
            cases.append(case)
    return cases


def validate_cases(cases: list[EvalCase]) -> list[str]:
    """Return a list of problems (empty = all cases valid).

    Checks: library installed at the pinned version, every required symbol
    resolves, and every forbidden symbol does NOT resolve (otherwise it is
    not a hallucination trap).
    """
    problems: list[str] = []
    for case in cases:
        try:
            installed = importlib.metadata.version(case.library)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"{case.id}: library {case.library!r} not installed")
            continue
        if installed != case.version:
            problems.append(
                f"{case.id}: pinned version {case.version}, installed {installed}"
            )
        for sym in case.required_symbols:
            if not verify.resolve_symbol(sym):
                problems.append(f"{case.id}: required symbol does not resolve: {sym}")
        for sym in case.forbidden_symbols:
            if verify.resolve_symbol(sym):
                problems.append(
                    f"{case.id}: forbidden symbol resolves (not a valid trap): {sym}"
                )
    return problems
