"""HTTPX transport that pins an explicit HTTPS host allowlist to validated IPs."""

from __future__ import annotations

import ipaddress
import logging
import socket
import time
from collections.abc import Callable
from functools import partial
from typing import Any

import anyio
import httpcore
import httpx

Resolver = Callable[[str, int], list[str]]
Dialer = Callable[..., Any]
logger = logging.getLogger("repoguard.pinned_transport")


def _system_resolve(host: str, port: int) -> list[str]:
    results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(result[4][0] for result in results))


def _public_addresses(addresses: list[str]) -> list[str]:
    if not addresses or len(addresses) > 16:
        raise httpcore.ConnectError("DNS returned an invalid number of addresses")
    parsed: list[str] = []
    try:
        for address in addresses:
            ip = ipaddress.ip_address(address)
            mapped = getattr(ip, "ipv4_mapped", None)
            if (
                not ip.is_global
                or ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
                or mapped is not None
            ):
                raise httpcore.ConnectError("DNS resolved to a prohibited IP address")
            parsed.append(str(ip))
    except ValueError as exc:
        raise httpcore.ConnectError("DNS returned an invalid IP address") from exc
    return list(dict.fromkeys(parsed))


class _DiagnosticStream:
    """Delegate a socket stream while recording only TLS stage and exception class."""

    def __init__(self, stream: httpcore.AsyncNetworkStream) -> None:
        self._stream = stream

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return await self._stream.read(max_bytes, timeout)

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        await self._stream.write(buffer, timeout)

    async def aclose(self) -> None:
        await self._stream.aclose()

    def get_extra_info(self, info: str) -> Any:
        return self._stream.get_extra_info(info)

    async def start_tls(
        self,
        ssl_context: Any,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            secured = await self._stream.start_tls(ssl_context, server_hostname, timeout)
        except Exception as exc:
            logger.warning("Outbound TLS handshake or certificate verification failed (%s)", type(exc).__name__)
            raise
        logger.info("Outbound TLS handshake and certificate verification succeeded")
        return _DiagnosticStream(secured)


class _PinnedNetworkBackend(httpcore.AnyIOBackend):
    def __init__(
        self,
        allowed_hosts: frozenset[str],
        resolver: Resolver = _system_resolve,
        dialer: Dialer | None = None,
    ):
        self._allowed_hosts = allowed_hosts
        self._resolver = resolver
        self._dialer = dialer

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        if host.casefold() not in self._allowed_hosts or port != 443:
            raise httpcore.ConnectError("Outbound destination is not on the approved host allowlist")

        started = time.monotonic()
        try:
            lookup = partial(self._resolver, host, port)
            if timeout is None:
                addresses = await anyio.to_thread.run_sync(lookup, abandon_on_cancel=True)
            else:
                with anyio.fail_after(timeout):
                    addresses = await anyio.to_thread.run_sync(lookup, abandon_on_cancel=True)
        except TimeoutError as exc:
            logger.warning("Approved outbound hostname DNS lookup timed out")
            raise httpcore.ConnectTimeout("DNS resolution timed out") from exc
        except OSError as exc:
            logger.warning("Approved outbound hostname DNS lookup failed (%s)", type(exc).__name__)
            raise httpcore.ConnectError("DNS resolution failed") from exc

        # Reject the entire DNS set when any answer is unsafe. Never retry by
        # hostname: each socket is opened directly to one of these validated IPs.
        try:
            addresses = _public_addresses(addresses)
        except httpcore.ConnectError as exc:
            logger.warning("Outbound DNS answer validation rejected the destination (%s)", type(exc).__name__)
            raise
        families = sorted({f"IPv{ipaddress.ip_address(address).version}" for address in addresses})
        logger.info("Approved outbound hostname resolved to %d validated address(es): %s", len(addresses), ", ".join(families))
        last_error: Exception | None = None
        for address in addresses:
            remaining = None if timeout is None else timeout - (time.monotonic() - started)
            if remaining is not None and remaining <= 0:
                raise httpcore.ConnectTimeout("Connection timed out")
            try:
                if self._dialer is not None:
                    stream = await self._dialer(
                        address, port, remaining, local_address, socket_options
                    )
                else:
                    stream = await super().connect_tcp(
                        host=address,
                        port=port,
                        timeout=remaining,
                        local_address=local_address,
                        socket_options=socket_options,
                    )
                logger.info("Pinned IPv%s TCP connection established", ipaddress.ip_address(address).version)
                return _DiagnosticStream(stream)
            except httpcore.ConnectTimeout as exc:
                logger.warning("Pinned %s TCP connection timed out", f"IPv{ipaddress.ip_address(address).version}")
                last_error = exc
            except httpcore.ConnectError as exc:
                logger.warning(
                    "Pinned %s TCP connection failed (%s: %s)",
                    f"IPv{ipaddress.ip_address(address).version}",
                    type(exc).__name__,
                    str(exc)[:120],
                )
                last_error = exc
        if last_error is not None:
            raise last_error
        raise httpcore.ConnectError("No public GitHub address could be connected")


class PinnedGitHubTransport(httpx.AsyncHTTPTransport):
    """HTTPX transport pinned to DNS-validated addresses for a fixed host allowlist.

    HTTPX retains the URL hostname for the Host header and TLS SNI/certificate
    checks. The httpcore network backend receives only the resolved IP literal.
    Proxy support is absent, redirects are disabled by the caller, and idle
    connections are not pooled so each new request resolves and validates again.
    """

    def __init__(
        self,
        allowed_hosts: set[str] | frozenset[str],
        *,
        resolver: Resolver = _system_resolve,
        dialer: Dialer | None = None,
        verify: bool | Any = True,
    ) -> None:
        self._allowed_hosts = frozenset(host.casefold() for host in allowed_hosts)
        if not self._allowed_hosts:
            raise ValueError("At least one outbound host must be allowed")
        ssl_context = httpx.create_ssl_context(verify=verify, trust_env=False)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context,
            max_connections=4,
            max_keepalive_connections=0,
            keepalive_expiry=0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=_PinnedNetworkBackend(self._allowed_hosts, resolver, dialer),
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host.casefold()
        if request.url.scheme != "https" or host not in self._allowed_hosts:
            raise httpx.UnsupportedProtocol("Only explicitly allowed HTTPS GitHub hosts are supported")
        if request.url.port not in (None, 443):
            raise httpx.UnsupportedProtocol("Only HTTPS port 443 is supported")
        authority = request.url.netloc.decode("ascii").casefold()
        if authority not in {host, f"{host}:443"}:
            raise httpx.UnsupportedProtocol("GitHub URL authority is not supported")
        return await super().handle_async_request(request)


PinnedHostTransport = PinnedGitHubTransport
