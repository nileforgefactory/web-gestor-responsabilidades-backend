"""Clasificación de errores HTTP/red para logs concisos."""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from enum import Enum

import httpx


class NetworkErrorKind(str, Enum):
    TIMEOUT = "timeout"
    SSL = "ssl"
    DNS = "dns"
    HTTP_CLIENT = "http_4xx"
    HTTP_SERVER = "http_5xx"
    NETWORK = "network"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class NetworkErrorInfo:
    kind: NetworkErrorKind
    message: str
    retryable: bool


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    """Recorre ``__cause__`` y ``__context__`` (excepciones encadenadas)."""
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def _root_cause(exc: BaseException) -> BaseException:
    chain = _iter_exception_chain(exc)
    return chain[-1] if chain else exc


def classify_http_error(exc: BaseException) -> NetworkErrorInfo:
    """Resume un error httpx/httpcore en tipo + mensaje corto para logs."""
    root = _root_cause(exc)
    text = str(root) or type(root).__name__

    if isinstance(root, httpx.TimeoutException):
        return NetworkErrorInfo(
            kind=NetworkErrorKind.TIMEOUT,
            message=text,
            retryable=True,
        )

    if isinstance(root, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in text:
        return NetworkErrorInfo(
            kind=NetworkErrorKind.SSL,
            message=text,
            retryable=True,
        )

    if "Name or service not known" in text or "Temporary failure in name resolution" in text:
        return NetworkErrorInfo(
            kind=NetworkErrorKind.DNS,
            message=text,
            retryable=False,
        )

    if isinstance(root, httpx.HTTPStatusError):
        code = root.response.status_code
        if 400 <= code < 500:
            return NetworkErrorInfo(
                kind=NetworkErrorKind.HTTP_CLIENT,
                message=f"HTTP {code}",
                retryable=False,
            )
        return NetworkErrorInfo(
            kind=NetworkErrorKind.HTTP_SERVER,
            message=f"HTTP {code}",
            retryable=True,
        )

    if isinstance(root, (httpx.ConnectError, httpx.ReadError, httpx.WriteError, OSError)):
        return NetworkErrorInfo(
            kind=NetworkErrorKind.NETWORK,
            message=text,
            retryable=True,
        )

    return NetworkErrorInfo(
        kind=NetworkErrorKind.UNKNOWN,
        message=text or type(root).__name__,
        retryable=False,
    )


def is_transient_network_error(exc: BaseException) -> bool:
    """True si el error es de red/timeout y conviene reintentar o continuar sin traceback."""
    for link in _iter_exception_chain(exc):
        if link.__class__.__name__ == "ResponseHandlingException":
            info = classify_http_error(link)
            if info.retryable:
                return True
        if isinstance(
            link,
            (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.ReadError,
                httpx.WriteError,
                OSError,
            ),
        ):
            return True

    info = classify_http_error(exc)
    return info.kind in {
        NetworkErrorKind.TIMEOUT,
        NetworkErrorKind.SSL,
        NetworkErrorKind.NETWORK,
        NetworkErrorKind.HTTP_SERVER,
    }
