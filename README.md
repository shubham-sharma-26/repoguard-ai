# RepoGuard AI

RepoGuard AI is a local-first analyzer for public GitHub projects. Each run is pinned to a resolved commit and combines repository structure, local Python static analysis, and lexical source-grounded Q&A.

## What works

- Accepts public GitHub repository URLs and rejects credentials, custom ports, malformed paths, and other hosts.
- Resolves the default branch to a full commit SHA; downloads that exact snapshot through `api.github.com` and a constrained `codeload.github.com` redirect.
- Pins each outbound TCP connection to a validated public IPv4/IPv6 DNS answer while retaining the original TLS SNI, certificate hostname check, and HTTP Host header. Environment proxies and connection reuse are disabled.
- Applies streaming archive, entry-count, per-file, total uncompressed-file, chunk, and output bounds. It never executes repository code.
- Reports file/language statistics and extracts Python AST functions, classes, imports, and top-level assignments.
- Runs Ruff and Bandit against up to 100 Python files with subprocess timeouts; reports tool availability.
- Records when static-analysis coverage is truncated at that 100-file limit.
- Persists complete analysis snapshots/history using SQLite by default or PostgreSQL when configured.
- Provides file search and bounded source excerpts, filtered findings, lexical Q&A with snapshot citations, and Markdown/JSON exports.
- Includes a responsive React/TypeScript dashboard and FastAPI OpenAPI documentation.

## Scope and limitations

- Analysis is synchronous. Redis/RQ jobs, progress polling, cancellation, and retries are not implemented.
- Python has AST symbol extraction. Other languages are classified by extension and chunked lexically. Tree-sitter structural parsing for more languages, call graphs, embeddings, pgvector queries, and LLM providers are not implemented.
- Q&A is deterministic lexical retrieval. It does not claim semantic or AI-generated understanding.
- Findings are local Ruff/Bandit output. There is no AI remediation, authentication, or multi-user isolation; keep the service on a trusted local machine.
- Compose includes PostgreSQL with pgvector, but application storage is JSON and does not use vectors. Docker runtime was unavailable during implementation.
- Compose published ports bind to `127.0.0.1`; the local development server commands also use loopback.
- GitHub API rate limits may apply. `GITHUB_TOKEN` is optional and must be set via the environment.

## Run locally

Requirements: Python 3.13+, Node.js 24+, npm. Docker is optional.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Set-Location backend
uvicorn app.main:app --reload
```

The backend uses `backend/repoguard.db` SQLite when `DATABASE_URL` is unset. In another terminal:

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

Open http://127.0.0.1:5173. API docs are at http://127.0.0.1:8000/docs. For optional file-based configuration, copy `.env.example` to `backend/.env`; never commit `.env`.

## PostgreSQL with Docker Compose

```powershell
docker compose up --build
```

Compose credentials are for local development only. Replace them before using a shared environment.

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Process health |
| GET | `/api/readiness` | Database readiness |
| POST | `/api/analyses` | Analyze a public GitHub URL |
| GET | `/api/analyses` | Compact recent analysis history |
| GET | `/api/analyses/{id}` | Retrieve a snapshot |
| GET | `/api/analyses/{id}/files` | List/search file paths |
| GET | `/api/analyses/{id}/file-content?path=...` | Read bounded indexed excerpts for one manifest file |
| GET | `/api/analyses/{id}/findings` | Filter static findings |
| POST | `/api/analyses/{id}/ask` | Lexical source Q&A with citations |
| GET | `/api/analyses/{id}/report.md` | Markdown report |
| GET | `/api/analyses/{id}/report.json` | JSON report |

## Development checks

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m ruff check app tests
..\.venv\Scripts\python.exe -m pytest -q
Set-Location ..\frontend
npm.cmd exec -- prettier --check src
npm.cmd run build
```

The frontend currently has no configured lint script. CI runs the backend lint/test suite and frontend build. Repository scripts, tests, and binaries are never run by the analyzer.

## Runtime audit (2026-10-11)

- Verified local startup at `http://127.0.0.1:8000` and `http://127.0.0.1:5173/`; health, readiness, frontend page, and Vite's `/api/health` proxy returned HTTP 200.
- Backend tests (71) and Ruff passed; dependency consistency (`pip check`) passed. The 43 focused transport tests use a local TLS server and verify IPv4/IPv6 dial targets, TLS SNI/certificate hostname, Host header, denied DNS answers and redirects, proxy/pool behavior, timeouts, and response limits. Prettier check and the frontend TypeScript/Vite production build passed. The controlled fixture API workflow includes persisted SQLite readback and report/Q&A checks.
- Live `pallets/itsdangerous` analysis was attempted again through the application API but outbound connection to GitHub failed (`httpcore.ConnectError: All connection attempts failed`, returned as HTTP 502 by the local API). Live commit, manifest, and scanner results are therefore unverified.
- Docker engine was unavailable, so container startup was not tested. SQLite local mode was used.
- See [PROJECT_STATUS.md](PROJECT_STATUS.md) for commands, exact results, and remaining audit items. Connections are DNS-pinned and TLS-verified, but the unauthenticated application remains intended for trusted localhost use only.

## Architecture

- `backend/app/services/analyzer.py`: URL/host checks, archive safety, extraction, symbols, static tools, lexical retrieval.
- `backend/app/main.py`: HTTP endpoints, response validation, errors, reports.
- `backend/app/database.py`: SQLAlchemy persistence.
- `backend/migrations`: Alembic baseline migration.
- `frontend/src`: React dashboard and typed API client.

See [SECURITY.md](SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md), and [PROJECT_STATUS.md](PROJECT_STATUS.md).
