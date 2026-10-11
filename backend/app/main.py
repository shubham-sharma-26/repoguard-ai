import html
import logging
from collections import Counter
from pathlib import PurePosixPath

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import get_settings
from app.database import get_analysis, list_analyses, save_analysis
from app.schemas import (
    AnalysisResult,
    AnalysisSummary,
    AnalysisView,
    AnalyzeRequest,
    Answer,
    QuestionRequest,
)
from app.services.analyzer import AnalysisError, analyze_repository
from app.services.rag import answer_question

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("repoguard")
settings = get_settings()
app = FastAPI(
    title="RepoGuard AI",
    version="1.0.0",
    description="Analyze public GitHub repositories using static tools and evidence-grounded retrieval.",
)


class _BodyLimitExceeded(Exception):
    pass


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])


@app.middleware("http")
async def security_headers(request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        received_bytes = 0
        original_receive = request.receive

        async def bounded_receive():
            nonlocal received_bytes
            message = await original_receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > 16_384:
                    raise _BodyLimitExceeded
            return message

        request._receive = bounded_receive
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > 16_384
            except ValueError:
                return JSONResponse({"detail": "Invalid request body size"}, status_code=400)
            if too_large:
                return JSONResponse({"detail": "Request body exceeds the 16 KB limit"}, status_code=413)
    try:
        response = await call_next(request)
    except _BodyLimitExceeded:
        return JSONResponse({"detail": "Request body exceeds the 16 KB limit"}, status_code=413)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "repoguard-api"}


@app.get("/api/readiness")
def readiness() -> dict:
    try:
        from app.database import engine

        with engine.connect():
            return {"status": "ready", "database": "connected"}
    except Exception as exc:
        logger.warning("Readiness database check failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Database is not ready") from exc


@app.post("/api/analyses", response_model=AnalysisSummary, status_code=201)
async def create_analysis(request: AnalyzeRequest) -> AnalysisSummary:
    try:
        result = await analyze_repository(request.url)
        save_analysis(result.model_dump(mode="json"))
        return _summary(result)
    except AnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.TimeoutException as exc:
        logger.warning("GitHub connection timed out (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=504,
            detail="The secure connection to GitHub timed out. Check outbound network access and try again.",
        ) from exc
    except httpx.ConnectError as exc:
        logger.warning("GitHub secure connection failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="Could not establish a secure connection to GitHub. Check DNS and outbound network access.",
        ) from exc
    except httpx.NetworkError as exc:
        logger.warning("GitHub network request failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="A network error interrupted GitHub analysis. Check outbound network access and retry.",
        ) from exc
    except Exception as exc:
        # Exception messages and tracebacks may contain untrusted request or provider
        # details. Keep client-facing diagnostics useful without logging those values.
        logger.error("Repository analysis failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="Analysis could not be completed. Check connectivity and try again.",
        ) from exc


@app.get("/api/analyses", response_model=list[AnalysisSummary])
def history(limit: int = Query(default=30, ge=1, le=100)) -> list[AnalysisSummary]:
    return [
        AnalysisSummary(
            id=item["id"],
            owner=item["owner"],
            name=item["name"],
            url=item["url"],
            commit_sha=item["commit_sha"],
            analyzed_at=item["analyzed_at"],
            status=item["status"],
            file_count=item["file_count"],
            findings_count=len(item["findings"]),
            symbol_count=len(item["symbols"]),
        )
        for item in list_analyses(limit)
    ]


def _summary(result: AnalysisResult) -> AnalysisSummary:
    return AnalysisSummary(
        id=result.id,
        owner=result.owner,
        name=result.name,
        url=result.url,
        commit_sha=result.commit_sha,
        analyzed_at=result.analyzed_at,
        status=result.status,
        file_count=result.file_count,
        findings_count=len(result.findings),
        symbol_count=len(result.symbols),
    )


