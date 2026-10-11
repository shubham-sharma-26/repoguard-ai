# RepoGuard AI interview guide

This guide describes the implementation in this repository as it exists. The project has not been deployed publicly. Live GitHub ingestion, live OpenAI requests, and PostgreSQL/pgvector operation are unverified in the current environment.

## 60-second project explanation

RepoGuard AI is a local-first tool for understanding public GitHub repositories. It validates a repository URL, resolves and records a commit SHA, downloads that exact archive through a DNS-pinned HTTPS transport, and indexes bounded files without executing repository code. Python files get AST-based function, class, import, and top-level definition extraction; Ruff and Bandit run with time and output limits. The snapshot is stored in SQLite by default. Users can browse files and findings, ask source-grounded questions with lexical retrieval, and export Markdown or JSON reports. Optional embeddings and OpenAI generation use separate provider interfaces, but the no-key path stays local and gives an extractive answer or reports insufficient evidence. Citations are checked against the saved file manifest, commit, and line bounds.

## Architecture walkthrough

1. **UI and API:** `frontend/src/App.tsx` provides the workspace, snapshots, file previews, findings, Q&A, and report links. `frontend/src/types.ts` describes API data. Vite forwards `/api` to the loopback FastAPI server.
2. **HTTP layer:** `backend/app/main.py` validates request schemas, calls services, loads snapshots, validates Q&A citations, and returns reports. It does not implement archive parsing or ranking.
3. **Ingestion:** `backend/app/services/analyzer.py` validates supported GitHub URL forms, resolves the default branch to a commit SHA, reads bounded API/archive responses, rejects unsafe paths and non-regular ZIP entries, parses supported text, extracts Python symbols, builds chunks, and invokes local static tools.
4. **Outbound transport:** `backend/app/services/github_transport.py` resolves allowlisted hosts immediately before dialing, rejects unsafe answers, connects to a validated IP literal, retains the original host for TLS SNI/certificate verification and HTTP `Host`, ignores environment proxies, and disables idle connection reuse. Redirects are handled explicitly.
5. **Analysis and persistence:** Pydantic models describe snapshots. SQLAlchemy stores their JSON payload in `analysis_runs`; SQLite is the default. Optional PostgreSQL vector rows are scoped by analysis ID, commit, and embedding model.
6. **Q&A:** `backend/app/services/rag.py` ranks lexical evidence and optionally semantic vectors, bounds context, treats repository excerpts as untrusted, then uses a configured provider or deterministic extractive fallback. The HTTP layer independently validates source references.

```mermaid
sequenceDiagram
    participant U as User / React UI
    participant A as FastAPI
    participant G as Pinned GitHub transport
    participant P as Parser + Ruff/Bandit
    participant D as SQLite / optional PostgreSQL
    participant R as Retrieval / optional OpenAI
    U->>A: Submit public GitHub URL
    A->>G: Resolve metadata and pinned commit
    G-->>A: Bounded metadata and pinned archive
    A->>P: Parse bounded regular files
    P-->>A: Manifest, symbols, findings, chunks
    A->>D: Persist exact snapshot
    U->>A: Ask a repository question
    A->>D: Load one snapshot by ID
    A->>R: Retrieve bounded evidence; optional provider
    R-->>A: Answer and candidate citation IDs
    A->>A: Check path, commit SHA, and line bounds
    A-->>U: Answer and validated source references
```

## Design decisions and trade-offs

- **Modular monolith:** route handling, ingestion, retrieval, and persistence have clear boundaries without distributed-service overhead.
- **Commit-pinned snapshots:** branches move. Recording the resolved SHA ties the downloaded archive, saved data, and citations to one reproducible state.
- **Archive processing rather than execution:** repository content is parsed as data. The analyzer does not run package scripts, tests, builds, or binaries. This is safer but does not reveal runtime behavior.
- **Constrained transport:** connect to a validated IP while preserving hostname-based TLS checks. This addresses DNS rebinding at the application connection layer; it cannot control network-layer routing/NAT.
- **SQLite-first persistence:** core local use does not depend on Docker or PostgreSQL. pgvector is optional and must not be described as active in SQLite mode.
- **Provider interfaces and fallback:** tests do not need paid credentials or Internet. Configuring a non-empty provider key is the operator's opt-in to sending bounded source text externally.
- **Citations as references, not proof:** validation ensures a file and line range belong to the chosen snapshot. It does not prove an LLM's sentence is supported semantically.

## Security controls and limits

