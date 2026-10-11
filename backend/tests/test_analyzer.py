import stat
import sys
import zipfile
from pathlib import Path

import pytest

from app.services.analyzer import (
    AnalysisError,
    _analysis_coverage,
    _is_regular_archive_entry,
    _python_symbols,
    _run_bounded_process,
    _safe_archive_path,
    _static_findings,
    _symbols_for_source,
    parse_github_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/octocat/hello",
        "https://evil.example/octocat/hello",
        "https://user:pass@github.com/octocat/hello",
        "https://github.com:444/octocat/hello",
        "https://github.com:bad/octocat/hello",
        "https://github.com/octocat/../other",
        "https://github.com/octocat",
    ],
)
def test_rejects_unsafe_or_unsupported_urls(url: str) -> None:
    with pytest.raises(AnalysisError):
        parse_github_url(url)


@pytest.mark.parametrize(
    ("url", "canonical"),
    [
        ("https://github.com/octocat/hello", "https://github.com/octocat/hello"),
        ("https://github.com/octocat/hello.git", "https://github.com/octocat/hello"),
        ("https://www.github.com/octocat/hello/", "https://github.com/octocat/hello"),
    ],
)
def test_accepts_supported_public_repo_url_forms(url: str, canonical: str) -> None:
    assert parse_github_url(url)[2] == canonical


@pytest.mark.parametrize(
    "path", ["../evil.py", "/absolute.py", "root/../../escape.py", "root\\evil.py"]
)
def test_archive_path_rejects_traversal(path: str) -> None:
    assert _safe_archive_path(path, "root") is None


def test_archive_path_strips_only_archive_prefix() -> None:
    assert _safe_archive_path("root/src/main.py", "root") == "src/main.py"


@pytest.mark.parametrize("file_type", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR])
def test_archive_skips_symlinks_and_special_file_types(file_type: int) -> None:
    entry = zipfile.ZipInfo("root/payload.py")
    entry.create_system = 3
    entry.external_attr = (file_type | 0o644) << 16
    assert not _is_regular_archive_entry(entry)


def test_archive_accepts_regular_file_and_unspecified_zip_mode() -> None:
    regular = zipfile.ZipInfo("root/source.py")
    regular.create_system = 3
    regular.external_attr = (stat.S_IFREG | 0o644) << 16
    unspecified = zipfile.ZipInfo("root/legacy.py")
    assert _is_regular_archive_entry(regular)
    assert _is_regular_archive_entry(unspecified)


def test_python_ast_extracts_structural_symbols() -> None:
    symbols = _python_symbols(
        "import os\n\nclass Store:\n    def load(self):\n        return os.getcwd()\n", "store.py"
    )
    assert [(symbol.kind, symbol.name) for symbol in symbols] == [
        ("import", "os"),
        ("class", "Store"),
        ("function", "load"),
    ]


def test_python_ast_handles_syntax_errors() -> None:
    assert _python_symbols("def broken(:\n", "broken.py") == []


def test_javascript_parser_extracts_imports_functions_classes_methods_and_ranges() -> None:
    source = Path(__file__).parent / "fixtures" / "symbols.js"
    symbols = _symbols_for_source(source.read_text(encoding="utf-8"), "src/symbols.js")
    by_name = {(symbol.kind, symbol.name): symbol for symbol in symbols}

    assert ("import", "./format.js") in by_name
    assert ("function", "greet") in by_name
    assert ("function", "normalize") in by_name
    assert ("class", "Greeter") in by_name
    assert ("method", "constructor") in by_name
    assert ("method", "say") in by_name
    assert (by_name[("function", "greet")].start_line, by_name[("function", "greet")].end_line) == (3, 5)
    assert (by_name[("method", "say")].start_line, by_name[("method", "say")].end_line) == (14, 16)


def test_typescript_parser_extracts_imports_functions_classes_methods_and_ranges() -> None:
    source = Path(__file__).parent / "fixtures" / "symbols.ts"
    symbols = _symbols_for_source(source.read_text(encoding="utf-8"), "src/symbols.ts")
    by_name = {(symbol.kind, symbol.name): symbol for symbol in symbols}

    assert ("import", "./user.js") in by_name
    assert ("function", "displayName") in by_name
    assert ("class", "UserLabel") in by_name
    assert ("method", "render") in by_name
    assert (by_name[("function", "displayName")].start_line, by_name[("function", "displayName")].end_line) == (3, 5)
    assert (by_name[("method", "render")].start_line, by_name[("method", "render")].end_line) == (8, 10)


def test_tsx_parser_handles_jsx_syntax_without_execution() -> None:
    source = Path(__file__).parent / "fixtures" / "symbols.tsx"
    symbols = _symbols_for_source(source.read_text(encoding="utf-8"), "src/Button.tsx")
    by_name = {(symbol.kind, symbol.name): symbol for symbol in symbols}

    assert ("import", "react") in by_name
    assert ("function", "Button") in by_name
    assert (by_name[("function", "Button")].start_line, by_name[("function", "Button")].end_line) == (3, 5)


def test_python_structure_dispatch_preserves_ast_extraction_and_ranges() -> None:
    symbols = _symbols_for_source("class Box:\n    def get(self):\n        return 1\n", "box.py")
    assert [(symbol.kind, symbol.name) for symbol in symbols] == [
        ("class", "Box"),
        ("function", "get"),
    ]
    assert (symbols[1].start_line, symbols[1].end_line) == (2, 3)


def test_malformed_and_unsupported_sources_are_safely_ignored() -> None:
    fixture = Path(__file__).parent / "fixtures" / "malformed.ts"
    assert _symbols_for_source(fixture.read_text(encoding="utf-8"), "malformed.ts") == []
    assert _symbols_for_source("function valid() {}", "script.rb") == []


def test_analysis_coverage_does_not_describe_unscanned_languages_as_clean() -> None:
    coverage = _analysis_coverage(
        [("main.py", "print('ok')")], {"ruff": "0.12.2", "bandit": "unavailable"}
    )
    assert coverage == {
        "Python": "partially_analyzed",
        "JavaScript": "not_analyzed",
        "TypeScript": "not_analyzed",
    }
    assert _analysis_coverage([], {})["Python"] == "no_supported_files"


def test_static_tools_report_python_findings_when_installed() -> None:
    findings, versions = _static_findings([("sample.py", "import os\neval(input())\n")])
    assert versions["ruff"] != "unavailable"
    assert versions["bandit"] != "unavailable"
    assert {finding.source for finding in findings} == {"Ruff", "Bandit"}


def test_analyzer_subprocess_output_is_bounded() -> None:
    command = [sys.executable, "-c", "print('x' * 1100000)"]
    assert _run_bounded_process(command, "") is None
