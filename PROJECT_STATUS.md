# Project status

Updated: 2026-10-11

## Repository Q&A answer quality update

- Replaced raw-source fallback responses with deterministic, question-aware answers built from the selected snapshot's symbols, file line counts, and persisted findings. Questions outside these local fact types receive a cited uncertainty response; raw retrieved source is shown only in the separate source preview.
- Kept optional OpenAI generation and embedding behind the existing provider interface. The provider prompt now explicitly requests concise explanations instead of source excerpts. Invalid, partial, duplicated, or fabricated citation IDs cause local uncertainty fallback.
- The API revalidates citation paths, exact commit identity, and source line bounds. The Q&A panel renders paragraphs/lists, separate supporting-source links, a loading state, and a visible insufficient-evidence state.
- Added regressions for structure locations, largest source files by line count, static-analysis findings, unanswerable and provider-error cases, provider-disabled behavior, invalid citations, and snapshot isolation.
- Verification for this update: **120 backend tests passed** (five upstream deprecation warnings); Ruff and `pip check` passed; Prettier, TypeScript, and the Vite production build passed. Providers were mock-tested only; no live AI API calls were made.

## Broader local Q&A evidence synthesis

- Added deterministic evidence ranking over README/documentation lines, dependency manifests, file paths, extracted symbols and summaries, indexed source chunks, and persisted findings. Intent vocabulary expands varied wording for purpose, architecture, features, authentication, APIs/databases, dependencies, security, and improvements.
- Local answers attribute claims to project documentation or extracted records, distinguish structural observations from complete runtime behavior, report findings as potential issues, and name missing evidence when the snapshot is insufficient. Requirements and `pyproject.toml` / `package.json` dependency metadata are read without executing repository files.
- Supporting paths and ranges are validated against the supplied analysis snapshot and commit. The approach is deterministic retrieval and templates, not a local LLM; complex behavior explanations remain uncertain unless the optional provider is configured.
- New fixture tests cover purpose, architecture, features, auth/API implementation locations, dependency manifests, security wording, insufficient evidence, invalid citations, credential redaction, and broad-answer snapshot isolation. Verification: **136 backend tests passed** with five upstream deprecation warnings; Ruff and `pip check` passed; Prettier, TypeScript, and the production build passed. AI provider calls were mocked; no live GitHub, OpenAI, or PostgreSQL integration was exercised for this update.

## JavaScript/TypeScript structure and coverage update

- Added syntax-only Tree-sitter extraction for JavaScript, JSX, TypeScript, and TSX functions, classes, methods, and imports. Existing Python AST extraction remains in place. Unsupported or malformed syntax yields no symbols without evaluating source.
- Exposed static-analysis coverage to API consumers, the dashboard, and Markdown reports. Ruff/Bandit still analyze Python only; JavaScript/TypeScript explicitly report `not_analyzed` because no suitable JS/TS scanner is configured in the backend deployment. Zero findings must not be read as a JS/TS clean bill of health.
- Added JS/TS fixtures and tests for import/function/class/method extraction, line ranges, malformed and unsupported files, Python regression behavior, snapshot-scoped Q&A, and citation path/range rejection.
- Verification: **112 backend tests passed** (five upstream deprecation warnings); Ruff and `pip check` passed; Prettier check and TypeScript/Vite production build passed. A live public analysis of `pallets/itsdangerous` at `672971d66a2ef9f85151e53283113f33d642dabd` processed 50 files, extracted 296 symbols, and reported 82 Python findings. Its snapshot contained no JavaScript/TypeScript files. No AI key was configured, so no provider call was made.

## Completed

- Initialized Git in the previously empty workspace.
- Implemented a React/TypeScript/Vite dashboard.
- Added clickable repository file navigation with bounded source excerpts from the pinned snapshot.
- Implemented FastAPI health/readiness, repository analysis, compact snapshot history, files, filtered findings, Q&A, and escaped Markdown/JSON reports.
- Added GitHub URL validation, commit pinning, constrained API/archive access, bounded ZIP processing, Python AST symbols, lexical chunks/retrieval, and Ruff/Bandit integration.
- Added SQLAlchemy persistence (SQLite default; PostgreSQL configurable), Alembic migration, Docker Compose, CI, security docs, and regression tests.
- Implemented optional provider-backed embeddings and OpenAI chat generation with deterministic local answers for indexed facts, uncertainty for unsupported local questions, citation validation, hybrid retrieval, and frontend retrieval/provider status.
- Added `PinnedGitHubTransport` for DNS-answer validation and IP-literal socket connections to the two fixed GitHub service hosts; API and archive traffic bypass environment proxies, redirects are manually constrained, TLS verification remains enabled, and connections are not reused.
- Tightened repository URL parsing to reject query strings, fragments, and ambiguous repeated path separators. Bounded GitHub metadata JSON responses to 1 MB.
- Bound Docker Compose published ports to loopback.

