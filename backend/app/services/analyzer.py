import ast
import json
import os
import re
import threading
import time
import uuid
import zipfile
from collections import Counter
from datetime import UTC, datetime
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import urlparse

import httpx
import tree_sitter_python
from tree_sitter import Language, Parser

from app.core.config import get_settings
from app.schemas import AnalysisResult, Chunk, FileInfo, Finding, Symbol
from app.services.github_transport import PinnedGitHubTransport

EXTENSIONS = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C",
    ".html": "HTML",
    ".css": "CSS",
    ".md": "Markdown",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".sql": "SQL",
}
MAX_ARCHIVE_BYTES = 30_000_000
MAX_SCANNER_OUTPUT_BYTES = 1_000_000


class AnalysisError(ValueError):
    pass


def parse_github_url(raw: str) -> tuple[str, str, str]:
    try:
        parsed = urlparse(raw.strip())
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise AnalysisError("The GitHub URL is malformed.") from exc
    if parsed.scheme != "https" or host not in {"github.com", "www.github.com"}:
        raise AnalysisError("Use a public GitHub URL such as https://github.com/owner/repository.")
    if parsed.username or parsed.password or port not in (None, 443):
        raise AnalysisError("Credentials and custom ports are not supported.")
    if parsed.netloc.casefold() not in {
        "github.com",
        "github.com:443",
        "www.github.com",
        "www.github.com:443",
    }:
        raise AnalysisError("The GitHub URL authority is not supported.")
    if parsed.query or parsed.fragment:
        raise AnalysisError("Repository URLs must not include a query or fragment.")
    pieces = parsed.path.split("/")
    if len(pieces) not in {3, 4} or pieces[0] or (len(pieces) == 4 and pieces[3]):
        raise AnalysisError("The URL must point directly to an owner and repository.")
    owner, name = pieces[1:3]
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", owner) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,100}", name
    ):
        raise AnalysisError("The GitHub owner or repository name is invalid.")
    return (
        owner,
        name.removesuffix(".git"),
        f"https://github.com/{owner}/{name.removesuffix('.git')}",
    )


def _validate_archive_redirect(location: str, owner: str, name: str, commit_sha: str) -> str:
    try:
        target = urlparse(location)
        port = target.port
    except ValueError as exc:
        raise AnalysisError("GitHub returned an unsupported archive destination.") from exc
    expected_archive_paths = {
        f"/{owner}/{name}/legacy.zip/{commit_sha}".casefold(),
        f"/{owner}/{name}/zip/{commit_sha}".casefold(),
    }
    if (
        target.scheme != "https"
        or target.hostname != "codeload.github.com"
        or port not in (None, 443)
        or target.netloc.casefold() not in {"codeload.github.com", "codeload.github.com:443"}
        or target.username
        or target.password
        or target.query
        or target.fragment
        or target.path.casefold() not in expected_archive_paths
    ):
        raise AnalysisError("GitHub returned an unsupported archive destination.")
    return location


def _safe_archive_path(name: str, root: str) -> str | None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        return None
    parts = path.parts
    if len(parts) < 2 or parts[0] != root:
        return None
    rel = PurePosixPath(*parts[1:]).as_posix()
    return rel if rel and not rel.startswith("../") else None


async def _read_bounded_archive(response: httpx.Response) -> bytes:
    parts: list[bytes] = []
    size = 0
    async for part in response.aiter_bytes():
        size += len(part)
        if size > MAX_ARCHIVE_BYTES:
            raise AnalysisError("Repository archive exceeds the 30 MB download limit.")
        parts.append(part)
    return b"".join(parts)


async def _github_json(client: httpx.AsyncClient, url: str) -> tuple[int, httpx.Headers, dict]:
    parts: list[bytes] = []
    size = 0
    async with client.stream("GET", url) as response:
        status = response.status_code
        headers = response.headers
        async for part in response.aiter_bytes():
            size += len(part)
            if size > 1_000_000:
                raise AnalysisError("GitHub metadata response exceeds the 1 MB limit.")
            parts.append(part)
    try:
        payload = json.loads(b"".join(parts))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError("GitHub returned invalid repository metadata.") from exc
    if not isinstance(payload, dict):
        raise AnalysisError("GitHub returned invalid repository metadata.")
    return status, headers, payload


