from __future__ import annotations

from types import SimpleNamespace

import anyio
import pytest

from app.core.config import Settings
from app.schemas import AnalysisResult, Chunk, FileInfo
from app.services.rag import (
    GeminiProvider,
    ProviderError,
    ProviderRateLimit,
    ProviderTimeout,
    answer_question,
    configured_llm_provider,
    selected_provider_name,
)


def _settings(**updates) -> Settings:
    values = {"openai_api_key": None, "gemini_api_key": None}
    values.update(updates)
    return Settings(_env_file=None, **values)


def _analysis() -> AnalysisResult:
    text = "def verify_token(token):\n    return token == 'accepted'\n"
    return AnalysisResult(
        id="analysis-gemini", owner="sample", name="repo",
        url="https://github.com/sample/repo", commit_sha="c" * 40,
        default_branch="main", analyzed_at="2026-01-01T00:00:00Z", status="completed",
        file_count=1, total_bytes=len(text), languages={"Python": 1},
        files=[FileInfo(path="src/auth.py", size=len(text), language="Python", line_count=2)],
        symbols=[], findings=[], chunks=[Chunk(
            path="src/auth.py", language="Python", start_line=1, end_line=2, text=text,
        )], skipped=[], tool_versions={}, duration_ms=1,
    )


def _adapter(response_text="{\"answer\":\"It compares a token to the accepted value.\",\"citations\":[1]}") -> GeminiProvider:
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.model = "gemini-test"
    provider.timeout = 2
    provider.max_output_chars = 8000
    provider.requests = []

    def generate_content(**kwargs):
        provider.requests.append(kwargs)
        return SimpleNamespace(text=response_text)

    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    provider._types = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)
    return provider


def test_gemini_sdk_adapter_generates_bounded_json_request() -> None:
    provider = _adapter()
    result = anyio.run(provider.generate, "Only use evidence.", "question and evidence")
    assert '"citations":[1]' in result
    request = provider.requests[0]
    assert request["model"] == "gemini-test"
    assert request["contents"] == "question and evidence"
    assert request["config"]["system_instruction"] == "Only use evidence."
    assert request["config"]["response_mime_type"] == "application/json"
    assert request["config"]["max_output_tokens"] == 900


def test_gemini_adapter_rejects_empty_or_oversized_response() -> None:
    empty = _adapter("")
    with pytest.raises(ProviderError, match="empty or oversized"):
        anyio.run(empty.generate, "system", "user")
    huge = _adapter("x" * 8001)
    with pytest.raises(ProviderError, match="empty or oversized"):
        anyio.run(huge.generate, "system", "user")


def test_gemini_adapter_maps_rate_limit_and_timeout_without_leaking_error() -> None:
    class QuotaError(Exception):
        code = 429

    provider = _adapter()
    provider._client.models.generate_content = lambda **kwargs: (_ for _ in ()).throw(QuotaError("secret details"))
    with pytest.raises(ProviderRateLimit, match="rate limit"):
        anyio.run(provider.generate, "system", "user")

    class NetworkTimeout(Exception):
        pass

    provider = _adapter()
    provider._client.models.generate_content = lambda **kwargs: (_ for _ in ()).throw(NetworkTimeout("secret timeout"))
    with pytest.raises(ProviderTimeout, match="timed out"):
        anyio.run(provider.generate, "system", "user")


def test_missing_gemini_key_keeps_local_provider_fallback() -> None:
    config = _settings(rag_provider="gemini")
    assert selected_provider_name(config) == "gemini"
    assert configured_llm_provider(config) is None
    result = anyio.run(lambda: answer_question(_analysis(), "Explain what verify_token does", settings=config))
    assert result["generation_mode"] == "local"
    assert result["provider_status"] == "not_configured"
    assert result["provider_name"] == "gemini"
    assert "Gemini API key is missing" in result["provider_message"]


def test_auto_selection_prefers_configured_gemini_without_paid_provider_failover() -> None:
    config = _settings(
        rag_provider="auto", gemini_api_key="mock-gemini-key", openai_api_key="mock-openai-key"
    )
    assert selected_provider_name(config) == "gemini"
    # Selecting Gemini must not create an OpenAI embedding client either.
    from app.services.rag import configured_provider

    assert configured_provider(config) is None


def test_gemini_answer_uses_retrieved_snapshot_citation() -> None:
    provider = _adapter()
    result = anyio.run(lambda: answer_question(
        _analysis(), "Explain what verify_token does", provider=provider, settings=_settings()
    ))
    assert result["generation_mode"] == "llm"
    assert result["provider_name"] == "custom"
    assert result["citations"] == [{
        "index": 1, "path": "src/auth.py", "start_line": 1, "end_line": 2,
        "commit_sha": "c" * 40,
    }]


def test_gemini_quota_error_falls_back_to_local_with_validated_citation() -> None:
    class QuotaProvider:
        async def generate(self, system_prompt: str, user_prompt: str) -> str:
            raise ProviderRateLimit("provider response must not be exposed")

    result = anyio.run(lambda: answer_question(
        _analysis(), "Explain what verify_token does", provider=QuotaProvider(), settings=_settings()
    ))
    assert result["generation_mode"] == "local"
    assert result["provider_status"] == "error"
    assert "provider response must not be exposed" not in result["provider_message"]
    assert result["citations"][0]["path"] == "src/auth.py"
    assert result["citations"][0]["commit_sha"] == "c" * 40


def test_gemini_fabricated_citation_is_rejected_and_uses_local_evidence() -> None:
    provider = _adapter('{"answer":"Unsupported claim.","citations":[99]}')
    result = anyio.run(lambda: answer_question(
        _analysis(), "Explain what verify_token does", provider=provider, settings=_settings()
    ))
    assert result["generation_mode"] == "local"
    assert result["provider_status"] == "error"
    assert result["citations"][0]["path"] == "src/auth.py"
