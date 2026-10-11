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
    generation_mode: str = "extractive_fallback"
    provider_status: str = "not_configured"
    provider_message: str = "AI provider is not configured."
    evidence_sufficient: bool = False