## Environment observed

- Python 3.13.7, pip 25.3, Node.js 24.11.1, npm 11.6.2, Git 2.50.1, Docker CLI 28.4.0 / Compose 2.39.4.
- PowerShell blocks `npm.ps1`; `npm.cmd` works.
- Docker daemon is not accessible in this session. No provider keys were present in inspected environment variable names.

## Verification

- Backend runtime: `..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` started; `/api/health` and `/api/readiness` both returned HTTP 200. The SQLite readiness check connected.
- Frontend runtime: `npm.cmd run dev -- --host 127.0.0.1 --port 5173` reported Vite ready; `/` and the browser-facing `/api/health` proxy both returned HTTP 200.
- Backend: `..\.venv\Scripts\python.exe -m pytest -q` passed (71 tests); `..\.venv\Scripts\python.exe -m ruff check app tests` and `..\.venv\Scripts\python.exe -m pip check` passed. Five upstream deprecation warnings remain (Starlette/AnyIO, Bandit option, and Python AST API).
- Transport regression suite: `..\.venv\Scripts\python.exe -m pytest -q tests\test_github_transport.py` passed (43 tests). Coverage includes public/private/mixed/IPv4/IPv6 DNS, changed answers, proving prohibited answers cause zero dial attempts, actual IPv4 and IPv6 connector IP selection with local TLS routing, TLS SNI/hostname and HTTP Host verification, blocked host/scheme/port and archive redirects, proxy/pool behavior, DNS and read timeouts, and metadata/archive size caps.
- Frontend: `npm.cmd exec -- prettier --check src` passed; `npm.cmd run build` passed TypeScript and Vite production build. There is no configured frontend lint script, so no frontend lint command was run.
- A controlled API fixture test covered submission, detail/statistics, file tree and preview, symbol ranges, Q&A citations and an unanswerable question, Markdown/JSON reports, and persistence after reopening an isolated SQLite database.
- Live GitHub ingestion was retried through `POST /api/analyses` for `https://github.com/pallets/itsdangerous`; the actual pinned connection to `api.github.com` failed with `httpcore.ConnectError: All connection attempts failed`, returned as generic HTTP 502. No real repository was analyzed, so commit resolution, live counts, and real Ruff/Bandit findings remain unverified.
- `docker compose config --quiet` passed without starting containers, but Docker CLI warned that local Docker configuration access was denied. `docker info` confirmed the engine pipe is unavailable, so no container was started. Local SQLite workflow was used.
- Previous implementation checks recorded `alembic upgrade head` on a fresh SQLite database and `docker compose config --quiet`; they were not rerun during this runtime audit.

## Runtime audit findings

- DNS rebinding protection is implemented in `backend/app/services/github_transport.py`: connection-time DNS lookup, reject-all on any prohibited answer, connect to an approved IP literal, preserve origin hostname for TLS SNI/certificate checks and `Host`, disable proxies and idle pooling, restrict scheme/host/port, and cap API JSON responses. There is no automatic redirect following.
- Codeload is contacted only after `_validate_archive_redirect` verifies the exact expected owner/repository/commit archive path; that request uses a separate pinned transport without GitHub authorization.
- Added 43 focused network-transport regression cases. Their loopback TLS server uses a test-only private certificate/key accepted only by that test's explicitly trusted test client context; the application retains normal certificate verification.
- Fixed citation validation to reject a citation whose commit SHA differs from the loaded snapshot. Added `test_ask_drops_citations_from_another_commit`.
- Added an isolated controlled-fixture workflow regression test; it does not write test records into the user's application database.
- The live application API returns a concise 502 for outbound GitHub connection failure. The server log includes an exception traceback but does not log request body, source, authorization header, or token.
- No application-specific URLs are configured in frontend source; Vite's `/api` proxy returned the backend health JSON successfully.