def _run_bounded_process(args: list[str], input_text: str, timeout: int = 3) -> str | None:
    """Run a local analyzer with bounded time and captured output; never invokes a shell."""
    import subprocess

    process = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    output = bytearray()
    exceeded = threading.Event()
    timed_out = threading.Event()

    def read_stdout() -> None:
        assert process.stdout is not None
        while chunk := process.stdout.read(65536):
            if len(output) + len(chunk) > MAX_SCANNER_OUTPUT_BYTES:
                exceeded.set()
                process.kill()
                return
            output.extend(chunk)

    def write_stdin() -> None:
        assert process.stdin is not None
        try:
            process.stdin.write(input_text.encode("utf-8"))
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            process.stdin.close()

    reader = threading.Thread(target=read_stdout, daemon=True)
    writer = threading.Thread(target=write_stdin, daemon=True)
    reader.start()
    writer.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out.set()
        process.kill()
        process.wait()
    reader.join(timeout=1)
    writer.join(timeout=1)
    if process.poll() is None:
        process.kill()
        process.wait()
    if exceeded.is_set() or timed_out.is_set():
        return None
    return output.decode("utf-8", errors="replace")


def _python_symbols(text: str, path: str) -> list[Symbol]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    results: list[Symbol] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            results.append(
                Symbol(
                    name=node.name,
                    kind="class" if isinstance(node, ast.ClassDef) else "function",
                    path=path,
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    summary=ast.get_docstring(node) or "",
                )
            )
        elif isinstance(node, ast.Import | ast.ImportFrom):
            module = (
                node.module
                if isinstance(node, ast.ImportFrom)
                else ", ".join(n.name for n in node.names)
            )
            results.append(
                Symbol(
                    name=module or "relative import",
                    kind="import",
                    path=path,
                    start_line=node.lineno,
                    end_line=node.lineno,
                )
            )
        elif isinstance(node, ast.Assign | ast.AnnAssign) and getattr(node, "col_offset", 1) == 0:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    results.append(
                        Symbol(
                            name=target.id,
                            kind="definition",
                            path=path,
                            start_line=node.lineno,
                            end_line=getattr(node, "end_lineno", node.lineno),
                        )
                    )
    return sorted(results, key=lambda item: (item.start_line, item.name))


def _tree_sitter_parse(text: str) -> int:
    parser = Parser(Language(tree_sitter_python.language()))
    return int(parser.parse(text.encode("utf-8")).root_node.has_error)


