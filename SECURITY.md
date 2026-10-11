# Security notes

Repository contents are untrusted. RepoGuard does not execute repository code, tests, package scripts, build scripts, notebooks, or binaries.

## Implemented safeguards

- HTTPS GitHub URLs only; credentials, unexpected ports, unsupported hosts, malformed paths, and non-public repositories are rejected.
- Repository metadata, commit resolution, and archive requests start at fixed `api.github.com`; automatic redirects are disabled. The only accepted archive redirect is the expected HTTPS `codeload.github.com` snapshot path, and API authorization is not forwarded to the archive host.
- `PinnedGitHubTransport` resolves DNS immediately before each TCP connection, rejects the whole answer set if any IPv4/IPv6 address is non-global, private, loopback, link-local, multicast, reserved, unspecified, or IPv4-mapped IPv6, and passes a validated IP literal to the socket connector. It never reconnects by the original hostname. HTTPX retains the URL hostname for TLS SNI, certificate hostname validation, and the HTTP `Host` header.
- Proxy environment variables are ignored (`trust_env=False` and a direct transport); idle connection pooling and automatic redirects are disabled so each new connection gets a fresh DNS check. HTTPS port 443, response timeouts, a 1 MB GitHub JSON limit, and a 30 MB archive limit are enforced.
- Connection diagnostics identify DNS lookup/answer validation, pinned TCP, and TLS handshake/certificate-verification stages. They record exception classes and bounded connection diagnostics only; they do not include request headers, repository content, tokens, or environment values.
- Archive paths reject absolute paths, backslashes, and traversal. Archive downloads are streamed with a byte cap. Entry count, file size, total accepted uncompressed size, chunks, and compression ratio are bounded.
- Ruff/Bandit static analysis is capped at 100 Python files per run to bound subprocess work. JavaScript/TypeScript are structurally parsed but currently have no configured lint/security scanner; the API reports those languages as `not_analyzed`.
- UTF-8 text only. Unsupported and binary content is skipped.
- Ruff/Bandit use argument arrays (no shell), three-second timeouts, and one-megabyte captured-output caps.
- Request bodies (by declared content length), fields, and list sizes are bounded. CORS and trusted hosts are restricted by configuration/defaults.
- Logs exclude request bodies, source contents, and credentials; client errors are concise.
- Unexpected repository-analysis exceptions log only their class/category; untrusted exception messages and traceback text are not emitted. Regression coverage checks that a sentinel error value does not reach logs.
- Q&A citations are checked against the loaded snapshot's file manifest, line bounds, and exact commit SHA before being returned. Regression tests cover cross-commit citations.
- Optional OpenAI use is disabled unless `OPENAI_API_KEY` is configured. Configuring it opts in to sending bounded repository chunks for embeddings and the question plus retrieved source excerpts for generation. The API origin is fixed and uses the same DNS-validated pinned-IP HTTPS transport; redirects and environment proxies are disabled, normal TLS verification is retained, and keys/provider response bodies are not logged.
- Embedding values are stored within their exact analysis snapshot and tagged by model. PostgreSQL pgvector searches filter by analysis ID, commit SHA, and model. SQLite searches only the loaded snapshot; lexical fallback remains available without provider credentials or vectors.
- The model receives repository text as untrusted evidence, not instructions. It can cite only numeric IDs for retrieved chunks; the server maps those IDs back to known sources and independently validates manifest path, commit SHA, and line bounds. Invalid citations or generation errors produce an explicit extractive fallback.

## Known limitations

- DNS rebinding between validation and connection is addressed by pinning the socket connection to the IP address validated by the transport. Tests use a controlled local TLS server and a routing shim to show that the selected DNS IP reaches the connector while TLS SNI, certificate verification, and `Host` retain the GitHub hostname.
- The operating-system `getaddrinfo` call runs in AnyIO's bounded worker pool. Cancelling a timed-out lookup stops waiting for it but cannot forcibly terminate the underlying OS resolver call; a resolver that hangs can occupy a worker until the OS call returns.
- This control prevents DNS answers from redirecting the connection to private addresses; it cannot control unusual network-layer routing/NAT that redirects an otherwise public destination. Keep the unauthenticated application bound to localhost and do not treat it as a complete security scanner.
- Archives are buffered in memory up to the download limit rather than streamed.
- ZIP symlinks and non-regular special entries are skipped. This avoids treating their stored link/device payload as ordinary source; archive files are not extracted to a filesystem path.
- No authentication or per-user access control exists. Do not expose the API on an untrusted network or use it as a multi-tenant service.
- Source chunks persist locally; the API returns only bounded file excerpts and does not include chunks in general detail or JSON reports. Add authentication and repository-scoped authorization before network exposure.
- The external font stylesheet is optional and may be removed for fully offline use.
- Live GitHub ingestion could not be verified during the 2026-10-11 runtime audits. DNS resolved `api.github.com` and `codeload.github.com` to IPv4 answers, but the actual pinned IPv4 TCP connection to both failed with `httpcore.ConnectError: All connection attempts failed`; the failure occurred before TLS. This indicates GitHub outbound connectivity is unavailable from the current environment, but does not identify the specific firewall, sandbox, or local network cause. Controlled fixture and TLS tests are separate and are not evidence of live GitHub ingestion.
- The OpenAI provider integration uses mocked HTTP responses in tests only; no live AI request was made during this milestone. PostgreSQL/pgvector schema and search are also unverified against a running service; SQLite lexical fallback and in-snapshot vector retrieval are the supported local paths.

## Final quality audit update (2026-10-11)

