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


def _root_cause(exc: BaseException) -> BaseException:
    current: BaseException = exc
    while current.__cause__ is not None:
        current = current.__cause__
    return current


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
    info = classify_http_error(exc)
    return info.kind in {
        NetworkErrorKind.TIMEOUT,
        NetworkErrorKind.SSL,
        NetworkErrorKind.NETWORK,
        NetworkErrorKind.HTTP_SERVER,
    }
