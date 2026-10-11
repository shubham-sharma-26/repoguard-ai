# RepoGuard AI RAG pipeline

RepoGuard's Q&A uses a provider interface in `backend/app/services/rag.py`. Repository snapshots remain the source of truth. Each chunk and any embedding are stored within that analysis payload, alongside its repository ID, pinned commit, path, and line range. Retrieval receives one loaded `AnalysisResult`; it cannot search across other snapshots.

## Local mode

With `RAG_PROVIDER=local` or with no provider key configured (the default), no AI provider requests are made. Q&A first answers exact snapshot facts (symbol locations, largest files, and saved findings), then uses deterministic ranked evidence from README/documentation lines, supported dependency manifests, file paths, extracted symbols and summaries, source chunks, and findings. Query intent expansion supports varied wording about project purpose, architecture, features, authentication, API/database integration, dependencies, security, and possible improvements. Documentation claims are attributed to the documentation; file-layout statements are identified as structural observations rather than complete runtime behavior. Findings remain potential tool reports, not confirmed vulnerabilities. Relevant citations are checked against files and line ranges in the selected analysis commit.

This local mode is a deterministic evidence-ranking and templating pipeline, not a local language model. It cannot reliably explain arbitrary runtime behavior or prove that an implementation works. If the snapshot lacks relevant documentation, symbols, manifests, or findings, the answer names missing evidence and suggests a narrower question. It does not turn an arbitrary retrieved code excerpt into an explanation. The mode requires no API credential or network access.

## Optional model providers

Provider selection is controlled by `RAG_PROVIDER`: `auto` (default) prefers Gemini when `GEMINI_API_KEY` is present, then OpenAI when `OPENAI_API_KEY` is present, and otherwise local mode. `local`, `gemini`, and `openai` force a mode. A configured provider failure or quota limit always falls back to local synthesis; RepoGuard does not switch to another remote provider after a failure. Provider name/readiness is returned without credentials and shown in the Q&A status badges.

### Gemini generation

Install the pinned official `google-genai` Python SDK through `backend/requirements.txt`. Set `GEMINI_API_KEY` in the backend process environment or `backend/.env`, select `RAG_PROVIDER=gemini`, and optionally change `GEMINI_MODEL`. The default is `gemini-3.1-flash-lite`. Google's current official [pricing page](https://ai.google.dev/gemini-api/docs/pricing) lists standard text input/output for this model as free tier, and the [model docs](https://ai.google.dev/gemini-api/docs/models) list it as supported. Quotas, regional availability, and free-tier eligibility may change; a configured Google Cloud billing account may permit charges after free quota limits. RepoGuard never enables billing and does not silently fall back to a paid model/provider. For a hard no-charge requirement, use a project without billing and monitor its API quota/usage. Do not send a real key in chat, source control, or frontend configuration.

Gemini is generation-only. It receives only the already retrieved, bounded, redacted excerpts and the question after retrieval from one pinned snapshot. The provider is configured with a request timeout, JSON response mode, deterministic temperature, and bounded output token/character limits. The model is prompted to ignore instructions in repository content. Its citation IDs are mapped only to retrieved evidence, then the API validates path, exact commit, and line bounds. Missing key, SDK initialization failure, quota, timeout, invalid output, or citation failure uses local fallback; it never triggers an OpenAI request automatically.

The free tier may use submitted prompts and outputs to improve Google's products, as stated by Google. Enabling Gemini therefore opts in to sending selected repository excerpts and the question to Google. Inspect repositories for secrets and review current provider terms before enabling. Secret-like values are redacted from model context, but detection is not exhaustive.

### Optional OpenAI provider

To opt in, set `RAG_PROVIDER=openai` and `OPENAI_API_KEY` in the backend environment or a local, untracked `backend/.env`. `RAG_EMBEDDING_MODEL` defaults to `text-embedding-3-small`; `RAG_CHAT_MODEL` defaults to `gpt-4o-mini`. The provider origin is fixed to `https://api.openai.com/v1`; the shared pinned transport validates DNS answers and connects to those exact public IPs, redirects and environment proxies are disabled, TLS verification stays enabled, and the key is never logged.