def _static_findings(files: list[tuple[str, str]]) -> tuple[list[Finding], dict[str, str]]:
    findings: list[Finding] = []
    versions: dict[str, str] = {}
    files = files[:100]
    try:
        import ruff

        versions["ruff"] = ruff.__name__
        import subprocess

        from ruff.__main__ import find_ruff_bin

        ruff_bin = find_ruff_bin()
        version = subprocess.run(
            [ruff_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if version.returncode == 0:
            versions["ruff"] = version.stdout.strip().split()[-1]
        for path, text in files:
            try:
                output = _run_bounded_process(
                    [ruff_bin, "check", "--output-format", "json", "-"], text
                )
                if output is None:
                    continue
                for item in json.loads(output or "[]"):
                    loc = item.get("location", {})
                    findings.append(
                        Finding(
                            severity="low",
                            rule_id=item.get("code") or "RUFF",
                            title=item.get("message", "Ruff finding")[:120],
                            message=item.get("message", ""),
                            path=path,
                            line=loc.get("row"),
                            end_line=item.get("end_location", {}).get("row"),
                            source="Ruff",
                            evidence=item.get("message", ""),
                        )
                    )
            except (ImportError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
                continue
    except ImportError:
        versions["ruff"] = "unavailable"
    try:
        import bandit

        versions["bandit"] = getattr(bandit, "__version__", "installed")
        for path, text in files:
            try:
                import subprocess

                output = _run_bounded_process(
                    [os.sys.executable, "-m", "bandit", "-f", "json", "-q", "-"], text
                )
                if output is None:
                    continue
                payload = json.loads(output or "{}")
                for item in payload.get("results", []):
                    findings.append(
                        Finding(
                            severity=item.get("issue_severity", "LOW").lower(),
                            rule_id=item.get("test_id", "BANDIT"),
                            title=item.get("test_name", "Bandit finding"),
                            message=item.get("issue_text", ""),
                            path=path,
                            line=item.get("line_number"),
                            end_line=item.get("line_number"),
                            source="Bandit",
                            evidence=item.get("code", ""),
                        )
                    )
            except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
                continue
    except ImportError:
        versions["bandit"] = "unavailable"
    return findings, versions


async def analyze_repository(raw_url: str) -> AnalysisResult:
    started = time.monotonic()
    settings = get_settings()
    owner, name, canonical_url = parse_github_url(raw_url)
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    timeout = httpx.Timeout(settings.request_timeout)
    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        transport=PinnedGitHubTransport({"api.github.com"}),
    ) as client:
        status, response_headers, meta = await _github_json(
            client, f"https://api.github.com/repos/{owner}/{name}"
        )
        if status == 404:
            raise AnalysisError("Repository was not found or is not publicly accessible.")
        if status in (403, 429) and (
            response_headers.get("x-ratelimit-remaining") == "0" or status == 429
        ):
            raise AnalysisError(
                "GitHub API rate limit reached. Try again later or configure a GitHub token."
            )
        if status != 200:
            raise AnalysisError(
                f"GitHub could not provide repository metadata (HTTP {status})."
            )
        if meta.get("private"):
            raise AnalysisError("Only public repositories can be analyzed.")
        if meta.get("size", 0) * 1024 > MAX_ARCHIVE_BYTES:
            raise AnalysisError("Repository is larger than the 30 MB archive limit.")
        branch = meta.get("default_branch", "HEAD")
        branch_status, _, commit_payload = await _github_json(
            client, f"https://api.github.com/repos/{owner}/{name}/commits/{branch}"
        )
        if branch_status != 200:
            raise AnalysisError("Could not resolve the repository's current commit.")
        commit_sha = commit_payload.get("sha", "")
        if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
            raise AnalysisError("GitHub returned an invalid commit identifier.")
        archive_url = f"https://api.github.com/repos/{owner}/{name}/zipball/{commit_sha}"
        async with client.stream("GET", archive_url) as archive_response:
            archive_status = archive_response.status_code
            location = archive_response.headers.get("location", "")
            if archive_status == 200:
                archive_content = await _read_bounded_archive(archive_response)
        if archive_status in (301, 302, 303, 307, 308):
            location = _validate_archive_redirect(location, owner, name, commit_sha)
            # Do not forward GitHub API authorization headers to the archive host.
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
                transport=PinnedGitHubTransport({"codeload.github.com"}),
            ) as archive_client:
                async with archive_client.stream("GET", location) as archive_response:
                    if archive_response.status_code != 200:
                        raise AnalysisError("GitHub archive download failed.")
                    archive_content = await _read_bounded_archive(archive_response)
        elif archive_status != 200:
            raise AnalysisError("Repository archive could not be downloaded within the size limit.")

    files: list[FileInfo] = []
    skipped: list[FileInfo] = []
    source: list[tuple[str, str]] = []
    chunks: list[Chunk] = []
    symbols: list[Symbol] = []
    languages: Counter[str] = Counter()
    total_bytes = 0
    try:
        with zipfile.ZipFile(BytesIO(archive_content)) as archive:
            entries = archive.infolist()
            if len(entries) > settings.max_files * 2:
                raise AnalysisError("Repository contains too many archive entries.")
            root = entries[0].filename.split("/")[0] if entries else ""
            for item in entries:
                rel = _safe_archive_path(item.filename, root)
                if rel is None or item.is_dir():
                    continue
                if item.file_size > settings.max_file_bytes:
                    skipped.append(
                        FileInfo(
                            path=rel,
                            size=item.file_size,
                            language="Unknown",
                            reason_skipped="File exceeds per-file limit",
                        )
                    )
                    continue
                if item.file_size > MAX_ARCHIVE_BYTES or (
                    item.compress_size and item.file_size / item.compress_size > 200
                ):
                    skipped.append(
                        FileInfo(
                            path=rel,
                            size=item.file_size,
                            language="Unknown",
                            reason_skipped="Suspicious archive compression ratio",
                        )
                    )
                    continue
                if (
                    len(files) >= settings.max_files
                    or total_bytes + item.file_size > settings.max_total_bytes
                ):
                    skipped.append(
                        FileInfo(
                            path=rel,
                            size=item.file_size,
                            language="Unknown",
                            reason_skipped="Repository analysis limit reached",
                        )
                    )
                    continue
                total_bytes += item.file_size
                ext = PurePosixPath(rel).suffix.lower()
                language = EXTENSIONS.get(ext, "Other")
                info = FileInfo(path=rel, size=item.file_size, language=language)
                files.append(info)
                languages[language] += 1
                if ext not in EXTENSIONS:
                    skipped.append(
                        FileInfo(
                            path=rel,
                            size=item.file_size,
                            language=language,
                            reason_skipped="Unsupported file type",
                        )
                    )
                    continue
                if item.file_size == 0:
                    continue
                try:
                    data = archive.read(item)
                    text = data.decode("utf-8")
                except (UnicodeDecodeError, RuntimeError, OSError):
                    skipped.append(
                        FileInfo(
                            path=rel,
                            size=item.file_size,
                            language=language,
                            reason_skipped="Binary or invalid UTF-8",
                        )
                    )
                    continue
                info.line_count = len(text.splitlines())
                source.append((rel, text))
                lines = text.splitlines()
                if len(lines) > 800:
                    info.reason_skipped = "Search chunks limited to first 800 lines"
                if ext == ".py":
                    symbols.extend(_python_symbols(text, rel))
                    _tree_sitter_parse(text)
                # Bounded, deterministic chunks; evidence retains exact line bounds.
                step = 80
                for offset in range(0, min(len(lines), 800), step):
                    block = "\n".join(lines[offset : offset + step])
                    chunks.append(
                        Chunk(
                            path=rel,
                            language=language,
                            start_line=offset + 1,
                            end_line=min(offset + step, len(lines)),
                            text=block[:12000],
                        )
                    )
                if len(chunks) >= 2000:
                    break
    except zipfile.BadZipFile as exc:
        raise AnalysisError("GitHub returned an invalid repository archive.") from exc
    python_sources = [(path, text) for path, text in source if path.endswith(".py")]
    findings, tools = _static_findings(python_sources)
    if len(python_sources) > 100:
        tools["static_analysis_scope"] = "First 100 Python files scanned; remaining files skipped."
        for path, text in python_sources[100:]:
            skipped.append(
                FileInfo(
                    path=path,
                    size=len(text.encode("utf-8")),
                    language="Python",
                    reason_skipped="Static analysis file limit reached",
                )
            )
    return AnalysisResult(
        id=str(uuid.uuid4()),
        owner=owner,
        name=name,
        url=canonical_url,
        commit_sha=commit_sha,
        default_branch=branch,
        analyzed_at=datetime.now(UTC),
        status="completed",
        file_count=len(files),
        total_bytes=total_bytes,
        languages=dict(languages),
        files=files,
        symbols=symbols[:15000],
        findings=findings[:5000],
        chunks=chunks[:2000],
        skipped=skipped[:5000],
        tool_versions={
            "python": os.sys.version.split()[0],
            "tree-sitter-python": "0.23.6",
            **tools,
        },
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def answer_question(analysis: AnalysisResult, question: str) -> dict:
    terms = {term.lower() for term in re.findall(r"[A-Za-z_][A-Za-z_0-9]{2,}", question)}
    scored: list[tuple[int, Chunk]] = []
    for chunk in analysis.chunks:
        haystack = f"{chunk.path} {chunk.text}".lower()
        score = sum(haystack.count(term) for term in terms)
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [chunk for _, chunk in scored[:5]]
    if not selected:
        return {
            "answer": "I could not find enough matching source evidence in this snapshot to answer confidently.",
            "citations": [],
            "mode": "lexical",
        }
    citations = [
        {
            "path": chunk.path,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "commit_sha": analysis.commit_sha,
        }
        for chunk in selected
    ]
    evidence = "\n".join(f"{c.path}:{c.start_line}-{c.end_line}" for c in selected)
    return {
        "answer": f"I found relevant code in {len(selected)} source section(s). Inspect {evidence}. This answer uses lexical retrieval; review the cited code before relying on an interpretation.",
        "citations": citations,
        "mode": "lexical",
    }