## Follow-up live connectivity diagnosis (2026-10-11)

- Submitted `https://github.com/pallets/itsdangerous` through the running local API. It returned HTTP 502; no analysis was saved.
- DNS lookup succeeded for both `api.github.com` and `codeload.github.com`, with IPv4 answers only in this environment. The application's `PinnedGitHubTransport` rejected no DNS answers; its direct TCP attempts to the validated IPv4 addresses failed with `httpcore.ConnectError: All connection attempts failed` for both hosts.
- Therefore the observed failure is before TLS negotiation. This live attempt does not establish whether the environment would trust GitHub's TLS certificate; controlled transport tests separately cover TLS hostname verification. The evidence points to outbound network reachability or policy, not a demonstrated pinning or TLS defect. It does not identify which local/network policy blocks the connection.
- Transport logs now distinguish DNS lookup/policy rejection, pinned IPv4/IPv6 TCP failure/success, and TLS handshake/certificate verification failure/success. Logs include only stage and exception class (and a bounded TCP diagnostic), not headers, tokens, repository contents, or environment values.
- Reverification after the diagnostic change: backend tests passed (74); `ruff check app tests` passed; frontend `prettier --check src` passed; `npm run build` passed TypeScript and Vite production build. No frontend lint script is configured.
- Live GitHub ingestion remains unavailable and unverified in this environment. A successful controlled fixture or test TLS server is not evidence of live GitHub access.

## Milestone 15 — optional AI RAG (2026-10-11)

- Added separate embedding and LLM provider protocols and an OpenAI implementation using a fixed HTTPS API origin and the existing DNS-pinned transport, with TLS verification, disabled redirects/proxies, response-size caps, and safe error categories. No API key is required by tests or by the local lexical workflow.
- With `OPENAI_API_KEY` configured, analysis embeds at most 256 bounded source chunks per snapshot in batches; vectors and model labels are persisted alongside each chunk. Embedding failures are logged by exception category and do not fail repository analysis.
- Q&A performs lexical ranking plus semantic cosine ranking where query and snapshot embeddings are available, and reciprocal-rank fusion when both have matches. PostgreSQL attempts a dimension-specific pgvector table, scoped metadata index, and cosine HNSW index; the query filters by analysis ID, exact commit SHA, and embedding model. SQLite uses vectors stored in the loaded snapshot and retains lexical fallback.
- Optional generation receives bounded retrieved evidence and a prompt that treats repository text as untrusted. It must return citation IDs from the retrieved set; unsupported IDs or provider errors cause a deterministic local uncertainty response. The API also verifies citation paths, commit SHA, and line bounds.
- Frontend Q&A labels retrieval mode, generation mode, provider status, and insufficient evidence. Citation buttons load source previews from the same stored analysis.
- Tests run without internet or paid credentials. The OpenAI API was not called. The local PostgreSQL/pgvector engine was unavailable, so pgvector DDL/query execution remains unverified; SQL snapshot/commit/model filter behavior is mocked in a regression test.
- Verification for this milestone: `..\.venv\Scripts\python.exe -m pytest -q tests` passed (**89 tests, 5 upstream deprecation warnings**); `..\.venv\Scripts\python.exe -m ruff check app tests` passed; `npm.cmd exec -- prettier --check src` passed; `npm.cmd run build` passed TypeScript and Vite production build.
- Configuration and privacy details: [docs/RAG_PIPELINE.md](docs/RAG_PIPELINE.md). Live GitHub analysis remains blocked at outbound pinned TCP, as recorded above.

## Known issues / scope boundaries

- Synchronous API analysis only; Redis/RQ jobs are absent.
- Optional OpenAI embeddings/generation are implemented but were not exercised against the live provider; the no-key default uses lexical retrieval and deterministic snapshot metadata answers, with uncertainty for questions it cannot answer safely.
- Python AST plus JavaScript/TypeScript syntax symbols are supported; other languages use extension classification and text chunks. Static analysis currently covers Python only.
- pgvector storage/query is attempted when PostgreSQL is active, but was not exercised against a running PostgreSQL/pgvector service in this environment.
- SQLAlchemy creates tables at startup; the Alembic baseline exists but migrations are not wired into container startup.
- No authentication; deployment should remain local/trusted.
- Timed-out operating-system DNS lookups cannot be forcibly stopped; cancellation ends the application wait while the bounded AnyIO worker call may continue until the OS resolver returns.
- Live GitHub ingestion could not be verified in this environment because outbound GitHub access failed.