When configured, repository analysis sends up to `RAG_EMBEDDING_MAX_CHUNKS` source chunks to the embedding endpoint in bounded batches. Chunk text is capped by `RAG_CHUNK_MAX_CHARS`, and each embedding's model and dimension are validated before storage. Snapshot status distinguishes ready, partial, empty, error, and not configured. If embedding fails or times out, analysis still completes and Q&A remains usable through lexical retrieval.

On a question, RepoGuard answers supported snapshot-metadata questions locally without provider calls. For other questions, it sends the question for an embedding only when matching snapshot vectors exist. Lexical and semantic rankings are merged with reciprocal-rank fusion. Retrieved evidence, repository name, pinned commit SHA, and the question are then sent to chat generation when configured. The model is instructed to provide a concise explanation and not repeat source excerpts. If generation fails, RepoGuard invokes the same deterministic local evidence synthesis and reports uncertainty where the saved evidence does not support an answer. Provider rate limits, timeouts, malformed responses, and oversized responses are handled as provider errors without exposing raw provider bodies.

**Privacy:** configuring the API key opts in to external transmission of bounded source chunks during analysis and relevant excerpts plus the question during Q&A. Review repository contents and provider terms before enabling this. No provider is contacted by default. The analyzer only accepts public GitHub repositories, but public code can still contain sensitive material.

## Storage and retrieval

- SQLite keeps embeddings in each persisted analysis JSON payload; semantic retrieval uses cosine similarity within the loaded snapshot. Lexical retrieval remains available if no embeddings or provider are available.
- PostgreSQL uses an optional pgvector table when the server has the `vector` extension. On saving embedded results, the backend attempts `CREATE EXTENSION IF NOT EXISTS vector`, creates a dimension-specific table, a metadata index scoped by analysis ID/commit/model, and an HNSW cosine index when dimensions permit. If the extension or permissions are unavailable, the snapshot is still saved and retrieval falls back to the vectors in the snapshot payload (or lexical mode if no vectors exist).
- `AnalysisResult` JSON reports omit chunks and therefore omit embedding values. File preview responses also omit embeddings.

## Evidence and prompt-injection handling

Repository text is untrusted data. The system prompt says to ignore instructions inside retrieved content and answer only from supplied evidence. The model receives bounded, serialized evidence and is asked to cite numeric references from the retrieved set. Citation IDs must all be unique and refer to retrieved context; partial, fabricated, or malformed IDs invalidate the generated answer. The API validates every citation path against the selected snapshot manifest, checks the exact commit SHA, and enforces positive line ranges within the file's stored line count. Failed validation returns an uncertainty response with no unsupported answer text. This reduces unsupported references; it cannot guarantee that every generated sentence is correct, so inspect the cited source.

## Bounds and honest status

Defaults cap embedding batches at 32 chunks, embeddings at 256 chunks per snapshot, individual text at 8,000 characters, retrieval at five chunks, assembled context at 12,000 characters, provider HTTP calls at 12 seconds, each RAG async stage at 20 seconds, PostgreSQL connection and statement timeouts at 20 seconds, and provider response bodies at 2 MB (with an additional 8,000-character answer cap). These are per-stage bounds for Q&A; they are not a single end-to-end 20-second deadline. Settings have validation ranges in `backend/app/core/config.py`.

Answer responses expose retrieval mode (`lexical`, `semantic`, or `hybrid`), generation mode (`llm`, `local`, or `none`), provider name/status and safe provider message, and whether evidence met the lexical/similarity threshold. PostgreSQL/pgvector was not available in the local test environment; its SQL filters and optional fallback path are unit-tested, but a live PostgreSQL extension/index run remains unverified. Live Gemini and OpenAI calls are not made by automated tests; Gemini adapter behavior is verified with a mocked SDK surface.

## Verification results

### Repository profile and intent ranking

