# Project status

Updated: 2026-10-11

## Completed

- Initialized Git in the previously empty workspace.
- Implemented a React/TypeScript/Vite dashboard.
- Added clickable repository file navigation with bounded source excerpts from the pinned snapshot.
- Implemented FastAPI health/readiness, repository analysis, compact snapshot history, files, filtered findings, Q&A, and escaped Markdown/JSON reports.
- Added GitHub URL validation, commit pinning, constrained API/archive access, bounded ZIP processing, Python AST symbols, lexical chunks/retrieval, and Ruff/Bandit integration.
- Added SQLAlchemy persistence (SQLite default; PostgreSQL configurable), Alembic migration, Docker Compose, CI, security docs, and regression tests.
- Documented unimplemented AI and background-job features explicitly.
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

## Known issues / scope boundaries

- Synchronous API analysis only; Redis/RQ jobs are absent.
- No configurable LLM/embedding provider; Q&A uses lexical retrieval.
- Python AST symbols only; other languages use extension classification and text chunks.
- pgvector is available in Compose but not used by application queries/storage.
- SQLAlchemy creates tables at startup; the Alembic baseline exists but migrations are not wired into container startup.
- No authentication; deployment should remain local/trusted.
- Timed-out operating-system DNS lookups cannot be forcibly stopped; cancellation ends the application wait while the bounded AnyIO worker call may continue until the OS resolver returns.
- Live GitHub ingestion could not be verified in this environment because outbound GitHub access failed.

## Next steps

1. Run the full analysis workflow against a public Python repository when outbound GitHub access is available.
2. Consider isolating OS DNS lookups in a dedicated bounded resolver worker service if environments with unreliable DNS become a deployment target.
3. Wire Alembic upgrades into application startup instead of relying on SQLAlchemy table creation.
4. Add authentication and repository-scoped access control before any shared deployment; treat Tree-sitter breadth, embeddings/LLM, and background jobs as later separate milestones.
