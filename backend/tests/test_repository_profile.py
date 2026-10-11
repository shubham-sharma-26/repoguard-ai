from app.schemas import AnalysisResult, Chunk, FileInfo, Finding, Symbol
from app.services.repository_profile import build_profile, build_recommendations


def snapshot() -> AnalysisResult:
    files = [
        FileInfo(path="README.md", size=40, language="Markdown", line_count=2),
        FileInfo(path="package.json", size=80, language="JSON", line_count=5),
        FileInfo(path="src/app.ts", size=100, language="TypeScript", line_count=12),
        FileInfo(path="src/auth.ts", size=100, language="TypeScript", line_count=8),
        FileInfo(path="tests/auth.test.ts", size=50, language="TypeScript", line_count=4),
    ]
    return AnalysisResult(
        id="snap", owner="o", name="n", url="https://github.com/o/n", commit_sha="a" * 40,
        default_branch="main", analyzed_at="2026-01-01T00:00:00Z", status="completed",
        file_count=len(files), total_bytes=280, languages={"TypeScript": 3, "Markdown": 1, "JSON": 1},
        files=files,
        symbols=[
            Symbol(name="createApp", kind="function", path="src/app.ts", start_line=2, end_line=8, summary=""),
            Symbol(name="AuthService", kind="class", path="src/auth.ts", start_line=1, end_line=8, summary=""),
            Symbol(name="./auth", kind="import", path="src/app.ts", start_line=1, end_line=1, summary=""),
        ],
        findings=[Finding(severity="high", rule_id="B105", title="Possible hardcoded password", message="Review literal", path="src/auth.ts", line=5, end_line=5, source="Bandit")],
        chunks=[
            Chunk(path="README.md", language="Markdown", start_line=1, end_line=2, text="# A small account portal\nUsers can sign in and manage profiles."),
            Chunk(path="package.json", language="JSON", start_line=1, end_line=5, text='{"dependencies":{"react":"^19","express":"^5"}}'),
            Chunk(path="src/app.ts", language="TypeScript", start_line=1, end_line=12, text="import { AuthService } from './auth'; export function createApp() {}"),
            Chunk(path="src/auth.ts", language="TypeScript", start_line=1, end_line=8, text="export class AuthService { signIn() { return true; } }"),
            Chunk(path="tests/auth.test.ts", language="TypeScript", start_line=1, end_line=4, text="test('sign in', () => {});"),
        ], skipped=[], tool_versions={}, analysis_coverage={"TypeScript": "not_analyzed"}, duration_ms=1,
    )


def test_profile_extracts_documentation_stack_modules_and_relationships() -> None:
    profile = build_profile(snapshot())
    categories = {fact.category for fact in profile.facts}
    assert {"purpose", "stack", "module", "relationship", "testing", "limitation"} <= categories
    purpose = next(fact for fact in profile.facts if fact.category == "purpose")
    assert "account portal" in purpose.statement
    assert purpose.basis == "documented"
    assert profile.architecture_diagram and "graph TD" in profile.architecture_diagram


def test_recommendations_are_prioritized_and_cite_snapshot_locations() -> None:
    recs = build_recommendations(snapshot())
    assert any(r.category == "potential_risk" and r.priority == "P1" for r in recs)
    assert any(r.category == "missing_capability" and r.priority == "P2" for r in recs)
    for recommendation in recs:
        for evidence in recommendation.evidence:
            file = next(f for f in snapshot().files if f.path == evidence.path)
            assert 1 <= evidence.start_line <= evidence.end_line <= file.line_count