The analyzer persists a versioned `project_profile` on each `AnalysisResult`. It is synthesized only from the selected snapshot's file manifest, indexed chunks, extracted symbols/import statements, static findings, and language coverage. Facts carry a basis (`documented`, `observed`, `inferred`, or `tool_report`) and validated file/line evidence when present. The profile currently detects README purpose text, language/config manifests, conventional entry-point names, syntax-defined modules, resolvable syntactic import relationships, test/deployment/CI paths, selected API/database/security source patterns, and analyzer findings/coverage. These are bounded heuristics: they do not establish complete runtime flow, feature behavior, security effectiveness, or a full architecture graph. Import diagrams only show matching syntactic imports.

The analysis API lazily enriches older saved payloads with profile version 1 when they have no profile. Newly analyzed snapshots are enriched before persistence. Profile facts and improvement suggestions are included in JSON and Markdown reports. Suggestions from Bandit remain potential risks; Ruff reports are best-practice items; unscanned languages produce coverage recommendations. No automated recommendation claims a confirmed defect. Priority P0 is reserved for independently verified critical defects and is not assigned by these heuristics.

Lexical chunk ranking removes generic question terms, adds category-specific vocabulary/path signals for authentication, APIs, databases, testing, and static analysis, suppresses generic README chunks for unrelated implementation questions, and heavily discounts lockfiles. Optional semantic scores can still contribute when embeddings are configured. Local answer synthesis remains deterministic and evidence bounded; broad requests can still be uncertain where the snapshot lacks docs, useful symbols, or supported-language analysis. It is not a general semantic model.

### Broader local synthesis update (2026-10-11)

The suite passed **136 tests** with five upstream deprecation warnings; Ruff, `pip check`, Prettier, TypeScript validation, and the Vite production build passed. Tests exercise deterministic README, architecture, feature, symbol, dependency, findings, uncertainty, snapshot, provider-fallback, citation-validation, and credential-redaction paths. No live AI, GitHub, or PostgreSQL/pgvector integration was used for this update.

The backend suite passed **89 tests** with five upstream deprecation warnings; Ruff passed. Frontend Prettier, TypeScript, and the Vite production build passed. Embedding/chat requests were mocked, so no live provider credential or paid provider was used. The pgvector query was tested with a mocked PostgreSQL result, not a running PostgreSQL/pgvector server. Live GitHub ingestion remains unverified because pinned outbound TCP failed before TLS.

### Local integration verification update (2026-10-11)

The observed process environment had neither `OPENAI_API_KEY` nor `DATABASE_URL`, and no `backend/.env` file was present. The app's no-key mode therefore used local lexical retrieval and deterministic snapshot answers with SQLite; a regression test verifies that this path does not construct an external provider. The controlled FastAPI fixture test passed answerable and unanswerable questions, citation validation, Markdown/JSON exports, and persistence after reopening an isolated SQLite file. This fixture is not a substitute for a live GitHub run.

The OpenAI key is the operator's explicit opt-in; there is no additional UI consent prompt. Set a non-empty `OPENAI_API_KEY` only after deciding to transmit bounded source chunks for embedding and retrieved excerpts plus the question for answer generation. This milestone made no live or billable provider requests. Provider timeouts, rate limits, malformed responses, response bounds, and embedding dimensions are verified with mocks.

The Alembic baseline migration passed on a fresh temporary SQLite database. Docker CLI was available but its daemon pipe was missing, `DATABASE_URL` was unset, and no PostgreSQL/pgvector service was used. The pgvector query filters remain mock-tested; actual extension creation, indexes, persistence, and vector retrieval are unverified. Final checks: **92 backend tests passed** with six warnings, Ruff passed, Prettier check passed, and TypeScript plus production build passed.

The later Milestone 17 audit added ZIP special-entry rejection and safer exception logging without changing the RAG provider path. Its final suite passed **97 tests** with five upstream deprecation warnings; Ruff, `pip check`, Prettier, TypeScript, and the production build passed. This does not change the external integration verification limits above.