- GitHub destinations and HTTPS port are fixed; all DNS answers must be public and the connection uses a validated IP literal. TLS stays enabled, proxies and automatic redirects are disabled, and the archive redirect is validated separately.
- Archive bytes, metadata, entry counts, file sizes, accepted source bytes, scanner time/output, RAG chunks/context, and provider response bytes are bounded. ZIP symlinks and special files are skipped; traversal paths are rejected.
- Ruff and Bandit use fixed argument arrays and stdin, with no shell interpolation. Repository code is never executed.
- Provider failures avoid logging credentials or raw response bodies. Unexpected analysis errors log only the exception category, not untrusted exception text or traceback.
- Citations must match a manifest path, exact commit SHA, and valid positive line range. Retrieval uses one loaded snapshot.
- There is no authentication or multi-user isolation; keep the service on loopback. An operating-system DNS resolver call cannot be forcibly stopped once running in its worker. Network infrastructure can still block or reroute a public IP. Static analysis is not a complete security assessment.

## RAG and citation flow

The fallback retriever tokenizes the question and ranks chunks from one `AnalysisResult`. If matching snapshot vectors and a configured embedding provider are available, semantic ranking is combined with lexical ranks. OpenAI generation is optional. The prompt marks repository excerpts as untrusted evidence and asks for integer citation IDs from supplied chunks. The server maps IDs to known sources, then the API checks path, exact snapshot SHA, and line bounds. Provider failure or invalid IDs results in an explicit extractive fallback. No relevant evidence results in an insufficient-evidence answer without citations.

This is evidence-grounded retrieval, not guaranteed semantic verification. OpenAI has not been called live. PostgreSQL/pgvector has only mocked query-filter coverage, not a live database integration test.

## Testing strategy

- Unit tests cover URL validation, archive path and file-type checks, Python symbols, subprocess limits, provider errors/bounds, retrieval isolation, prompt-injection handling, and citation rejection.
- Transport tests use mocked DNS and controlled local TLS servers to check the actual dialed IP, Host header, TLS hostname behavior, redirects, timeouts, proxy isolation, and response limits.
- `test_fixture_workflow.py` uses FastAPI's test client and a deterministic snapshot with an isolated SQLite database. It verifies route workflow, previews, symbols, answerable and unanswerable Q&A, citations, reports, and persistence after database reopen. It does not contact GitHub.
- `test_migrations.py` upgrades and inspects a new temporary SQLite database, not the user's application database.
- Frontend checks use Prettier, TypeScript, and the Vite production build. No frontend lint or browser component-test script is configured.

Run from the repository root:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check app tests
Set-Location ..\frontend
npm.cmd exec -- prettier --check src
npm.cmd run build
```

## Honest answers to likely questions

- **Has live GitHub analysis been verified?** No. DNS resolved in the last connection audit, but the pinned TCP connection failed before TLS. Fixture workflow tests are controlled local data only.
- **Does semantic search always use pgvector?** No. SQLite can compare vectors stored in a snapshot when embeddings exist. PostgreSQL attempts pgvector when configured and available; current database query-filter coverage is mocked. The response's retrieval mode reports whether semantic evidence was used.
- **Does a missing key make the app unusable?** No. Analysis and Q&A work locally. Q&A uses lexical retrieval and an extractive snippet, or reports insufficient evidence.
- **Does a citation guarantee an answer is true?** No. It guarantees only that the path/range belongs to the loaded commit. The source still needs review.
- **Is this a security scanner?** It reports Ruff and Bandit output but is not comprehensive and cannot establish that a repository is secure.

## Five technical questions and answers

1. **How is DNS rebinding mitigated?** The transport resolves immediately before connection, rejects unsafe or mixed answer sets, then dials an approved IP literal. HTTPX still uses the original hostname for TLS SNI, certificate checks, and `Host`. Proxies, automatic redirects, and idle connection reuse are disabled. See `backend/app/services/github_transport.py`.
2. **Why record a commit SHA?** A branch may move. The SHA pins the archive and makes stored results and citations refer to one reproducible repository state.
3. **How do you ensure repository code is not run?** Files are read as bounded ZIP entries. Python is parsed with AST/Tree-sitter, and local Ruff/Bandit receive source over stdin with fixed arguments, timeouts, and output limits. Repository-provided commands are not invoked.
4. **How are LLM citations constrained?** The model sees bounded retrieved chunks and numeric references. Only supplied IDs are mapped back to known chunks, then the API checks manifest membership, commit, and line range. This constrains references, not semantic truth.
5. **What happens when AI is unavailable or fails?** Without a configured key, Q&A remains lexical with an extractive fallback. Provider errors are safely categorized; if no evidence matches, the app returns an insufficient-evidence answer with no citations.
