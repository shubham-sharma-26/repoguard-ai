"""Evidence-only repository profile synthesis for an analyzed snapshot."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import PurePosixPath

from app.schemas import (
    AnalysisResult,
    ImprovementRecommendation,
    ProfileEvidence,
    ProfileFact,
    ProjectProfile,
)

_DOCS = {"readme", "overview", "architecture", "contributing"}
_MANIFESTS = {
    "pyproject.toml", "requirements.txt", "package.json", "cargo.toml",
    "go.mod", "pom.xml", "build.gradle", "composer.json",
}


def _evidence(path: str, start: int = 1, end: int | None = None) -> ProfileEvidence:
    return ProfileEvidence(path=path, start_line=start, end_line=max(start, end or start))


def build_profile(result: AnalysisResult) -> ProjectProfile:
    """Describe only facts supported by stored files, symbols, or tool output."""
    facts: list[ProfileFact] = []
    by_path: dict[str, list] = defaultdict(list)
    for symbol in result.symbols:
        by_path[symbol.path].append(symbol)
    file_map = {file.path: file for file in result.files}
    docs = [f for f in result.files if any(
        token in f.path.casefold().split("/")[-1].split(".")[0] for token in _DOCS
    )]

    for doc in docs:
        chunks = [c for c in result.chunks if c.path == doc.path]
        if chunks:
            excerpt = " ".join(c.text.strip() for c in chunks[:2]).splitlines()
            lines = [re.sub(r"^\s{0,3}#{1,6}\s*", "", line).strip() for line in excerpt]
            useful = next((line for line in lines if len(line) > 12 and not line.startswith(("[", "```"))), None)
            if useful:
                facts.append(ProfileFact(category="purpose", statement=useful[:320], basis="documented",
                    evidence=[_evidence(doc.path, chunks[0].start_line, chunks[min(1, len(chunks)-1)].end_line)]))
                break

    if result.languages:
        summary = ", ".join(f"{name} ({count} files)" for name, count in sorted(result.languages.items(), key=lambda x: -x[1])[:8])
        facts.append(ProfileFact(category="stack", statement=f"Detected languages: {summary}.", basis="observed"))
    for f in result.files:
        basename = f.path.rsplit("/", 1)[-1].casefold()
        if basename in _MANIFESTS:
            chunks = [c for c in result.chunks if c.path == f.path]
            if chunks:
                facts.append(ProfileFact(category="stack", statement=f"Dependency/configuration manifest: {f.path}.", basis="observed",
                    evidence=[_evidence(f.path, chunks[0].start_line, chunks[0].end_line)]))
        lower = f.path.casefold()
        if any(part in lower.split("/") for part in ("test", "tests", "__tests__")) or basename.startswith(("test_", "*.test.", "*.spec.")):
            facts.append(ProfileFact(category="testing", statement=f"Test-related file detected: {f.path}.", basis="observed",
                evidence=[_evidence(f.path, 1, f.line_count or 1)]))
        if basename in {"dockerfile", "docker-compose.yml", "compose.yml"}:
            facts.append(ProfileFact(category="deployment", statement=f"Deployment/container configuration detected: {f.path}.", basis="observed",
                evidence=[_evidence(f.path, 1, f.line_count or 1)]))
        if basename in {".github/workflows"} or ".github/workflows/" in lower:
            facts.append(ProfileFact(category="ci", statement=f"CI workflow detected: {f.path}.", basis="observed",
                evidence=[_evidence(f.path, 1, f.line_count or 1)]))

    entry_patterns = re.compile(r"(^|/)(main|app|server|index|__main__)\.(py|js|jsx|ts|tsx)$", re.I)
    for f in result.files:
        if entry_patterns.search(f.path):
            syms = by_path.get(f.path, [])
            end = max((s.end_line for s in syms), default=f.line_count or 1)
            facts.append(ProfileFact(category="entry_point", statement=f"Conventional entry-point file detected: {f.path}.", basis="inferred",
                evidence=[_evidence(f.path, 1, end)]))

    for path, syms in by_path.items():
        definitions = [s for s in syms if s.kind in {"class", "function", "method"}]
        if definitions:
            names = ", ".join(s.name for s in definitions[:8])
            facts.append(ProfileFact(category="module", statement=f"{path} defines {names}{'…' if len(definitions)>8 else ''}.", basis="observed",
                evidence=[_evidence(path, min(s.start_line for s in definitions), max(s.end_line for s in definitions))]))

    for chunk in result.chunks:
        lower_path = chunk.path.casefold()
        lines = chunk.text.splitlines()
        for offset, line in enumerate(lines):
            line_number = chunk.start_line + offset
            stripped = line.strip()
            if re.search(r"@(?:app|router)\.(?:get|post|put|patch|delete|api_route)\s*\(|\b(?:router|app)\.(?:get|post|put|patch|delete)\s*\(", stripped):
                facts.append(ProfileFact(category="api", statement=f"Route declaration detected in {chunk.path}: {stripped[:180]}", basis="observed",
                    evidence=[_evidence(chunk.path, line_number)]))
            if re.search(r"\b(?:from|import)\s+(?:sqlalchemy|psycopg|sqlite3|prisma|mongoose|typeorm|knex)\b|\b(?:create_engine|mongoose\.connect|PrismaClient)\b", stripped, re.I):
                facts.append(ProfileFact(category="data", statement=f"Database-related dependency or connection reference detected in {chunk.path}.", basis="observed",
                    evidence=[_evidence(chunk.path, line_number)]))
            if re.search(r"\b(?:password_context|bcrypt|argon2|verify_password|csrf|escape|httpOnly|httponly|rate_limit|Depends\(.*get_current_user)\b", stripped, re.I):
                facts.append(ProfileFact(category="security", statement=f"Security-related code construct detected in {chunk.path}; this does not establish that the control is complete or correctly configured.", basis="observed",
                    evidence=[_evidence(chunk.path, line_number)]))
            if lower_path.rsplit("/", 1)[-1].startswith("readme") and re.match(r"^\s{0,3}#{1,4}\s+", line):
                heading = re.sub(r"^\s{0,3}#{1,4}\s+", "", line).strip()
                if re.search(r"feature|capabilit|workflow|what it does", heading, re.I):
                    facts.append(ProfileFact(category="feature", statement=f"Documentation has a feature section titled “{heading[:120]}”. Specific behavior should be checked against implementation evidence.", basis="documented",
                        evidence=[_evidence(chunk.path, line_number)]))

    # Module relationships are reported only when a stored import names a known file/module.
    known = {p.rsplit(".", 1)[0].replace("/", ".") for p in file_map}
    edges: list[tuple[str, str]] = []
    for symbol in result.symbols:
        if symbol.kind != "import":
            continue
        target = symbol.name.replace("\\", "/").removesuffix(".py")
        if target.startswith(("./", "../")):
            parent = PurePosixPath(symbol.path).parent
            target_path = str((parent / target).as_posix())
            parts = []
            for part in target_path.split("/"):
                if part == "..":
                    if parts:
                        parts.pop()
                elif part != ".":
                    parts.append(part)
            target = ".".join(parts)
        else:
            target = target.replace("/", ".")
        match = next((m for m in known if target == m or target.endswith("." + m) or m.endswith("." + target)), None)
        if match:
            source = symbol.path.rsplit(".", 1)[0].replace("/", ".")
            facts.append(ProfileFact(category="relationship", statement=f"{source} imports {match}.", basis="observed",
                evidence=[_evidence(symbol.path, symbol.start_line, symbol.end_line)]))
            edges.append((source, match))

    for finding in result.findings[:200]:
        facts.append(ProfileFact(category="security" if finding.source.casefold() == "bandit" else "limitation",
            statement=f"{finding.source} reported {finding.rule_id}: {finding.title} ({finding.severity}).",
            basis="tool_report", evidence=[_evidence(finding.path, finding.line or 1, finding.end_line or finding.line or 1)]))
    for path, coverage in result.analysis_coverage.items():
        facts.append(ProfileFact(category="limitation", statement=f"Analysis coverage: {path}: {coverage}", basis="tool_report"))

    diagram = None
    if edges:
        labels = sorted({name for edge in edges for name in edge})[:18]
        ids = {name: f"m{i}" for i, name in enumerate(labels)}
        def safe(value: str) -> str:
            return re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:80]

        rows = ["graph TD"] + [f"  {ids[a]}[\"{safe(a)}\"] --> {ids[b]}[\"{safe(b)}\"]" for a, b in edges[:30] if a in ids and b in ids]
        diagram = "\n".join(rows)
    return ProjectProfile(version=1, facts=facts[:500], architecture_diagram=diagram)


def build_recommendations(result: AnalysisResult) -> list[ImprovementRecommendation]:
    """Produce evidence-linked review suggestions, never auto-confirm defects."""
    recommendations: list[ImprovementRecommendation] = []
    for finding in result.findings[:100]:
        bandit = finding.source.casefold() == "bandit"
        severity = finding.severity.casefold()
        priority = "P1" if severity in {"high", "error", "critical"} else "P2" if severity in {"medium", "warning"} else "P3"
        recommendations.append(ImprovementRecommendation(
            priority=priority,
            category="potential_risk" if bandit else "best_practice",
            title=finding.title,
            problem=f"{finding.source} reported {finding.rule_id}: {finding.message}",
            why_it_matters="This tool report merits human review; it is not by itself confirmation of a vulnerability or defect.",
            recommended_change=finding.message,
            verification=f"Review {finding.source} rule {finding.rule_id} against the cited code and rerun analysis after any change.",
            evidence=[_evidence(finding.path, finding.line or 1, finding.end_line or finding.line or 1)],
        ))
    for language, status in result.analysis_coverage.items():
        if status in {"not_analyzed", "partially_analyzed"}:
            source = next((f for f in result.files if f.language.casefold() == language.casefold()), None)
            recommendations.append(ImprovementRecommendation(
                priority="P2",
                category="missing_capability",
                title=f"Extend static analysis coverage for {language}",
                problem=f"The saved analysis reports {language} as {status.replace('_', ' ')}.",
                why_it_matters="Findings cannot be interpreted as a clean bill of health for language content that was not scanned.",
                recommended_change=f"Add a suitable non-executing static analyzer for {language} and normalize its output.",
                verification="Add a controlled fixture with a known rule result and confirm the analyzer reports its exact file and line.",
                evidence=[_evidence(source.path, 1, source.line_count or 1)] if source else [],
            ))
    return recommendations[:100]


def enrich_analysis(result: AnalysisResult) -> AnalysisResult:
    return result.model_copy(update={
        "project_profile": build_profile(result),
        "recommendations": build_recommendations(result),
    })
