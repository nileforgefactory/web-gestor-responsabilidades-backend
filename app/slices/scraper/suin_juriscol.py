"""Cliente SUIN-Juriscol: búsqueda oficial y descarga de normas."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from html import unescape
from typing import Any
from urllib.parse import quote, unquote, urlparse, parse_qs

import httpx

from app.core.config import Settings
from app.slices.scraper.web_search import SearchHit

logger = logging.getLogger(__name__)

SUIN_JSON_CONTENT_TYPE = "application/json, text/javascript, */*; q=0.01"
SUIN_DEFAULT_USER = "web"
SUIN_DEFAULT_PASSWD = "dA4qd1uUGLLtM6IK+1xiVQ=="

_TIPO_API: dict[str, str] = {
    "ley": "Leyes",
    "decreto": "Decretos",
    "resolucion": "Resolucion",
    "circular": "Circular",
    "constitucion": "Constitucion",
    "acto": "Acto",
    "acuerdo": "Acuerdo",
}


@dataclass(frozen=True)
class SuinNormQuery:
    """Campos de búsqueda en el formulario de normatividad SUIN."""

    tipo: str
    numero: str | None = None
    anio: str | None = None
    epigrafe: str | None = None
    nombre_codigo: str | None = None


@dataclass(frozen=True)
class SuinDocumentRef:
    """Referencia interna a un documento SUIN."""

    path: str
    title: str | None = None
    view_url: str | None = None


def suin_base_url(settings: Settings) -> str:
    return (settings.scraper_suin_base_url or "https://www.suin-juriscol.gov.co").rstrip("/")


def is_suin_url(url: str, *, settings: Settings | None = None) -> bool:
    """True si la URL pertenece al dominio SUIN-Juriscol."""
    try:
        host = urlparse(url.strip()).netloc.lower()
    except ValueError:
        return False
    if host.startswith("www."):
        host = host[4:]
    base = "suin-juriscol.gov.co"
    if settings is not None:
        try:
            configured = urlparse(suin_base_url(settings)).netloc.lower()
            if configured.startswith("www."):
                configured = configured[4:]
            base = configured or base
        except ValueError:
            pass
    return host == base or host.endswith("." + base)


def url_looks_like_suin_document(url: str, *, settings: Settings | None = None) -> bool:
    """True si la URL apunta a un documento descargable en SUIN."""
    if not is_suin_url(url, settings=settings):
        return False
    path = urlparse(url).path.lower()
    query = urlparse(url).query.lower()
    if "viewdocument.asp" in path:
        return "ruta=" in query or "id=" in query
    if "html2word_generator/convertservice" in path:
        return "justdownload=true" in query or "name=" in query
    if "/ciclopews/ciclope.svc/convertir/pdf/" in path:
        return True
    return path.endswith(".pdf")


def parse_norm_reference(norma: str) -> SuinNormQuery | None:
    """
    Interpreta referencias como ``Ley 599 de 2000`` o ``Decreto 1074 de 2015``.

    Devuelve None si no se reconoce un patrón útil para SUIN.
    """
    text = " ".join(norma.strip().split())
    if not text:
        return None

    lower = text.lower()
    if "constituc" in lower and "1991" in lower:
        return SuinNormQuery(tipo="Constitucion")
    if "constituc" in lower and "1886" in lower:
        return SuinNormQuery(tipo="Constitucion", epigrafe="1886")

    codigo = re.search(
        r"\b(c[oó]digo|estatuto)\s+(?:penal|laboral|comercio|procedimiento|general|disciplinario|"
        r"infancia|polic[ií]a|minero|org[aá]nico|nacional|contencioso|administrativo|"
        r"civil|procesal|sustancias)\b",
        lower,
    )
    if codigo:
        return SuinNormQuery(tipo="", epigrafe=text, nombre_codigo=text)

    match = re.search(
        r"\b(ley|decreto|resoluci[oó]n|circular|acto\s+legislativo|acuerdo)\s+"
        r"(\d+)\s*(?:de|\/|-)\s*(\d{4})\b",
        lower,
        flags=re.IGNORECASE,
    )
    if match:
        tipo_raw = match.group(1).replace("ó", "o")
        tipo_key = tipo_raw.split()[0]
        if tipo_key == "acto":
            tipo_api = "Acto"
        else:
            tipo_api = _TIPO_API.get(tipo_key, "Leyes")
        return SuinNormQuery(
            tipo=tipo_api,
            numero=match.group(2),
            anio=match.group(3),
        )

    return SuinNormQuery(epigrafe=text)


def path_from_suin_url(url: str) -> str | None:
    """Extrae ``Leyes/1663230`` desde una URL ``viewDocument``."""
    parsed = urlparse(url.strip())
    qs = parse_qs(parsed.query)
    ruta = qs.get("ruta", [None])[0]
    if isinstance(ruta, str) and ruta.strip():
        return unquote(ruta.strip())
    doc_id = qs.get("id", [None])[0]
    if isinstance(doc_id, str) and doc_id.strip():
        return f"Leyes/{doc_id.strip()}"
    return None


def build_view_url(base_url: str, path: str) -> str:
    return f"{base_url}/viewDocument.asp?ruta={quote(path, safe='/')}"


def build_canonical_suin_view_url(base_url: str, path: str) -> str:
    """URL canónica ``viewDocument.asp?id=…`` cuando el path es ``Coleccion/123``."""
    parts = path.strip("/").split("/")
    if len(parts) == 2 and parts[1].isdigit():
        return f"{base_url.rstrip('/')}/viewDocument.asp?id={parts[1]}"
    return build_view_url(base_url, path)


def dedupe_suin_search_hits(
    hits: list[SearchHit],
    *,
    settings: Settings,
) -> list[SearchHit]:
    """Unifica ``id=`` y ``ruta=`` del mismo documento; prefiere URL con ``id=``."""
    base = suin_base_url(settings)
    by_path: dict[str, SearchHit] = {}
    passthrough: list[SearchHit] = []

    for hit in hits:
        path = path_from_suin_url(hit.url)
        if not path:
            passthrough.append(hit)
            continue
        key = path.lower()
        prev = by_path.get(key)
        if prev is None or ("id=" in hit.url.lower() and "id=" not in prev.url.lower()):
            by_path[key] = hit

    result: list[SearchHit] = []
    for path_key, hit in by_path.items():
        path = path_from_suin_url(hit.url) or path_key
        canonical_url = build_canonical_suin_view_url(base, path)
        if canonical_url != hit.url:
            logger.info(
                "[SCRAPER] suin_url_canonica original=%s canonica=%s",
                hit.url,
                canonical_url,
            )
        result.append(
            SearchHit(url=canonical_url, title=hit.title, snippet=hit.snippet)
        )
    result.extend(passthrough)
    return result


def suin_hit_is_trusted(norma: str, hit: SearchHit) -> bool:
    """True si es ``viewDocument`` SUIN cuyo título coincide con la norma solicitada."""
    if not _is_suin_view_document_url(hit.url):
        return False
    parsed = parse_norm_reference(norma)
    return _hit_corresponds_to_norm(parsed, hit)


def build_pdf_download_url(base_url: str, file_name: str) -> str:
    return (
        f"{base_url}/HTML2Word_Generator/ConvertService"
        f"?justDownload=true&name={quote(file_name, safe='')}"
    )


class SuinJuriscolClient:
    """Consulta SUIN-Juriscol antes que la búsqueda web genérica."""

    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        settings: Settings,
    ) -> None:
        self._http = http
        self.settings = settings
        self.base_url = suin_base_url(settings)
        self.ws_url = f"{self.base_url}/CiclopeWs/Ciclope.svc"

    async def search(self, norma: str, *, max_results: int) -> list[SearchHit]:
        if not self.settings.scraper_suin_enabled:
            return []

        hits: list[SearchHit] = []
        seen: set[str] = set()
        parsed = parse_norm_reference(norma)

        if self.settings.scraper_suin_primary_web_search:
            for hit in await self._search_norma_suin_web(
                norma, parsed=parsed, max_results=max_results
            ):
                if hit.url in seen:
                    continue
                seen.add(hit.url)
                hits.append(hit)
                if len(hits) >= max_results:
                    logger.info(
                        "[SCRAPER] norma=%r fase=busqueda_suin_web enlaces=%d",
                        norma,
                        len(hits),
                    )
                    return dedupe_suin_search_hits(hits, settings=self.settings)[:max_results]

        if not hits and parsed is not None and self.settings.scraper_suin_use_find_api:
            for hit in await self._search_find_api(parsed, max_results=max_results):
                if hit.url in seen:
                    continue
                seen.add(hit.url)
                hits.append(hit)
                if len(hits) >= max_results:
                    break

        if not hits and self.settings.scraper_suin_fallback_site_search:
            for hit in await self._search_site_index(norma, max_results=max_results):
                if hit.url in seen:
                    continue
                seen.add(hit.url)
                hits.append(hit)
                if len(hits) >= max_results:
                    break

        if hits:
            logger.info(
                "[SCRAPER] norma=%r fase=busqueda_suin enlaces=%d",
                norma,
                len(hits),
            )
        hits = dedupe_suin_search_hits(hits, settings=self.settings)
        return hits[:max_results]

    async def _search_norma_suin_web(
        self,
        norma: str,
        *,
        parsed: SuinNormQuery | None,
        max_results: int,
    ) -> list[SearchHit]:
        """
        Búsqueda principal: ``{norma} suin`` en el índice web (como en el navegador).

        Solo acepta enlaces ``viewDocument`` de SUIN cuyo título coincide con la norma.
        """
        text = norma.strip()
        if not text:
            return []

        queries = [
            f"{text} suin",
            f'"{text}" suin',
        ]
        hits: list[SearchHit] = []
        seen: set[str] = set()
        for query in queries:
            logger.info(
                "[SCRAPER] norma=%r fase=busqueda_suin_web query=%r",
                norma,
                query,
            )
            batch = await asyncio.to_thread(
                self._ddg_norma_suin_search, query, max_results
            )
            for hit in batch:
                if hit.url in seen:
                    continue
                if not _is_suin_view_document_hit(hit):
                    logger.info(
                        "[SCRAPER] norma=%r suin_web_omitido no_viewDocument url=%s",
                        norma,
                        hit.url,
                    )
                    continue
                if not _hit_corresponds_to_norm(parsed, hit):
                    logger.info(
                        "[SCRAPER] norma=%r suin_web_omitido titulo_no_coincide url=%s title=%r",
                        norma,
                        hit.url,
                        hit.title,
                    )
                    continue
                seen.add(hit.url)
                hits.append(hit)
                logger.info(
                    "[SCRAPER] norma=%r fase=busqueda_suin_web hit fuente=suin_viewdocument "
                    "url=%s titulo=%r",
                    norma,
                    hit.url,
                    hit.title,
                )
            if hits:
                break

        return self._rank_hits(hits, parsed)[:max_results]

    async def _search_find_api(
        self,
        parsed: SuinNormQuery,
        *,
        max_results: int,
    ) -> list[SearchHit]:
        query: dict[str, Any] = {
            "form": "normatividad",
            "hitlist": "legis",
            "coleccion": "legis",
            "fields": "tipo|numero|anio|sector|entidad_emisora|estado_documento|epigrafe",
            "pageSize": max(20, max_results),
            "usuario": self.settings.scraper_suin_user or SUIN_DEFAULT_USER,
            "passwd": self.settings.scraper_suin_passwd or SUIN_DEFAULT_PASSWD,
        }
        if parsed.tipo:
            query["tipo"] = parsed.tipo
        if parsed.numero:
            query["numero"] = parsed.numero
        if parsed.anio:
            query["anio_desde"] = parsed.anio
            query["anio_hasta"] = parsed.anio
        if parsed.epigrafe:
            query["epigrafe"] = parsed.epigrafe
        if parsed.nombre_codigo:
            query["nombre_codigo"] = parsed.nombre_codigo

        data = await self._post_find(query)
        if not data or data.get("error"):
            if data and data.get("error"):
                logger.debug(
                    "[SCRAPER] suin_find_api error=%s",
                    data.get("error"),
                )
            return []

        docs = data.get("docs") or []
        hits: list[SearchHit] = []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            path = doc.get("path")
            if not isinstance(path, str) or not path.strip():
                continue
            view_url = build_view_url(self.base_url, path.strip())
            if _is_suin_jurisprudence_url(view_url):
                continue
            title = _doc_title(doc)
            hits.append(
                SearchHit(
                    url=build_view_url(self.base_url, path.strip()),
                    title=title,
                    snippet=_doc_snippet(doc),
                )
            )
        return self._rank_hits(hits, parsed)[:max_results]

    async def _post_find(self, query: dict[str, Any]) -> dict[str, Any] | None:
        headers = {
            "User-Agent": self.settings.scraper_user_agent,
            "Content-Type": "json",
            "Accept": SUIN_JSON_CONTENT_TYPE,
            "Referer": f"{self.base_url}/legislacion/normatividad.html",
            "Origin": self.base_url,
        }
        try:
            response = await self._request_post(
                f"{self.ws_url}/Find",
                content=json.dumps(query),
                headers=headers,
            )
        except httpx.HTTPError as exc:
            logger.warning("[SCRAPER] suin_find_api fallo_red error=%s", exc)
            return None

        if response.status_code != 200:
            logger.warning(
                "[SCRAPER] suin_find_api status=%s",
                response.status_code,
            )
            return None

        try:
            payload = response.json()
        except ValueError:
            logger.warning("[SCRAPER] suin_find_api respuesta_no_json")
            return None
        return payload if isinstance(payload, dict) else None

    async def _search_site_index(
        self,
        norma: str,
        *,
        max_results: int,
    ) -> list[SearchHit]:
        queries = [
            f'site:suin-juriscol.gov.co viewDocument "{norma.strip()}"',
            f"site:suin-juriscol.gov.co viewDocument {norma.strip()}",
        ]
        hits: list[SearchHit] = []
        seen: set[str] = set()
        parsed = parse_norm_reference(norma)
        for query in queries:
            batch = await asyncio.to_thread(self._ddg_site_search, query, max_results)
            for hit in batch:
                if hit.url in seen:
                    continue
                if not _hit_corresponds_to_norm(parsed, hit):
                    continue
                seen.add(hit.url)
                hits.append(hit)
            if hits:
                break
        return self._rank_hits(hits, parsed)[:max_results]

    def _ddg_norma_suin_search(self, query: str, max_results: int) -> list[SearchHit]:
        return self._ddg_web_search(query, max_results, require_view_document=True)

    def _ddg_site_search(self, query: str, max_results: int) -> list[SearchHit]:
        return self._ddg_web_search(query, max_results, require_view_document=True)

    def _ddg_web_search(
        self,
        query: str,
        max_results: int,
        *,
        require_view_document: bool,
    ) -> list[SearchHit]:
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                logger.warning("[SCRAPER] suin_web_search paquete ddgs no instalado")
                return []

        rows = DDGS().text(query, max_results=max_results * 3)
        hits: list[SearchHit] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = row.get("href") or row.get("url")
            if not isinstance(url, str) or not url.startswith("http"):
                continue
            if not is_suin_url(url, settings=self.settings):
                continue
            if require_view_document and not _is_suin_view_document_url(
                url, settings=self.settings
            ):
                continue
            if not url_looks_like_suin_document(url, settings=self.settings):
                continue
            if _is_suin_jurisprudence_url(url):
                continue
            title = str(row.get("title") or "") or None
            hits.append(
                SearchHit(
                    url=url,
                    title=title,
                    snippet=str(row.get("body") or row.get("snippet") or "")[:500] or None,
                )
            )
        return hits

    def _rank_hits(
        self,
        hits: list[SearchHit],
        parsed: SuinNormQuery | None,
    ) -> list[SearchHit]:
        if not hits or parsed is None:
            return hits

        def score(hit: SearchHit) -> tuple[int, int]:
            blob = " ".join(
                part for part in (hit.title, hit.snippet, hit.url) if part
            ).lower()
            points = 0
            if _title_matches_norm(parsed, hit.title):
                points += 12
            elif parsed.numero and re.search(rf"\b{re.escape(parsed.numero)}\b", blob):
                points += 3
            if parsed.anio and parsed.anio in blob:
                points += 4
            if parsed.tipo and parsed.tipo.lower() in blob:
                points += 2
            if parsed.epigrafe and parsed.epigrafe.lower()[:24] in blob:
                points += 2
            path = path_from_suin_url(hit.url) or ""
            path_lower = path.lower()
            if path_lower.startswith("leyes/"):
                points += 3
            elif path_lower.startswith("decretos/"):
                points += 3
            elif path_lower.startswith("constitucion/"):
                points += 3
            if _is_suin_jurisprudence_url(hit.url):
                points -= 8
            if hit.title and parsed.numero and parsed.anio:
                title_lower = hit.title.lower()
                other = re.search(
                    r"\b(ley|decreto|resoluci[oó]n|circular)\s+(\d+)\s*(?:de|\/|-)\s*(\d{4})\b",
                    title_lower,
                )
                if (
                    other
                    and other.group(2) != parsed.numero
                    and other.group(3) == parsed.anio
                ):
                    points -= 6
            return (points, len(blob))

        return sorted(hits, key=score, reverse=True)

    async def resolve_document_ref(self, url: str) -> SuinDocumentRef | None:
        path = path_from_suin_url(url)
        if not path:
            return None
        return SuinDocumentRef(
            path=path,
            view_url=build_view_url(self.base_url, path),
        )

    async def fetch_pdf_url(self, doc: SuinDocumentRef) -> str | None:
        """Genera PDF vía Ciclope y devuelve URL de descarga, si el servicio responde."""
        title = (doc.title or doc.path.replace("/", "_")).replace(" ", "_")
        safe_title = quote(title.replace("/", "-"), safe="")
        convert_url = f"{self.ws_url}/Convertir/pdf/{safe_title}/{doc.path}"
        payload = {
            "usuario": self.settings.scraper_suin_user or SUIN_DEFAULT_USER,
            "passwd": self.settings.scraper_suin_passwd or SUIN_DEFAULT_PASSWD,
        }
        headers = {
            "User-Agent": self.settings.scraper_user_agent,
            "Content-Type": "json",
            "Accept": SUIN_JSON_CONTENT_TYPE,
        }
        try:
            response = await self._request_post(
                convert_url,
                content=json.dumps(payload),
                headers=headers,
            )
        except httpx.HTTPError as exc:
            logger.debug("[SCRAPER] suin_convert_pdf fallo_red error=%s", exc)
            return None

        if response.status_code != 200 or not response.content:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        file_name = data.get("fileName") if isinstance(data, dict) else None
        if not isinstance(file_name, str) or not file_name.strip():
            return None
        return build_pdf_download_url(self.base_url, file_name.strip())

    async def fetch_view_html(self, doc: SuinDocumentRef) -> str:
        view_url = doc.view_url or build_view_url(self.base_url, doc.path)
        response = await self._request_get(
            view_url,
            headers={"User-Agent": self.settings.scraper_user_agent},
        )
        response.raise_for_status()
        return response.text

    async def _request_get(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
        verify = self.settings.scraper_fetch_verify_ssl
        try:
            return await self._http.get(
                url,
                headers=headers,
                timeout=httpx.Timeout(self.settings.scraper_fetch_timeout_sec, connect=20.0),
                follow_redirects=True,
            )
        except httpx.HTTPError:
            if (
                self.settings.scraper_fetch_ssl_fallback
                and verify
            ):
                async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
                    return await client.get(
                        url,
                        headers=headers,
                        timeout=httpx.Timeout(
                            self.settings.scraper_fetch_timeout_sec, connect=20.0
                        ),
                    )
            raise

    async def _request_post(
        self,
        url: str,
        *,
        content: str,
        headers: dict[str, str],
    ) -> httpx.Response:
        verify = self.settings.scraper_fetch_verify_ssl
        timeout = httpx.Timeout(self.settings.scraper_fetch_timeout_sec, connect=20.0)
        try:
            return await self._http.post(
                url,
                content=content,
                headers=headers,
                timeout=timeout,
                follow_redirects=True,
            )
        except httpx.HTTPError:
            if self.settings.scraper_fetch_ssl_fallback and verify:
                async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
                    return await client.post(
                        url,
                        content=content,
                        headers=headers,
                        timeout=timeout,
                    )
            raise


def extract_suin_html_text(html: str) -> str:
    """Extrae metadatos y texto completo de ``viewDocument.asp`` (página SUIN oficial)."""
    sections: list[str] = []

    title_match = re.search(r"(?is)<title[^>]*>([^<]+)</title>", html)
    if title_match:
        title = unescape(re.sub(r"\s+", " ", title_match.group(1))).strip()
        if title:
            title = title.split("|")[0].strip()
            sections.append(f"Título: {title}")

    meta_lines = _extract_suin_metadata_lines(html)
    sections.extend(meta_lines)

    body_html = _extract_suin_main_html(html)
    body_text = _html_fragment_to_text(body_html)

    if sections:
        header = "\n".join(sections)
        if body_text:
            return f"{header}\n\n{body_text}".strip()
        return header.strip()
    return body_text


def _extract_suin_metadata_lines(html: str) -> list[str]:
    """Campos ficha normativa (tablas y pares etiqueta/valor en SUIN)."""
    labels = (
        "Tipo",
        "Número",
        "Numero",
        "Año",
        "Anio",
        "Epígrafe",
        "Epigrafe",
        "Estado",
        "Entidad emisora",
        "Sector",
        "Fecha de expedición",
        "Fecha de publicación",
        "Diario oficial",
        "Vigencia",
    )
    found: list[str] = []
    seen: set[str] = set()
    label_alt = "|".join(re.escape(lb) for lb in labels)
    for match in re.finditer(
        rf"(?is)(?:<t[hd][^>]*>\s*)?({label_alt})\s*(?:</t[hd]>\s*<t[hd][^>]*>|:)\s*"
        rf"([^<\n]+)",
        html,
    ):
        key = re.sub(r"\s+", " ", unescape(match.group(1))).strip()
        val = re.sub(r"\s+", " ", unescape(match.group(2))).strip()
        if not val or len(val) > 400:
            continue
        line = f"{key}: {val}"
        if line.lower() not in seen:
            seen.add(line.lower())
            found.append(line)
    return found


def _extract_suin_main_html(html: str) -> str:
    """Intenta aislar el cuerpo normativo antes de convertir a texto plano."""
    patterns = (
        r'(?is)<div[^>]+id=["\']?(?:contenido|documento|texto|docum)[^"\']*["\']?[^>]*>'
        r"([\s\S]*?)</div>",
        r'(?is)<div[^>]+class=["\'][^"\']*(?:contenido|documento|texto)[^"\']*["\'][^>]*>'
        r"([\s\S]*?)</div>",
        r"(?is)<article[^>]*>([\s\S]*?)</article>",
    )
    for pattern in patterns:
        match = re.search(pattern, html)
        if match and len(match.group(1)) > 400:
            return match.group(1)
    return html


def _html_fragment_to_text(html: str) -> str:
    cleaned = re.sub(r"(?is)<script[\s\S]*?</script>", " ", html)
    cleaned = re.sub(r"(?is)<style[\s\S]*?</style>", " ", cleaned)
    cleaned = re.sub(r"(?is)<head[\s\S]*?</head>", " ", cleaned)
    text = re.sub(r"<[^>]+>", "\n", cleaned)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    lines = [ln.strip() for ln in text.splitlines()]
    compact: list[str] = []
    for ln in lines:
        if not ln:
            if compact and compact[-1] != "":
                compact.append("")
            continue
        if _is_suin_chrome_line(ln):
            continue
        compact.append(ln)
    joined = "\n".join(compact)
    return re.sub(r"\n{3,}", "\n\n", joined).strip()


def _is_suin_chrome_line(line: str) -> bool:
    lower = line.lower()
    noise = (
        "google-analytics",
        "gtag(",
        "dataLayer",
        "cookiesession",
        "responder encuesta",
        "lectura de voz",
        "inscripciones abiertas",
        "curso suin-juriscol",
        "ayúdanos a mejorar",
        "compartir este documento",
        "descargar en word",
        "guardar en pdf",
        "ir al portal suin-juriscol",
    )
    return any(token in lower for token in noise)


def _trim_suin_boilerplate(text: str) -> str:
    """Reservado; ya no recorta metadatos del encabezado SUIN."""
    return text.strip()


def _is_suin_view_document_url(url: str, *, settings: Settings | None = None) -> bool:
    """True si la URL es un ``viewDocument`` de SUIN (no PDF ni jurisprudencia)."""
    if not is_suin_url(url, settings=settings):
        return False
    path = urlparse(url).path.lower()
    return "viewdocument" in path


def _is_suin_view_document_hit(hit: SearchHit) -> bool:
    return _is_suin_view_document_url(hit.url)


def scraper_hit_source(url: str, *, settings: Settings | None = None) -> str:
    """Etiqueta legible para logs: origen del enlace candidato."""
    if _is_suin_view_document_url(url, settings=settings):
        return "suin_viewdocument"
    if is_suin_url(url, settings=settings):
        return "suin_otro"
    from app.slices.scraper.utils import url_looks_like_pdf

    if url_looks_like_pdf(url):
        return "pdf"
    return "web"


def sort_scraper_hits_prioritize_suin(
    hits: list[SearchHit],
    *,
    settings: Settings | None = None,
) -> list[SearchHit]:
    """Ordena candidatos: ``viewDocument`` SUIN primero, luego otros SUIN, luego PDF/web."""

    def priority(hit: SearchHit) -> tuple[int, str]:
        source = scraper_hit_source(hit.url, settings=settings)
        order = {
            "suin_viewdocument": 0,
            "suin_otro": 1,
            "pdf": 2,
            "web": 3,
        }
        return (order.get(source, 9), hit.url)

    return sorted(hits, key=priority)


def _hit_corresponds_to_norm(parsed: SuinNormQuery | None, hit: SearchHit) -> bool:
    """True si el resultado parece ser el documento normativo solicitado."""
    if parsed is None:
        return True
    if parsed.numero and parsed.anio:
        if _title_matches_norm(parsed, hit.title):
            return True
        # Rechazar otro número/año explícito en el título (p. ej. Ley 1150 de 2008).
        if hit.title:
            title_lower = hit.title.lower()
            other = re.search(
                r"\b(ley|decreto|resoluci[oó]n|circular)\s+(\d+)\s*(?:de|\/|-)\s*(\d{4})\b",
                title_lower,
            )
            if other and (
                other.group(2) != parsed.numero or other.group(3) != parsed.anio
            ):
                return False
        return False
    if parsed.epigrafe:
        epigrafe = parsed.epigrafe.lower()[:32]
        blob = " ".join(part for part in (hit.title, hit.snippet) if part).lower()
        return epigrafe in blob
    return True


def _title_matches_norm(parsed: SuinNormQuery, title: str | None) -> bool:
    if not title or not parsed.numero or not parsed.anio:
        return False
    title_norm = " ".join(title.lower().split())
    patterns = [
        rf"\bley\s+{re.escape(parsed.numero)}\s+de\s+{re.escape(parsed.anio)}\b",
        rf"\bdecreto\s+{re.escape(parsed.numero)}\s+de\s+{re.escape(parsed.anio)}\b",
        rf"\bresoluci[oó]n\s+{re.escape(parsed.numero)}\s+de\s+{re.escape(parsed.anio)}\b",
        rf"\bcircular\s+{re.escape(parsed.numero)}\s+de\s+{re.escape(parsed.anio)}\b",
    ]
    return any(re.search(pattern, title_norm) for pattern in patterns)


def _is_suin_jurisprudence_url(url: str) -> bool:
    path = (path_from_suin_url(url) or urlparse(url).path).lower()
    blocked = (
        "corteconstitucional/",
        "consejodeestado/",
        "cortesuprema/",
        "jurisprudencia/",
    )
    return any(token in path for token in blocked)


def _doc_title(doc: dict[str, Any]) -> str | None:
    for key in ("title", "homeTitle", "epigrafe"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    fields = doc.get("fields")
    if isinstance(fields, list):
        parts: list[str] = []
        for field in fields[:3]:
            if isinstance(field, dict):
                val = field.get("value")
                if isinstance(val, str) and val.strip():
                    parts.append(val.strip())
        if parts:
            return " ".join(parts)
    return None


def _doc_snippet(doc: dict[str, Any]) -> str | None:
    for key in ("epigrafe", "title"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:500]
    return None
