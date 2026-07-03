import pytest

from harness.extract import extract_code_blocks, extract_usage


class TestExtractCodeBlocks:
    def test_single_python_block(self):
        text = "Here you go:\n```python\nx = 1\n```\ndone"
        assert extract_code_blocks(text) == ["x = 1"]

    def test_bare_fence_and_py_fence(self):
        text = "```\na = 1\n```\n```py\nb = 2\n```"
        assert extract_code_blocks(text) == ["a = 1", "b = 2"]

    def test_no_blocks(self):
        assert extract_code_blocks("no code here") == []


class TestExtractUsage:
    def test_import_alias_chain(self):
        code = "import polars as pl\ndf = pl.read_csv('x.csv')"
        usage = extract_usage(code, "polars")
        assert "polars.read_csv" in usage.dotted_paths

    def test_plain_import(self):
        code = "import httpx\nc = httpx.Client()"
        usage = extract_usage(code, "httpx")
        assert "httpx.Client" in usage.dotted_paths

    def test_from_import(self):
        code = "from httpx import Client\nc = Client()"
        usage = extract_usage(code, "httpx")
        assert "httpx.Client" in usage.dotted_paths

    def test_from_submodule_import(self):
        code = "from textual.widgets import RichLog\nw = RichLog()"
        usage = extract_usage(code, "textual")
        assert "textual.widgets.RichLog" in usage.dotted_paths

    def test_submodule_import_alias(self):
        code = "import polars.selectors as cs\ncs.numeric()"
        usage = extract_usage(code, "polars")
        assert "polars.selectors.numeric" in usage.dotted_paths

    def test_method_on_variable_recorded_as_method_name(self):
        code = "import polars as pl\ndf = pl.read_csv('x')\ndf.group_by('a')"
        usage = extract_usage(code, "polars")
        assert "group_by" in usage.method_names
        assert "polars.group_by" not in usage.dotted_paths

    def test_method_on_call_result(self):
        code = "import polars as pl\npl.read_csv('x').groupby('a')"
        usage = extract_usage(code, "polars")
        assert "groupby" in usage.method_names

    def test_other_library_ignored_in_dotted_paths(self):
        code = "import os\nimport polars as pl\nos.path.join('a')\npl.col('x')"
        usage = extract_usage(code, "polars")
        assert not any(p.startswith("os.") for p in usage.dotted_paths)

    def test_subclass_method_defs_recorded(self):
        code = (
            "from textual.app import App\n"
            "class MyApp(App):\n"
            "    def compose(self):\n"
            "        yield from ()\n"
        )
        usage = extract_usage(code, "textual")
        assert "compose" in usage.method_names
        assert "textual.app.App" in usage.dotted_paths

    def test_syntax_error_propagates(self):
        with pytest.raises(SyntaxError):
            extract_usage("def broken(:", "polars")

    def test_bare_module_alias_not_in_dotted_paths(self):
        code = "import polars as pl\npl.read_csv('x')"
        usage = extract_usage(code, "polars")
        assert "polars.read_csv" in usage.dotted_paths
        assert "polars" not in usage.dotted_paths

    def test_foreign_module_attrs_not_in_method_names(self):
        code = (
            "import os\n"
            "import polars as pl\n"
            "os.path.join('a')\n"
            "pl.col('x')\n"
        )
        usage = extract_usage(code, "polars")
        assert "join" not in usage.method_names
        assert "path" not in usage.method_names

    def test_foreign_from_import_attrs_not_in_method_names(self):
        code = (
            "from pathlib import Path\n"
            "import polars as pl\n"
            "Path.home()\n"
            "pl.col('x')\n"
        )
        usage = extract_usage(code, "polars")
        assert "home" not in usage.method_names