- ZIP entry mode handling now skips symbolic links and special file types and records a skip reason. Regression tests cover symlinks, FIFO/character devices, and regular/unspecified ZIP modes. Archive paths are still validated and content stays in memory; no archive is extracted to disk.
- Unexpected exceptions in repository submission no longer log exception strings or full tracebacks. The log retains only the exception class; response messages remain concise and category-specific where known.
- Ruff and Bandit are invoked using fixed argument arrays and `shell=False`, with source passed on stdin, timeout and output caps.
- The frontend now keeps saved history errors visible, offers retry, and displays unavailable counts rather than zero when history cannot load. No browser automation test runner is configured, so this UI behavior has not been browser-tested automatically.
- Frontend network request failures now identify an unreachable local API; backend response messages retain their validation/repository versus GitHub connectivity distinction.
- Final observed checks: 97 backend tests passed (five upstream deprecation warnings), Ruff passed, `pip check` passed, Prettier/TypeScript/production build passed. `pip-audit` was absent and no online package advisory lookup was made; dependency consistency must not be interpreted as a vulnerability scan.
- Loopback health/readiness/OpenAPI and Vite dashboard/proxy requests returned HTTP 200; a live unsupported-host submission returned HTTP 422 without attempting outbound GitHub access. Browser automation was unavailable, so frontend error presentation was not visually exercised.
- No live GitHub, OpenAI, or PostgreSQL/pgvector requests were performed in this audit. The Docker engine pipe was unavailable. Keep unauthenticated use bound to loopback.

## Verification

- Backend tests: 89 passed with five upstream deprecation warnings; Ruff passed.
- Frontend Prettier check and TypeScript/Vite production build passed.
- Provider HTTP handling, prompt-injection boundaries, citation filtering, and pgvector query metadata scoping were exercised with deterministic mocks. No external AI request was made. Live GitHub remains unverified because pinned IPv4 TCP connections fail before TLS in the current environment.

## Milestone 16 local integration evidence (2026-10-11)

- Checked only whether provider/database settings were present, not credential values: `OPENAI_API_KEY` and `DATABASE_URL` were absent from process environment and no backend `.env` file existed. Fallback therefore selected SQLite with no configured OpenAI provider. The controlled workflow and an explicit regression test verify local Q&A does not construct/call a provider in this state.
- OpenAI source transmission is enabled only by a non-empty key explicitly configured by the operator. There is no separate per-repository consent control; configuring the key is the opt-in. The UI/docs disclose that bounded source chunks are sent for embeddings and relevant excerpts plus questions for generation. No OpenAI request was made or billable operation attempted.
- Runtime health/readiness and the Vite dashboard/proxy returned HTTP 200 on loopback. The fixture workflow verified validated citations, fallback/no-evidence behavior, report outputs, and persistence on an isolated SQLite database.
- The Alembic baseline was tested against a newly created temporary SQLite file only. No existing user database was upgraded or reset.
- Docker engine was unavailable through its Windows named pipe. `DATABASE_URL` was not configured, and no local PostgreSQL service was verified; pgvector DDL and actual vector search remain unverified. The SQL metadata filter is covered by a mocked test, not proof of a live database.
- Backend suite: 92 passed with six warnings; Ruff, frontend Prettier check, TypeScript, and production build passed. Live GitHub remains blocked before TLS by pinned outbound TCP, per the connectivity evidence above.

Report security issues privately to the project maintainer. Do not include real secrets in reports or issues.

## GitHub transport verification update (2026-10-11)

- The application continues to enforce destination allowlists, DNS address validation and IP-pinned TCP dialing, TLS certificate/hostname verification, disabled proxy use, no automatic redirects, exact codeload redirect validation, and bounded requests. No security control was disabled during diagnosis.
- In the restricted sandbox, the real analysis route resolved `api.github.com` to a permitted IPv4 address, then failed at TCP connect (`httpcore.ConnectError: All connection attempts failed`) before TLS. It returned HTTP 502. This is observed outbound reachability failure in that process context; it is not evidence of a TLS failure.
- Under separately approved outbound access, the same FastAPI route analyzed `pallets/itsdangerous` at commit `672971d66a2ef9f85151e53283113f33d642dabd`. The GitHub zipball's 302 target passed the exact host/path/commit redirect checks, then codeload returned the archive over the pinned transport with verified TLS. Report exports succeeded. No provider credentials were configured and no source was sent to an AI provider.
- The ordinary user's backend/browser context was not tested with that approved network permission. Environment-specific outbound policy can therefore still cause the UI's connectivity error. Keep the app bound to loopback and verify from the same process context used for normal local operation.

## Localhost audit recheck (2026-10-11)

- Local health/readiness and Vite-to-backend proxy checks succeeded. The current source's DNS-pinned transport resolved a permitted IPv4 address but failed TCP before TLS in this command context; ordinary `curl.exe` also failed to connect. This points to the current session's outbound TCP reachability and does not establish a TLS, redirect, or certificate defect.
- The Python process listening on 8000 began before the checked-out backend source's latest write times. WMI denied command-line/log inspection, so whether a reload process refreshed it could not be established. Its public-repository request returned the expected HTTP 502 connection detail. Do not treat health/readiness as proof that this process has current source loaded.
- Never work around this by disabling pinning/TLS or by enabling arbitrary proxies. Restart only the known RepoGuard backend from its own terminal after confirming the owning PID; leave unidentified listeners untouched. The approved live analysis noted above shows the secure code path can work when outbound TCP is allowed but is not proof about this local process.
