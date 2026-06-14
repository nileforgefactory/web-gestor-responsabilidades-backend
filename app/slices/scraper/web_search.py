"""Proveedores de búsqueda web para localizar normativa."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.core.config import Settings
from app.slices.scraper.utils import allowed_domains_list, url_domain_allowed, url_looks_like_pdf

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str | None = None
    snippet: str | None = None


class WebSearchProvider(Protocol):
    async def search(self, query: str, *, max_results: int) -> list[SearchHit]: ...


def build_web_search_provider(
    *,
    http: httpx.AsyncClient,
    settings: Settings,
) -> WebSearchProvider:
    """Cadena de proveedores según configuración."""
    provider = (settings.scraper_search_provider or "duckduckgo").strip().lower()
    allowed = allowed_domains_list(settings.scraper_allowed_domains)
    browser_headers = {
        "User-Agent": settings.scraper_user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    }

    if provider == "tavily" and settings.scraper_tavily_api_key:
        return TavilySearchProvider(
            http=http,
            api_key=settings.scraper_tavily_api_key,
            allowed_domains=allowed,
            headers=browser_headers,
        )

    chain: list[WebSearchProvider] = []
    if provider in ("duckduckgo", "ddgs", "auto"):
        chain.append(DdgsLibraryProvider(allowed_domains=allowed))
    if provider in ("duckduckgo", "html", "auto"):
        chain.append(
            DuckDuckGoHtmlProvider(
                http=http,
                allowed_domains=allowed,
                headers=browser_headers,
            )
        )
    if not chain:
        chain.append(DdgsLibraryProvider(allowed_domains=allowed))
    return ChainedSearchProvider(chain)


def _filter_hits(hits: list[SearchHit], allowed_domains: list[str]) -> list[SearchHit]:
    out: list[SearchHit] = []
    seen: set[str] = set()
    for hit in hits:
        url = hit.url.strip()
        if not url or url in seen:
            continue
        if not url_domain_allowed(url, allowed_domains):
            continue
        if not url_looks_like_pdf(url):
            logger.debug("[SCRAPER] busqueda_omitida_no_pdf url=%s", url)
            continue
        seen.add(url)
        out.append(hit)
    return out


def _unwrap_duckduckgo_redirect(href: str) -> str:
    """Decodifica enlaces intermedios de DuckDuckGo (uddg=)."""
    if "uddg=" in href:
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        uddg = qs.get("uddg", [None])[0]
        if uddg:
            return unquote(uddg)
    if href.startswith("//"):
        return "https:" + href
    return href


def _parse_duckduckgo_html(html: str, *, max_collect: int) -> list[SearchHit]:
    """Extrae enlaces de resultados del HTML lite de DuckDuckGo."""
    hits: list[SearchHit] = []
    seen: set[str] = set()

    link_pattern = re.compile(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>',
        re.IGNORECASE,
    )
    for match in link_pattern.finditer(html):
        href = _unwrap_duckduckgo_redirect(match.group(1))
        title = re.sub(r"<[^>]+>", " ", match.group(2))
        title = re.sub(r"\s+", " ", title).strip() or None
        if href.startswith("http") and href not in seen:
            seen.add(href)
            hits.append(SearchHit(url=href, title=title))
        if len(hits) >= max_collect:
            return hits

    # Fallback: cualquier redirect uddg en la página
    for href in re.findall(r'href="(https?://[^"]*uddg=[^"]+)"', html, re.IGNORECASE):
        url = _unwrap_duckduckgo_redirect(href)
        if url.startswith("http") and url not in seen:
            seen.add(url)
            hits.append(SearchHit(url=url))
        if len(hits) >= max_collect:
            break

    return hits


class ChainedSearchProvider:
    """Prueba proveedores en orden hasta obtener resultados."""

    def __init__(self, providers: list[WebSearchProvider]) -> None:
        self._providers = providers

    async def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        for provider in self._providers:
            hits = await provider.search(query, max_results=max_results)
            if hits:
                return hits
        return []


class DdgsLibraryProvider:
    """Búsqueda vía paquete ``ddgs`` (API interna de DuckDuckGo, más estable que HTML scrape)."""

    def __init__(self, *, allowed_domains: list[str]) -> None:
        self._allowed_domains = allowed_domains

    async def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        logger.debug("[SCRAPER] fase=busqueda_red proveedor=ddgs query=%r", query)

        def _run() -> list[SearchHit]:
            try:
                from ddgs import DDGS
            except ImportError:
                try:
                    from duckduckgo_search import DDGS  # compat legacy
                except ImportError:
                    logger.warning("[SCRAPER] paquete ddgs no instalado")
                    return []

            rows = DDGS().text(query, max_results=max_results)
            hits: list[SearchHit] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                url = row.get("href") or row.get("url")
                if isinstance(url, str) and url.startswith("http"):
                    hits.append(
                        SearchHit(
                            url=url,
                            title=str(row.get("title") or "") or None,
                            snippet=str(row.get("body") or row.get("snippet") or "")[:500] or None,
                        )
                    )
            return hits

        try:
            hits = await asyncio.to_thread(_run)
        except Exception as exc:
            logger.warning("[SCRAPER] ddgs fallo query=%r error=%s", query, exc)
            return []

        filtered = _filter_hits(hits, self._allowed_domains)[:max_results]
        logger.info(
            "[SCRAPER] fase=busqueda_red proveedor=ddgs resultados=%d",
            len(filtered),
        )
        return filtered


class DuckDuckGoHtmlProvider:
    """Respaldo: HTML lite de DuckDuckGo (requiere User-Agent de navegador real)."""

    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        allowed_domains: list[str],
        headers: dict[str, str],
    ) -> None:
        self._http = http
        self._allowed_domains = allowed_domains
        self._headers = headers

    async def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        logger.debug("[SCRAPER] fase=busqueda_red proveedor=duckduckgo_html query=%r", query)
        try:
            response = await self._http.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers=self._headers,
                timeout=httpx.Timeout(30.0, connect=15.0),
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            logger.warning("[SCRAPER] duckduckgo_html fallo query=%r error=%s", query, exc)
            return []

        if response.status_code != 200:
            logger.warning(
                "[SCRAPER] duckduckgo_html status=%s query=%r (posible bloqueo/bot)",
                response.status_code,
                query,
            )
            return []

        hits = _parse_duckduckgo_html(response.text, max_collect=max_results * 2)
        filtered = _filter_hits(hits, self._allowed_domains)[:max_results]
        logger.info(
            "[SCRAPER] fase=busqueda_red proveedor=duckduckgo_html resultados=%d",
            len(filtered),
        )
        return filtered


class TavilySearchProvider:
    """Búsqueda vía API Tavily (requiere SCRAPER_TAVILY_API_KEY)."""

    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        api_key: str,
        allowed_domains: list[str],
        headers: dict[str, str],
    ) -> None:
        self._http = http
        self._api_key = api_key
        self._allowed_domains = allowed_domains
        self._headers = headers

    async def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        logger.debug("[SCRAPER] fase=busqueda_red proveedor=tavily query=%r", query)
        payload: dict = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        }
        if self._allowed_domains:
            payload["include_domains"] = self._allowed_domains

        try:
            response = await self._http.post(
                "https://api.tavily.com/search",
                json=payload,
                headers=self._headers,
                timeout=httpx.Timeout(45.0, connect=15.0),
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            logger.warning("[SCRAPER] tavily fallo query=%r error=%s", query, exc)
            return []

        hits: list[SearchHit] = []
        for row in data.get("results") or []:
            if not isinstance(row, dict):
                continue
            url = row.get("url")
            if isinstance(url, str) and url.startswith("http"):
                hits.append(
                    SearchHit(
                        url=url,
                        title=str(row.get("title") or "") or None,
                        snippet=str(row.get("content") or "")[:500] or None,
                    )
                )

        filtered = _filter_hits(hits, self._allowed_domains)[:max_results]
        logger.info(
            "[SCRAPER] fase=busqueda_red proveedor=tavily resultados=%d",
            len(filtered),
        )
        return filtered
