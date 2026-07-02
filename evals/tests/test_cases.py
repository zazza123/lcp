import pytest

from harness.cases import CaseError, EvalCase, load_cases, validate_cases

VALID_YAML = """
- id: json-loads
  library: json
  version: "0"
  prompt: Parse a JSON string.
  checks:
    required_symbols: ["json:loads"]
    forbidden_symbols: ["json:parse"]
"""


def write(tmp_path, name, content):
    (tmp_path / name).write_text(content)
    return tmp_path


class TestLoadCases:
    def test_loads_valid_case(self, tmp_path):
        cases = load_cases(write(tmp_path, "json.yaml", VALID_YAML))
        assert len(cases) == 1
        case = cases[0]
        assert case.id == "json-loads"
        assert case.library == "json"
        assert case.required_symbols == ["json:loads"]
        assert case.forbidden_symbols == ["json:parse"]

    def test_missing_key_raises(self, tmp_path):
        write(tmp_path, "bad.yaml", "- id: x\n  library: json\n")
        with pytest.raises(CaseError, match="missing key"):
            load_cases(tmp_path)

    def test_duplicate_id_raises(self, tmp_path):
        write(tmp_path, "a.yaml", VALID_YAML)
        write(tmp_path, "b.yaml", VALID_YAML)
        with pytest.raises(CaseError, match="duplicate"):
            load_cases(tmp_path)

    def test_empty_checks_default_to_empty_lists(self, tmp_path):
        write(tmp_path, "a.yaml",
              "- id: x\n  library: json\n  version: '0'\n  prompt: p\n")
        case = load_cases(tmp_path)[0]
        assert case.required_symbols == []
        assert case.forbidden_symbols == []


def make_case(**kw):
    base = dict(id="c1", library="pyyaml", version="", prompt="p",
                required_symbols=[], forbidden_symbols=[])
    base.update(kw)
    return EvalCase(**base)


class TestValidateCases:
    def test_valid_case_no_problems(self):
        import importlib.metadata
        case = make_case(version=importlib.metadata.version("pyyaml"),
                         required_symbols=["yaml:safe_load"],
                         forbidden_symbols=["yaml:load_safe"])
        assert validate_cases([case]) == []

    def test_version_mismatch_reported(self):
        case = make_case(version="0.0.0")
        problems = validate_cases([case])
        assert any("0.0.0" in p for p in problems)

    def test_unresolvable_required_reported(self):
        import importlib.metadata
        case = make_case(version=importlib.metadata.version("pyyaml"),
                         required_symbols=["yaml:no_such_fn"])
        assert any("required" in p for p in validate_cases([case]))

    def test_resolvable_forbidden_reported(self):
        import importlib.metadata
        case = make_case(version=importlib.metadata.version("pyyaml"),
                         forbidden_symbols=["yaml:safe_load"])
        assert any("forbidden" in p for p in validate_cases([case]))

    def test_uninstalled_library_reported(self):
        case = make_case(library="no_such_dist_xyz")
        assert any("not installed" in p for p in validate_cases([case]))
