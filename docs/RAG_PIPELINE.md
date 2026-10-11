# RepoGuard AI RAG pipeline

RepoGuard's Q&A uses a provider interface in `backend/app/services/rag.py`. Repository snapshots remain the source of truth. Each chunk and any embedding are stored within that analysis payload, alongside its repository ID, pinned commit, path, and line range. Retrieval receives one loaded `AnalysisResult`; it cannot search across other snapshots.

## Local mode

With `OPENAI_API_KEY` unset (the default), no AI provider requests are made. Q&A uses deterministic lexical matching and returns a clearly labeled extractive source excerpt with snapshot citations. If no terms match, it returns an insufficient-evidence response with no citations. This mode requires no API credential or network access.

## Optional OpenAI provider

To opt in, set `OPENAI_API_KEY` in the backend environment or a local, untracked `backend/.env`. `RAG_EMBEDDING_MODEL` defaults to `text-embedding-3-small`; `RAG_CHAT_MODEL` defaults to `gpt-4o-mini`. The provider origin is fixed to `https://api.openai.com/v1`; the shared pinned transport validates DNS answers and connects to those exact public IPs, redirects and environment proxies are disabled, TLS verification stays enabled, and the key is never logged.

When configured, repository analysis sends up to `RAG_EMBEDDING_MAX_CHUNKS` source chunks to the embedding endpoint in bounded batches. Chunk text is capped by `RAG_CHUNK_MAX_CHARS`, and each embedding's model and dimension are validated before storage. Snapshot status distinguishes ready, partial, empty, error, and not configured. If embedding fails or times out, analysis still completes and Q&A remains usable through lexical retrieval.

On a question, RepoGuard sends the question for an embedding only when matching snapshot vectors exist. Lexical and semantic rankings are merged with reciprocal-rank fusion. Retrieved evidence, repository name, pinned commit SHA, and the question are then sent to chat generation when configured. If generation fails, RepoGuard labels the result as an extractive fallback instead of presenting the failed generation as an AI answer. Provider rate limits, timeouts, malformed responses, and oversized responses are handled as provider errors without exposing raw provider bodies.

**Privacy:** configuring the API key opts in to external transmission of bounded source chunks during analysis and relevant excerpts plus the question during Q&A. Review repository contents and provider terms before enabling this. No provider is contacted by default. The analyzer only accepts public GitHub repositories, but public code can still contain sensitive material.

## Storage and retrieval

- SQLite keeps embeddings in each persisted analysis JSON payload; semantic retrieval uses cosine similarity within the loaded snapshot. Lexical retrieval remains available if no embeddings or provider are available.
- PostgreSQL uses an optional pgvector table when the server has the `vector` extension. On saving embedded results, the backend attempts `CREATE EXTENSION IF NOT EXISTS vector`, creates a dimension-specific table, a metadata index scoped by analysis ID/commit/model, and an HNSW cosine index when dimensions permit. If the extension or permissions are unavailable, the snapshot is still saved and retrieval falls back to the vectors in the snapshot payload (or lexical mode if no vectors exist).
- `AnalysisResult` JSON reports omit chunks and therefore omit embedding values. File preview responses also omit embeddings.

## Evidence and prompt-injection handling

Repository text is untrusted data. The system prompt says to ignore instructions inside retrieved content and answer only from supplied evidence. The model receives bounded, serialized evidence and is asked to cite numeric references from the retrieved set. The server discards citation IDs that were not supplied, then the API validates every remaining path against the snapshot manifest, checks the exact commit SHA, and enforces positive line ranges within the file's stored line count. Invalid generated citations cause an extractive fallback. This reduces unsupported references; it cannot guarantee that every generated sentence is correct, so inspect the cited source.

## Bounds and honest status

Defaults cap embedding batches at 32 chunks, embeddings at 256 chunks per snapshot, individual text at 8,000 characters, retrieval at five chunks, assembled context at 12,000 characters, provider HTTP calls at 12 seconds, each RAG async stage at 20 seconds, PostgreSQL connection and statement timeouts at 20 seconds, and provider response bodies at 2 MB (with an additional 8,000-character answer cap). These are per-stage bounds for Q&A; they are not a single end-to-end 20-second deadline. Settings have validation ranges in `backend/app/core/config.py`.

Answer responses expose retrieval mode (`lexical`, `semantic`, or `hybrid`), generation mode (`llm`, `extractive_fallback`, or `none`), provider status and safe provider message, and whether evidence met the lexical/similarity threshold. PostgreSQL/pgvector was not available in the local test environment; its SQL filters and optional fallback path are unit-tested, but a live PostgreSQL extension/index run remains unverified. Live GitHub access remains blocked by outbound TCP connectivity, independent of the RAG provider tests.

## Verification results

The backend suite passed **89 tests** with five upstream deprecation warnings; Ruff passed. Frontend Prettier, TypeScript, and the Vite production build passed. Embedding/chat requests were mocked, so no live provider credential or paid provider was used. The pgvector query was tested with a mocked PostgreSQL result, not a running PostgreSQL/pgvector server. Live GitHub ingestion remains unverified because pinned outbound TCP failed before TLS.

### Local integration verification update (2026-10-11)

The observed process environment had neither `OPENAI_API_KEY` nor `DATABASE_URL`, and no `backend/.env` file was present. The app's no-key mode therefore used lexical retrieval/extractive fallback with SQLite; a regression test verifies that this path does not construct an external provider. The controlled FastAPI fixture test passed answerable and unanswerable questions, citation validation, Markdown/JSON exports, and persistence after reopening an isolated SQLite file. This fixture is not a substitute for a live GitHub run.

The OpenAI key is the operator's explicit opt-in; there is no additional UI consent prompt. Set a non-empty `OPENAI_API_KEY` only after deciding to transmit bounded source chunks for embedding and retrieved excerpts plus the question for answer generation. This milestone made no live or billable provider requests. Provider timeouts, rate limits, malformed responses, response bounds, and embedding dimensions are verified with mocks.

The Alembic baseline migration passed on a fresh temporary SQLite database. Docker CLI was available but its daemon pipe was missing, `DATABASE_URL` was unset, and no PostgreSQL/pgvector service was used. The pgvector query filters remain mock-tested; actual extension creation, indexes, persistence, and vector retrieval are unverified. Final checks: **92 backend tests passed** with six warnings, Ruff passed, Prettier check passed, and TypeScript plus production build passed.

The later Milestone 17 audit added ZIP special-entry rejection and safer exception logging without changing the RAG provider path. Its final suite passed **97 tests** with five upstream deprecation warnings; Ruff, `pip check`, Prettier, TypeScript, and the production build passed. This does not change the external integration verification limits above.
