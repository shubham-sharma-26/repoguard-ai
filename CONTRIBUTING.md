# Contributing

1. Create a Python virtual environment and install `backend/requirements.txt`.
2. Run `ruff check app tests` and `pytest -q` from `backend/`.
3. Run `npm.cmd install` and `npm.cmd run build` from `frontend/` on Windows (or `npm install` where the npm shim is available).
4. Bound untrusted input and add regression tests for security behavior.
5. Never execute repository content from an analysis, and never check in `.env`, credentials, or generated databases.
6. Update `PROJECT_STATUS.md` and user-facing docs when behavior changes.

CI validates backend lint/tests and the frontend production build.
