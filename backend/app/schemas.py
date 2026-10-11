from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    url: str = Field(max_length=500)


class FileInfo(BaseModel):
    path: str
    size: int
    language: str
    line_count: int | None = None
    reason_skipped: str | None = None


class Symbol(BaseModel):
    name: str
    kind: Literal["function", "class", "method", "import", "definition"]
    path: str
    start_line: int
    end_line: int
    summary: str = ""


class Finding(BaseModel):
    severity: str
    rule_id: str
    title: str
    message: str
    path: str
    line: int | None = None
    end_line: int | None = None
    source: str
    evidence: str = ""
    status: str = "detected"


class Chunk(BaseModel):
    path: str
    language: str
    start_line: int
    end_line: int
    symbol: str | None = None
    text: str
    embedding: list[float] | None = None
    embedding_model: str | None = None


class ProfileEvidence(BaseModel):
    path: str
    start_line: int
    end_line: int


class ProfileFact(BaseModel):
    category: Literal[
        "purpose", "users", "feature", "stack", "entry_point", "module", "relationship",
        "api", "data", "testing", "ci", "deployment", "documentation", "security",
        "limitation", "unknown",
    ]
    statement: str
    basis: Literal["documented", "observed", "inferred", "tool_report", "unknown"]
    evidence: list[ProfileEvidence] = Field(default_factory=list)


class ProjectProfile(BaseModel):
    version: int = 0
    facts: list[ProfileFact] = Field(default_factory=list)
    architecture_diagram: str | None = None


class ImprovementRecommendation(BaseModel):
    priority: Literal["P0", "P1", "P2", "P3"]
    category: Literal["confirmed_defect", "potential_risk", "missing_capability", "best_practice"]
    title: str
    problem: str
    why_it_matters: str
    recommended_change: str
    verification: str
    evidence: list[ProfileEvidence] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    id: str
    owner: str
    name: str
    url: str
    commit_sha: str
    default_branch: str
    analyzed_at: datetime
    status: str
    file_count: int
    total_bytes: int
    languages: dict[str, int]
    files: list[FileInfo]
    symbols: list[Symbol]
    findings: list[Finding]
    chunks: list[Chunk]
    skipped: list[FileInfo]
    tool_versions: dict[str, str]
    analysis_coverage: dict[str, str] = Field(default_factory=dict)
    duration_ms: int
    embedding_status: str = "not_configured"
    project_profile: ProjectProfile = Field(default_factory=ProjectProfile)
    recommendations: list[ImprovementRecommendation] = Field(default_factory=list)


class AnalysisSummary(BaseModel):
    id: str
    owner: str
    name: str
    url: str
    commit_sha: str
    analyzed_at: datetime
    status: str
    file_count: int
    findings_count: int
    symbol_count: int


class AnalysisView(BaseModel):
    id: str
    owner: str
    name: str
    url: str
    commit_sha: str
    default_branch: str
    analyzed_at: datetime
    status: str
    file_count: int
    total_bytes: int
    languages: dict[str, int]
    files: list[FileInfo]
    symbols: list[Symbol]
    findings: list[Finding]
    skipped: list[FileInfo]
    tool_versions: dict[str, str]
    analysis_coverage: dict[str, str] = Field(default_factory=dict)
    duration_ms: int
    embedding_status: str = "not_configured"
    project_profile: ProjectProfile = Field(default_factory=ProjectProfile)
    recommendations: list[ImprovementRecommendation] = Field(default_factory=list)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class Citation(BaseModel):
    path: str
    start_line: int
    end_line: int
    commit_sha: str


class Answer(BaseModel):
    answer: str
    citations: list[Citation]
    mode: str = "lexical"
    retrieval_mode: str = "lexical"
    generation_mode: str = "local"
    provider_status: str = "not_configured"
    provider_name: Literal["gemini", "openai", "local", "custom"] = "local"
    provider_message: str = "AI provider is not configured."
    evidence_sufficient: bool = False
