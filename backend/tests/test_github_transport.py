import socket
import ssl
import threading
import time
from pathlib import Path

import anyio
import httpcore
import httpx
import pytest

from app.services.analyzer import (
    AnalysisError,
    _github_json,
    _read_bounded_archive,
    _validate_archive_redirect,
    parse_github_url,
)
from app.services.github_transport import PinnedGitHubTransport, _public_addresses


class _LocalTLSServer:
    def __init__(self) -> None:
        fixture_dir = Path(__file__).parent / "fixtures"
        self.listener = socket.socket()
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.listener.settimeout(0.1)
        self.port = self.listener.getsockname()[1]
        self.requests: list[bytes] = []
        self.server_names: list[str | None] = []
        self.response_delay = 0.0
        self.stopping = threading.Event()
        self.served = threading.Event()
        self.server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.server_context.load_cert_chain(
            fixture_dir / "github-test-cert.pem", fixture_dir / "github-test-key.pem"
        )
        self.server_context.set_servername_callback(
            lambda _ssl, name, _context: self.server_names.append(name)
        )
        self.client_context = ssl.create_default_context(
            cafile=str(fixture_dir / "github-test-cert.pem")
        )
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        while not self.stopping.is_set():
            try:
                connection, _ = self.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            try:
                connection.settimeout(2)
                with self.server_context.wrap_socket(connection, server_side=True) as secure:
                    request = bytearray()
                    while b"\r\n\r\n" not in request and len(request) < 16384:
                        part = secure.recv(4096)
                        if not part:
                            break
                        request.extend(part)
                    if request:
                        self.requests.append(bytes(request))
                        time.sleep(self.response_delay)
                        secure.sendall(
                            b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n"
                            b"Connection: close\r\n\r\nok"
                        )
            except (OSError, ssl.SSLError):
                self.served.set()
                return
            self.served.set()
            return

    def join(self) -> None:
        self.served.wait(timeout=1)
        self.thread.join(timeout=1)

    def close(self) -> None:
        self.stopping.set()
        self.listener.close()
        self.thread.join(timeout=1)


@pytest.fixture
def tls_server():
    server = _LocalTLSServer()
    try:
        yield server
    finally:
        server.close()


@pytest.mark.parametrize("resolved_ip", ["93.184.216.34", "2606:4700:4700::1111"])
def test_pinned_transport_connects_to_the_validated_ip_and_preserves_tls_identity(
    tls_server, monkeypatch, resolved_ip
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    resolved: list[tuple[str, int]] = []
    dialed: list[tuple[str, int]] = []

    def resolver(host: str, port: int) -> list[str]:
        resolved.append((host, port))
        return [resolved_ip]

    async def local_route(ip, port, timeout, local_address, socket_options):
        dialed.append((ip, port))
        return await httpcore.AnyIOBackend().connect_tcp(
            "127.0.0.1", tls_server.port, timeout, local_address, socket_options
        )

    transport = PinnedGitHubTransport(
        {"api.github.com"}, resolver=resolver, dialer=local_route, verify=tls_server.client_context
    )

    async def request():
        async with httpx.AsyncClient(transport=transport, timeout=2, trust_env=False) as client:
            return await client.get("https://api.github.com/repos/example/project")

    response = anyio.run(request)
    tls_server.join()
    assert response.status_code == 200
    assert resolved == [("api.github.com", 443)]
    assert dialed == [(resolved_ip, 443)]
    assert tls_server.server_names == ["api.github.com"]
    assert b"Host: api.github.com" in tls_server.requests[0]


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["10.0.0.5"],
        ["169.254.1.1"],
        ["224.0.0.1"],
        ["192.0.2.1"],
        ["::1"],
        ["fe80::1"],
        ["ff02::1"],
        ["::ffff:127.0.0.1"],
        ["93.184.216.34", "127.0.0.1"],
    ],
)
def test_private_reserved_and_mixed_dns_answers_are_rejected(addresses) -> None:
    with pytest.raises(httpcore.ConnectError):
        _public_addresses(addresses)


@pytest.mark.parametrize(
    "addresses",
    [["127.0.0.1"], ["10.0.0.1"], ["fe80::1"], ["ff02::1"], ["93.184.216.34", "::1"]],
)
def test_transport_never_dials_when_any_dns_answer_is_prohibited(tls_server, addresses) -> None:
    dialed: list[str] = []

    async def local_route(ip, port, timeout, local_address, socket_options):
        dialed.append(ip)
        return await httpcore.AnyIOBackend().connect_tcp(
            "127.0.0.1", tls_server.port, timeout, local_address, socket_options
        )

    transport = PinnedGitHubTransport(
        {"api.github.com"},
        resolver=lambda *_: addresses,
        dialer=local_route,
        verify=tls_server.client_context,
    )

    async def request():
        async with httpx.AsyncClient(transport=transport, timeout=2) as client:
            with pytest.raises(httpx.ConnectError):
                await client.get("https://api.github.com/")

    anyio.run(request)
    assert dialed == []


@pytest.mark.parametrize("address", ["8.8.8.8", "2606:4700:4700::1111"])
def test_public_ipv4_and_ipv6_answers_are_permitted(address) -> None:
    assert _public_addresses([address]) == [address]