def _load_or_404(analysis_id: str) -> AnalysisResult:
    payload = get_analysis(analysis_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    result = AnalysisResult.model_validate(payload)
    if result.project_profile.version < 1:
        from app.services.repository_profile import enrich_analysis

        result = enrich_analysis(result)
    return result


@app.get("/api/analyses/{analysis_id}", response_model=AnalysisView)
def analysis_detail(analysis_id: str) -> AnalysisView:
    return AnalysisView.model_validate(_load_or_404(analysis_id).model_dump())


@app.get("/api/analyses/{analysis_id}/files")
def file_tree(
    analysis_id: str, q: str = "", limit: int = Query(default=500, ge=1, le=2000)
) -> dict:
    result = _load_or_404(analysis_id)
    query = q.casefold()[:200]
    items = [item.model_dump() for item in result.files if query in item.path.casefold()][:limit]
    return {"items": items, "total": len(result.files), "returned": len(items)}


@app.get("/api/analyses/{analysis_id}/file-content")
def file_content(analysis_id: str, path: str = Query(min_length=1, max_length=500)) -> dict:
    result = _load_or_404(analysis_id)
    normalized = PurePosixPath(path)
    if normalized.is_absolute() or ".." in normalized.parts or "\\" in path:
        raise HTTPException(status_code=422, detail="The repository file path is invalid")
    file_info = next((item for item in result.files if item.path == path), None)
    if file_info is None:
        raise HTTPException(status_code=404, detail="File not found in this snapshot")
    excerpts = [
        chunk.model_dump(exclude={"embedding", "embedding_model"})
        for chunk in result.chunks
        if chunk.path == path
    ][:50]
    return {
        "path": path,
        "line_count": file_info.line_count,
        "chunks": excerpts,
        "truncated": bool(
            file_info.line_count
            and (not excerpts or excerpts[-1]["end_line"] < file_info.line_count)
        ),
    }


@app.get("/api/analyses/{analysis_id}/findings")
def findings(
    analysis_id: str,
    severity: str | None = None,
    source: str | None = None,
    rule: str | None = None,
    path: str | None = None,
) -> dict:
    result = _load_or_404(analysis_id)
    found = result.findings
    if severity:
        found = [f for f in found if f.severity.casefold() == severity.casefold()]
    if source:
        found = [f for f in found if f.source.casefold() == source.casefold()]
    if rule:
        found = [f for f in found if rule.casefold() in f.rule_id.casefold()]
    if path:
        found = [f for f in found if path.casefold() in f.path.casefold()]
    return {"items": found, "total": len(found)}


@app.post("/api/analyses/{analysis_id}/ask", response_model=Answer)
async def ask(analysis_id: str, request: QuestionRequest) -> Answer:
    result = _load_or_404(analysis_id)
    answer = await answer_question(result, request.question)
    # Citation paths and ranges are checked against the pinned manifest before returning.
    manifest = {file.path for file in result.files}
    validated = []
    citations = answer["citations"]
    for citation in citations:
        path = PurePosixPath(citation["path"])
        if path.is_absolute() or ".." in path.parts or citation["path"] not in manifest:
            continue
        file_data = next((file for file in result.files if file.path == citation["path"]), None)
        if (
            file_data
            and citation.get("commit_sha") == result.commit_sha
            and file_data.line_count is not None
            and citation["start_line"] > 0
            and citation["end_line"] >= citation["start_line"]
            and citation["end_line"] <= file_data.line_count
        ):
            validated.append(citation)
    if citations and len(validated) != len(citations):
        answer.update(
            {
                "answer": "I could not validate the retrieved citations against this snapshot, so I cannot provide a grounded answer.",
                "citations": [],
                "generation_mode": "none",
                "provider_status": "error",
                "provider_message": "Citation validation failed against the selected repository snapshot.",
                "evidence_sufficient": False,
            }
        )
    else:
        answer["citations"] = validated
    return Answer.model_validate(answer)


@app.get("/api/analyses/{analysis_id}/report.md")
def markdown_report(analysis_id: str) -> Response:
    result = _load_or_404(analysis_id)

    def escape_markdown(value: str) -> str:
        value = html.escape(value.replace("\r", " ").replace("\n", " "), quote=False)
        for character in ("\\", "`", "*", "_", "[", "]", "(", ")", "#", "+", "-", ".", "!", "|", ">"):
            value = value.replace(character, "\\" + character)
        return value

    severities = Counter(finding.severity.lower() for finding in result.findings)
    symbol_kinds = Counter(symbol.kind for symbol in result.symbols)
    rows = [
        f"# {escape_markdown(result.owner)}/{escape_markdown(result.name)} analysis",
        "",
        f"- URL: {result.url}",
        f"- Commit: `{result.commit_sha}`",
        f"- Default branch: `{escape_markdown(result.default_branch)}`",
        f"- Analyzed: {result.analyzed_at.isoformat()}",
        f"- Files in manifest: {result.file_count}",
        f"- Accepted file bytes: {result.total_bytes}",
        f"- Duration: {result.duration_ms} ms",
        "",
        "## Languages",
        "",
    ]
    rows.extend(f"- {name}: {count} files" for name, count in sorted(result.languages.items()))
    rows.extend(["", "## Structure", "", f"- Extracted symbols: {len(result.symbols)}"])
    rows.extend(f"- {kind.title()}: {count}" for kind, count in sorted(symbol_kinds.items()))
    rows.extend(["", "## Project overview", ""])
    if result.project_profile.facts:
        for fact in result.project_profile.facts[:60]:
            citations = ", ".join(
                f"`{escape_markdown(ref.path)}:{ref.start_line}-{ref.end_line}`"
                for ref in fact.evidence
            )
            suffix = f" Evidence: {citations}." if citations else ""
            rows.append(f"- **{escape_markdown(fact.category.replace('_', ' ').title())} ({fact.basis}):** {escape_markdown(fact.statement)}{suffix}")
    else:
        rows.append("No profile facts could be derived from this snapshot.")
    rows.extend(["", "## Recommended improvements", ""])
    if result.recommendations:
        for item in result.recommendations[:60]:
            refs = ", ".join(f"`{escape_markdown(ref.path)}:{ref.start_line}-{ref.end_line}`" for ref in item.evidence)
            suffix = f" Evidence: {refs}." if refs else ""
            rows.append(f"- **{item.priority} · {escape_markdown(item.title)}** ({item.category.replace('_', ' ')}): {escape_markdown(item.recommended_change)}{suffix}")
        rows.append("\nPriorities are review guidance; analyzer findings are not automatically confirmed defects or vulnerabilities.")
    else:
        rows.append("No code-specific recommendations were supported by the stored analyzer output.")
    rows.extend(["", "## Tool versions", ""])
    rows.extend(
        f"- {escape_markdown(tool)}: `{escape_markdown(version)}`"
        for tool, version in sorted(result.tool_versions.items())
    )
    rows.extend(["", "## Static analysis coverage", ""])
    rows.extend(
        f"- {escape_markdown(language)}: {escape_markdown(status.replace('_', ' '))}"
        for language, status in sorted(result.analysis_coverage.items())
    )
    rows.extend(["", "## Severity distribution", ""])
    if severities:
        rows.extend(f"- {escape_markdown(level.title())}: {count}" for level, count in sorted(severities.items()))
    else:
        rows.append("- No findings were reported.")
    rows.extend(["", "## Findings", ""])
    if not result.findings:
        rows.append(
            "No tool findings were reported. This does not establish that the code is vulnerability-free."
        )
    for finding in result.findings:
        location = escape_markdown(finding.path)
        if finding.line:
            location += f":{finding.line}"
        rows.append(
            f"- **{finding.severity.upper()} {escape_markdown(finding.rule_id)}** "
            f"`{location}` - {escape_markdown(finding.title)}: {escape_markdown(finding.message)} "
            f"(source: {escape_markdown(finding.source)})"
        )
        if finding.evidence:
            rows.extend(["", "  <details><summary>Evidence</summary>", "", "  <pre>"])
            rows.extend("  " + html.escape(line, quote=False) for line in finding.evidence[:2000].splitlines())
            rows.extend(["  </pre>", "  </details>"])
    rows.extend(["", "## Skipped or limited files", ""])
    if not result.skipped:
        rows.append("No files were recorded as skipped or limited.")
    for item in result.skipped[:1000]:
        rows.append(
            f"- `{escape_markdown(item.path)}` - {escape_markdown(item.reason_skipped or 'Skipped')}"
        )
    if len(result.skipped) > 1000:
        rows.append(f"- {len(result.skipped) - 1000} additional entries omitted from this Markdown report.")
    rows.extend(
        [
            "",
            "## Limitations",
            "",
            "Results are static analysis and lexical structure only. No repository code was executed. "
            "Q&A uses lexical retrieval without a configured LLM. Review source code and validate findings.",
            "",
        ]
    )
    return Response(
        "\n".join(rows),
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{result.owner}-{result.name}-report.md"'
        },
    )


@app.get("/api/analyses/{analysis_id}/report.json")
def json_report(analysis_id: str) -> Response:
    result = _load_or_404(analysis_id)
    return Response(
        result.model_dump_json(indent=2, exclude={"chunks"}),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{result.owner}-{result.name}-report.json"'
        },
    )