## Milestone 16 — local integration verification (2026-10-11)

- Runtime configuration was checked without reading credential contents: no `OPENAI_API_KEY` or `DATABASE_URL` process variable was present and no `backend/.env` existed. Thus configured fallback uses local SQLite and has no configured external AI provider.
- Existing backend and Vite processes were already bound to loopback at ports 8000 and 5173. HTTP checks returned 200 for `/api/health`, `/api/readiness`, the dashboard document, and the Vite `/api/health` proxy. Attempts to start duplicate services encountered occupied ports. The extra Vite process that selected 5174 was stopped.
- `tests/test_fixture_workflow.py` exercised the actual FastAPI routes with a controlled snapshot and isolated SQLite: submission, detail, file tree/preview, symbol ranges, answerable Q&A and citations, insufficient-evidence behavior, Markdown/JSON exports, and persistence after reopening the database. It does not verify GitHub ingestion.
- Added `test_unconfigured_default_never_constructs_or_calls_external_provider`, `test_provider_configuration_requires_a_nonempty_explicit_key`, and `test_baseline_migration_upgrades_isolated_sqlite_database`. Migration verification used a new `tmp_path` database; the user's database was untouched.
- Final backend result: **92 passed, 6 warnings** (`python -m pytest -q`). Ruff `check app tests` passed. Frontend Prettier check and `npm run build` (which includes `tsc -b`) passed. No frontend lint script is configured.
- Docker CLI exists, but `docker info` could not connect to `//./pipe/docker_engine`; no Docker service was started. PostgreSQL/pgvector was not configured, so live vector DDL/query remains unverified. Tests verify query metadata scoping through a mock only. OpenAI requests remain mock-tested; none were made in this milestone.
- Source transmission is an explicit configuration opt-in: only setting a non-empty OpenAI key enables the provider; see [docs/RAG_PIPELINE.md](docs/RAG_PIPELINE.md). Do not configure it unless external processing is intended.

## Next steps

1. When an isolated PostgreSQL/pgvector service is available, run migration and end-to-end vector persistence/retrieval tests against a dedicated test database.
2. Run the full ingestion workflow against a public Python repository when outbound GitHub access is available.
3. Only after reviewing source-sharing implications and approving any cost, perform a manual OpenAI integration check with a deliberately configured key.
4. Wire Alembic upgrades into application startup instead of relying on SQLAlchemy table creation; keep unauthenticated operation restricted to localhost.

## Final localhost readiness recheck (2026-10-11)

- Current tree and changes were inspected and preserved. Root virtual environment is `.venv`; frontend dependencies are installed. No environment credentials were inspected or sent.
- Loopback services were already running: backend 127.0.0.1:8000 (Python PID 20584), Vite 127.0.0.1:5173 (Node PID 6200), and Vite 127.0.0.1:5174 (Node PID 23320). Health/readiness returned 200 and both Vite proxies returned the health JSON. The dashboard rendered at 5174 with no analyses in the current response. No duplicate processes were started or terminated.
- Existing backend PID start time was 02:38 local, while checked-out backend source files were written around 11:xx. This listener predates current source; WMI denied command-line access and its stdout/log stream was unavailable, so it cannot be proven whether an autoreloader installed the latest code. A request to it for `https://github.com/pallets/itsdangerous` returned HTTP 502 and `Could not establish a secure connection to GitHub...`; no saved success was returned.
- From this command context, both `curl.exe -I --connect-timeout 10 https://api.github.com` and the equivalent codeload check failed to connect. The current `PinnedGitHubTransport` resolved one approved IPv4 answer then emitted `Pinned IPv4 TCP connection failed (ConnectError: All connection attempts failed)` before TLS. This is evidence of outbound TCP failure in this session. The user's separately reported curl 200/301 is not contradicted; it was not reproducible from this executor. The last successful approved-egress full ingestion/export remains the earlier live verification, not a result from this ordinary local listener.
- Browser check: Chrome loaded `http://127.0.0.1:5174`; the page rendered and its `/api/health` proxy worked. DevTools console output was not available through the exposed automation interface; no browser console-clean claim is made. No UI submission was performed in this session.
- URL parsing accepts `https://github.com/owner/repo` without a `.git` suffix, `.git` suffixes, and the supported `www.github.com` form; added explicit parser regression coverage.
- Final gates after the URL test update: **105 passed, 5 upstream deprecation warnings**; repository-wide Ruff and `pip check` passed. Frontend Prettier, `npm run build` (`tsc -b` and Vite), and `npm ls --depth=0` passed. `git diff --check` passed; Git printed line-ending normalization warnings only.
- No confirmed defect in the pinned transport or redirect policy was found. No application network security control was weakened. Current local live ingestion remains blocked/unverified in this executor, and the existing backend may be stale. To test with current code, stop the known old backend from its owning terminal (only after confirming it), then use the exact PowerShell launch commands in README and submit from the dashboard. If outbound TCP remains blocked, capture that same backend terminal's pinned transport stage logs.

