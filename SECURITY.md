# Security notes

Repository contents are untrusted. RepoGuard does not execute repository code, tests, package scripts, build scripts, notebooks, or binaries.

## Implemented safeguards

- HTTPS GitHub URLs only; credentials, unexpected ports, unsupported hosts, malformed paths, and non-public repositories are rejected.
- Repository metadata, commit resolution, and archive requests start at fixed `api.github.com`; automatic redirects are disabled. The only accepted archive redirect is the expected HTTPS `codeload.github.com` snapshot path, and API authorization is not forwarded to the archive host.
- `PinnedGitHubTransport` resolves DNS immediately before each TCP connection, rejects the whole answer set if any IPv4/IPv6 address is non-global, private, loopback, link-local, multicast, reserved, unspecified, or IPv4-mapped IPv6, and passes a validated IP literal to the socket connector. It never reconnects by the original hostname. HTTPX retains the URL hostname for TLS SNI, certificate hostname validation, and the HTTP `Host` header.
- Proxy environment variables are ignored (`trust_env=False` and a direct transport); idle connection pooling and automatic redirects are disabled so each new connection gets a fresh DNS check. HTTPS port 443, response timeouts, a 1 MB GitHub JSON limit, and a 30 MB archive limit are enforced.
- Connection diagnostics identify DNS lookup/answer validation, pinned TCP, and TLS handshake/certificate-verification stages. They record exception classes and bounded connection diagnostics only; they do not include request headers, repository content, tokens, or environment values.
- Archive paths reject absolute paths, backslashes, and traversal. Archive downloads are streamed with a byte cap. Entry count, file size, total accepted uncompressed size, chunks, and compression ratio are bounded.
- Static analysis is capped at 100 Python files per run to bound subprocess work.
- UTF-8 text only. Unsupported and binary content is skipped.
- Ruff/Bandit use argument arrays (no shell), three-second timeouts, and one-megabyte captured-output caps.
- Request bodies (by declared content length), fields, and list sizes are bounded. CORS and trusted hosts are restricted by configuration/defaults.
- Logs exclude request bodies, source contents, and credentials; client errors are concise.
- Q&A citations are checked against the loaded snapshot's file manifest, line bounds, and exact commit SHA before being returned. Regression tests cover cross-commit citations.

## Known limitations

- DNS rebinding between validation and connection is addressed by pinning the socket connection to the IP address validated by the transport. Tests use a controlled local TLS server and a routing shim to show that the selected DNS IP reaches the connector while TLS SNI, certificate verification, and `Host` retain the GitHub hostname.
- The operating-system `getaddrinfo` call runs in AnyIO's bounded worker pool. Cancelling a timed-out lookup stops waiting for it but cannot forcibly terminate the underlying OS resolver call; a resolver that hangs can occupy a worker until the OS call returns.
- This control prevents DNS answers from redirecting the connection to private addresses; it cannot control unusual network-layer routing/NAT that redirects an otherwise public destination. Keep the unauthenticated application bound to localhost and do not treat it as a complete security scanner.
- Archives are buffered in memory up to the download limit rather than streamed.
- No authentication or per-user access control exists. Do not expose the API on an untrusted network or use it as a multi-tenant service.
- Source chunks persist locally; the API returns only bounded file excerpts and does not include chunks in general detail or JSON reports. Add authentication and repository-scoped authorization before network exposure.
- The external font stylesheet is optional and may be removed for fully offline use.
- Live GitHub ingestion could not be verified during the 2026-10-11 runtime audits. DNS resolved `api.github.com` and `codeload.github.com` to IPv4 answers, but the actual pinned IPv4 TCP connection to both failed with `httpcore.ConnectError: All connection attempts failed`; the failure occurred before TLS. This indicates GitHub outbound connectivity is unavailable from the current environment, but does not identify the specific firewall, sandbox, or local network cause. Controlled fixture and TLS tests are separate and are not evidence of live GitHub ingestion.

Report security issues privately to the project maintainer. Do not include real secrets in reports or issues.
