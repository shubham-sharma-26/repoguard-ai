import sys

import pytest

from app.services.analyzer import (
    AnalysisError,
    _python_symbols,
    _run_bounded_process,
    _safe_archive_path,
    _static_findings,
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


def test_accepts_canonical_public_repo_url() -> None:
    assert (
        parse_github_url("https://github.com/octocat/hello.git")[2]
        == "https://github.com/octocat/hello"
    )


@pytest.mark.parametrize(
    "path", ["../evil.py", "/absolute.py", "root/../../escape.py", "root\\evil.py"]
)
def test_archive_path_rejects_traversal(path: str) -> None:
    assert _safe_archive_path(path, "root") is None


def test_archive_path_strips_only_archive_prefix() -> None:
    assert _safe_archive_path("root/src/main.py", "root") == "src/main.py"


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


def test_static_tools_report_python_findings_when_installed() -> None:
    findings, versions = _static_findings([("sample.py", "import os\neval(input())\n")])
    assert versions["ruff"] != "unavailable"
    assert versions["bandit"] != "unavailable"
    assert {finding.source for finding in findings} == {"Ruff", "Bandit"}


def test_analyzer_subprocess_output_is_bounded() -> None:
    command = [sys.executable, "-c", "print('x' * 1100000)"]
    assert _run_bounded_process(command, "") is None