## Milestone 18 — GitHub ingestion failure diagnosis (2026-10-11)

- Traced `POST /api/analyses` from the typed frontend request through `create_analysis`, `analyze_repository`, GitHub metadata/commit/zipball requests, exact codeload redirect validation, and archive download. No redirect is automatically followed; each request uses the pinned transport.
- Reproduced the failure inside this sandbox through the real FastAPI route using an isolated temporary SQLite database. `api.github.com` resolved to one allowed public IPv4 address; the pinned TCP connection failed with `httpx.ConnectError` caused by `httpcore.ConnectError: All connection attempts failed`. No TLS handshake occurred. The route returned HTTP 502 with its connectivity-specific message.
- With approved outbound access, the same actual FastAPI route and pinned transport successfully analyzed the public repository `pallets/itsdangerous`: commit `672971d66a2ef9f85151e53283113f33d642dabd`, 50 files, 15 Python files, 296 symbols, and 82 findings. GitHub returned 302 for the zipball; the app validated the exact codeload destination and downloaded the archive over pinned, TLS-verified HTTPS (200). Markdown and JSON report endpoints both returned 200. The run used a temporary isolated SQLite database; no AI provider was configured or called.
- This proves the ingestion path can complete when outbound TCP is permitted. The previous failure is specific to the sandbox/network context, not a reproduced application transport defect. The user's independent `curl.exe` results differ from the default sandbox; do not assume a backend process has the same egress context as the elevated diagnostic.
- Extended redirect regression cases for URL credentials, query, fragment, traversal, network-path references, and case-insensitive owner/repository matching. No transport security was weakened. Updated two Alembic import orders so repository-wide Ruff passes.
- Verification: focused transport tests **49 passed**; full backend `pytest -q` **103 passed, 5 upstream deprecation warnings**; repository-wide `ruff check .` passed; frontend Prettier check passed; `npm run build` passed TypeScript and Vite production build.
- Remaining limitation: live analysis has not been confirmed from the user's ordinary running backend process or their browser session. The sandbox process still cannot establish outbound TCP. A separate live run in the ordinary local process context is needed to confirm the reported UI failure is resolved there.

## Milestone 17 — final quality audit (2026-10-11)

- Audited the working tree and inspected backend settings/routes/database/migrations, GitHub transport and ingestion, RAG providers, frontend API/Q&A/history, Compose, requirements, CI, and project/security documentation. Existing user database and prior workspace changes were preserved.
- Fixed the workspace history error path: history API failures no longer clear to an empty list; the UI displays an alert/retry action and unavailable counts instead of presenting zero as successful history.
- Unexpected repository-analysis exceptions now log the exception category only. Exception messages and tracebacks, which may contain untrusted request/provider details, are excluded from the application log. Added a regression test with a sentinel value.
- Archive ingestion now rejects ZIP symbolic links and special file types, recording them as skipped entries. Added regular, symlink, FIFO, and character-device tests. Static analyzer process creation explicitly passes `shell=False`.
- Frontend fetch failures now identify an unreachable local API; history failures remain visible with retry and unavailable/loading counts instead of misleading zeros.
- Added Alembic's explicit OS path separator setting to remove a migration configuration warning without changing the migration.
- Strengthened the controlled workflow test to run installed Ruff/Bandit against its small controlled source, verify a Ruff result via the API findings filter, and retain file/symbol preview, Q&A, citation, report, and persistence assertions.
- Final verification: **97 passed, 5 warnings** (`pytest -q`); Ruff passed; `pip check` reported no broken requirements; Prettier check, TypeScript/Vite production build, and `npm ls --depth=0` passed. Migration test uses an isolated temporary SQLite database.
- Remaining warnings are upstream Starlette/AnyIO, Bandit option deprecation, and Python AST `ast.Str`. No local frontend lint or browser component-test configuration exists. `pip-audit` is not installed, and no online vulnerability advisory lookup was run.
- CI now runs the frontend Prettier check in addition to the existing backend Ruff/tests and frontend build.
- Live service checks returned HTTP 200 for the backend health/readiness/OpenAPI endpoints and Vite dashboard/API proxy. A live invalid-host submission returned HTTP 422; backend route tests separately verify validation, inaccessible-repository, timeout, and connectivity response categories. A browser automation surface was unavailable, so no visual browser interaction was claimed.
- Local status checks found no OpenAI key or database URL in the current process environment and no `backend/.env`. This is not a live provider test. The Docker engine is unavailable through its named pipe. GitHub outbound TCP, OpenAI live calls, and live PostgreSQL/pgvector remain unverified.
- README now includes a Mermaid architecture, stack, explicit verified/unverified table, setup and fixture commands, and screenshot placeholders. Added [docs/INTERVIEW_GUIDE.md](docs/INTERVIEW_GUIDE.md) with an implementation-grounded explanation and five technical Q&As.