def test_dns_change_before_a_new_connection_is_revalidated(tls_server) -> None:
    answers = iter([["93.184.216.34"], ["127.0.0.1"]])
    resolutions: list[str] = []
    dials: list[str] = []

    def resolver(host: str, port: int) -> list[str]:
        answer = next(answers)
        resolutions.append(answer[0])
        return answer

    async def local_route(ip, port, timeout, local_address, socket_options):
        dials.append(ip)
        return await httpcore.AnyIOBackend().connect_tcp(
            "127.0.0.1", tls_server.port, timeout, local_address, socket_options
        )

    transport = PinnedGitHubTransport(
        {"api.github.com"}, resolver=resolver, dialer=local_route, verify=tls_server.client_context
    )

    async def requests():
        async with httpx.AsyncClient(transport=transport, timeout=2) as client:
            first = await client.get("https://api.github.com/first")
            assert first.status_code == 200
            with pytest.raises(httpx.ConnectError):
                await client.get("https://api.github.com/second")

    anyio.run(requests)
    tls_server.join()
    assert resolutions == ["93.184.216.34", "127.0.0.1"]
    assert dials == ["93.184.216.34"]
    assert len(tls_server.requests) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://api.github.com/repos/a/b",
        "https://api.github.com:444/repos/a/b",
        "https://evil.example/repos/a/b",
    ],
)
def test_transport_rejects_scheme_host_and_port_before_dns(url) -> None:
    transport = PinnedGitHubTransport({"api.github.com"}, resolver=lambda *_: ["93.184.216.34"])

    async def request():
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(httpx.UnsupportedProtocol):
                await client.get(url)

    anyio.run(request)


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repo",
        "https://github.com:444/owner/repo",
        "https://github.com/owner/repo?redirect=evil",
        "https://github.com//owner/repo",
        "https://github.com:/owner/repo",
        "https://github.com:0443/owner/repo",
        "https://github.com/owner/repo#fragment",
        "https://evil.example/owner/repo",
    ],
)
def test_repository_url_forms_reject_unexpected_destinations(url) -> None:
    with pytest.raises(AnalysisError):
        parse_github_url(url)


@pytest.mark.parametrize(
    "location",
    [
        "http://codeload.github.com/example/project/legacy.zip/" + "a" * 40,
        "https://codeload.github.com:444/example/project/legacy.zip/" + "a" * 40,
        "https://codeload.github.com:/example/project/legacy.zip/" + "a" * 40,
        "https://127.0.0.1/example/project/legacy.zip/" + "a" * 40,
        "https://evil.example/example/project/legacy.zip/" + "a" * 40,
        "https://codeload.github.com/example/project/legacy.zip/" + "b" * 40,
    ],
)
def test_redirects_to_prohibited_or_unpinned_destinations_are_rejected(location) -> None:
    with pytest.raises(AnalysisError):
        _validate_archive_redirect(location, "example", "project", "a" * 40)


def test_only_exact_codeload_redirect_is_accepted() -> None:
    location = "https://codeload.github.com/example/project/legacy.zip/" + "a" * 40
    assert _validate_archive_redirect(location, "example", "project", "a" * 40) == location


def test_tls_certificate_hostname_is_verified(tls_server, caplog) -> None:
    transport = PinnedGitHubTransport(
        {"api.github.com", "codeload.github.com"},
        resolver=lambda *_: ["93.184.216.34"],
        dialer=lambda ip, port, timeout, local_address, socket_options: httpcore.AnyIOBackend().connect_tcp(
            "127.0.0.1", tls_server.port, timeout, local_address, socket_options
        ),
        verify=tls_server.client_context,
    )

    async def request():
        async with httpx.AsyncClient(transport=transport, timeout=2) as client:
            with pytest.raises(httpx.ConnectError):
                await client.get("https://codeload.github.com/example/project")

    anyio.run(request)
    tls_server.join()
    assert tls_server.server_names == ["codeload.github.com"]
    assert tls_server.requests == []
    assert "GitHub TLS handshake or certificate verification failed" in caplog.text


def test_dns_lookup_timeout_is_bounded(tls_server) -> None:
    def slow_resolver(host: str, port: int) -> list[str]:
        time.sleep(0.3)
        return ["93.184.216.34"]

    transport = PinnedGitHubTransport({"api.github.com"}, resolver=slow_resolver)

    async def request():
        async with httpx.AsyncClient(transport=transport, timeout=0.05) as client:
            with pytest.raises(httpx.ConnectTimeout):
                await client.get("https://api.github.com/")

    anyio.run(request)


def test_response_read_timeout_is_enforced(tls_server) -> None:
    tls_server.response_delay = 0.2
    transport = PinnedGitHubTransport(
        {"api.github.com"},
        resolver=lambda *_: ["93.184.216.34"],
        dialer=lambda ip, port, timeout, local_address, socket_options: httpcore.AnyIOBackend().connect_tcp(
            "127.0.0.1", tls_server.port, timeout, local_address, socket_options
        ),
        verify=tls_server.client_context,
    )

    async def request():
        timeout = httpx.Timeout(2, read=0.05)
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
            with pytest.raises(httpx.ReadTimeout):
                await client.get("https://api.github.com/slow")

    anyio.run(request)
    tls_server.join()


def test_archive_response_size_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr("app.services.analyzer.MAX_ARCHIVE_BYTES", 2)
    response = httpx.Response(200, content=b"oversized")

    async def read():
        with pytest.raises(AnalysisError, match="30 MB"):
            await _read_bounded_archive(response)

    anyio.run(read)


def test_metadata_response_size_is_bounded() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b" " * 1_000_001)
    )

    async def request():
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(AnalysisError, match="1 MB"):
                await _github_json(client, "https://api.github.com/repos/example/project")

    anyio.run(request)