### Prioritized remaining work

1. Run a live public-repository test when outbound GitHub TCP is available; verify commit, manifest, symbols, scanner findings, citations, and exports.
2. When an isolated PostgreSQL/pgvector service is available, verify migrations and actual vector insert/query isolation against a disposable test database.
3. Only with a deliberate operator key and approval for any possible charges, run an optional live OpenAI test after reviewing data-sharing implications.
4. Add a frontend test runner/browser workflow for history/API failure states and capture genuine local UI screenshots. Keep authentication and access control as prerequisites to any network exposure.

## Repository understanding profile update (2026-10-11)

- Added a versioned, persisted profile synthesized from snapshot README/docs, language/config manifests, file metadata, extracted symbols/imports, scanner output, and coverage. It includes evidence tags and source references, plus a syntax-level module relationship diagram only when import edges resolve to indexed modules.
- Added lightweight route, database dependency, security construct, test/CI/deployment path, and feature-section observations. These use static patterns and do not prove runtime behavior or control effectiveness.
- Added question-intent weighted lexical chunk retrieval, generic README suppression for implementation questions, and lockfile downranking. Existing local fallback/provider and citation validation paths remain in use.
- Added Project Overview and Recommended Improvements tabs, plus the profile in JSON/Markdown reports. Scanner-derived suggestions remain review items; no automated P0/confirmed defect is produced.
- Regression coverage includes profile evidence, syntactic relationships, recommendations, and a README-versus-auth-source retrieval case. Full current verification: 139 backend tests passed with five upstream deprecation warnings; Ruff and pip check passed; Prettier check, TypeScript/Vite production build passed. GitHub/OpenAI/PostgreSQL live integration was not exercised in this change.

## Optional Gemini provider update (2026-10-11)

- Added the official Google `google-genai` SDK (pinned `2.29.0`) as an optional backend dependency. The configured Gemini model defaults to `gemini-3.1-flash-lite`; Google's current pricing docs list standard text input/output in the free tier. Model access, quotas, free-tier rules, and billing terms can change.
- Provider selection is `RAG_PROVIDER=auto|local|openai|gemini`. Auto prefers configured Gemini, then configured OpenAI, then local mode. A provider error or quota limit falls back locally and never switches to a different remote provider. Gemini is generation-only; it does not modify the current OpenAI embedding workflow.
- The backend sends only retrieved, redacted, bounded snapshot evidence plus the question. It validates generated citation IDs against retrieved chunks and relies on the existing API path/commit/line validation. Provider name and readiness are exposed without credentials.
- `.env.example` has blank key placeholders; Git ignores root and nested `.env` files. No key was added or live Gemini call made. Mock tests cover SDK request/output bounds, missing key, invalid output, quota/timeouts, fallback, and citation scoping.
- Verification after integration: **148 backend tests passed** with five upstream deprecation warnings; Ruff, `pip check`, frontend Prettier, TypeScript/Vite production build, and `git diff --check` passed. Gemini behavior was verified with mocked SDK calls and a local SDK import/client-construction check only; no credential, live Gemini request, or quota consumption was used.
