"""Orquestación: búsqueda web → descarga → validación IA → indexación RAG."""

from __future__ import annotations

import asyncio
import logging
from typing import cast

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import mysql_available, session_scope
from app.slices.conocimiento import repository as conocimiento_repo
from app.slices.conocimiento.schemas import (
    ConocimientoCreate,
    ConocimientoUpdate,
    TipoDocumento,
)
from app.slices.rag.ollama_client import OllamaError
from app.slices.rag.service import RagService
from app.slices.common.network_errors import classify_http_error, is_transient_network_error
from app.slices.common.territorio import (
    apply_pais_scope,
    collection_id_from_territorio,
    normalize_territorio,
    resolve_scraper_pais,
)
from app.slices.scraper.fetcher import fetch_and_extract
from app.slices.scraper.schemas import (
    NormaScraperResultado,
    ScraperBuscarResponse,
    ScraperResumen,
    ValidacionNormaOut,
)
from app.slices.scraper.utils import (
    build_search_query_variants,
    derive_document_id,
    infer_tipo_norma,
)
from app.slices.scraper.suin_juriscol import (
    SuinJuriscolClient,
    dedupe_suin_search_hits,
    scraper_hit_source,
    sort_scraper_hits_prioritize_suin,
    suin_hit_is_trusted,
)
from app.slices.scraper.validator import ValidationResult, validate_norm_document
from app.slices.scraper.web_search import SearchHit, build_web_search_provider

logger = logging.getLogger(__name__)


class ScraperService:
    """Busca normas en internet, valida con LLM e indexa en Qdrant."""

    def __init__(
        self,
        *,
        settings: Settings,
        rag: RagService,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.rag = rag
        self._http = http or rag.http
        self._search = build_web_search_provider(http=self._http, settings=settings)
        self._suin = SuinJuriscolClient(http=self._http, settings=settings)

    async def buscar_normas(
        self,
        normas: list[str],
        *,
        pais: str | None = None,
    ) -> ScraperBuscarResponse:
        """
        Procesa las normas en paralelo (asyncio) con límite de concurrencia.

        Cada norma usa su propia sesión MySQL cuando el catálogo está activo.
        """
        pais_efectivo = resolve_scraper_pais(
            pais, default=self.settings.scraper_default_pais
        )
        items: list[tuple[int, str, str | None]] = []
        for idx, raw in enumerate(normas):
            nombre = raw.strip() or None
            items.append((idx, raw, nombre))

        concurrencia = min(
            max(1, self.settings.scraper_max_concurrency),
            max(1, len(items)),
        )
        sem = asyncio.Semaphore(concurrencia)

        logger.info(
            "[SCRAPER] lote normas=%d pais=%s concurrencia=%d (paralelo asyncio)",
            len(items),
            pais_efectivo,
            concurrencia,
        )

        async def run_indexed(
            index: int, raw: str, nombre: str | None
        ) -> tuple[int, NormaScraperResultado]:
            if not nombre:
                return index, NormaScraperResultado(
                    norma=raw,
                    estado="error",
                    motivo="Referencia vacía.",
                )
            async with sem:
                try:
                    if mysql_available():
                        async with session_scope() as db:
                            resultado = await self._procesar_norma(
                                nombre, db=db, pais=pais_efectivo
                            )
                    else:
                        resultado = await self._procesar_norma(
                            nombre, db=None, pais=pais_efectivo
                        )
                    return index, resultado
                except Exception as exc:
                    logger.exception(
                        "[SCRAPER] norma=%r error_no_controlado", nombre
                    )
                    return index, NormaScraperResultado(
                        norma=nombre,
                        estado="error",
                        motivo=f"Error inesperado: {exc}",
                    )

        pairs = await asyncio.gather(
            *(run_indexed(idx, raw, nombre) for idx, raw, nombre in items)
        )
        pairs.sort(key=lambda p: p[0])
        resultados = [r for _, r in pairs]

        return ScraperBuscarResponse(
            resumen=ScraperResumen(
                solicitadas=len(resultados),
                indexadas=sum(1 for r in resultados if r.estado == "indexada"),
                no_encontradas=sum(1 for r in resultados if r.estado == "no_encontrada"),
                no_indexadas=sum(1 for r in resultados if r.estado == "no_indexada"),
                errores=sum(1 for r in resultados if r.estado == "error"),
                pais=pais_efectivo,
                concurrencia=concurrencia,
            ),
            resultados=resultados,
        )

    async def _procesar_norma(
        self,
        norma: str,
        *,
        db: AsyncSession | None,
        pais: str,
    ) -> NormaScraperResultado:
        logger.info("[SCRAPER] norma=%r pais=%s fase=inicio", norma, pais)
        urls_intentadas: list[str] = []
        ultima_validacion: ValidacionNormaOut | None = None
        ultimo_motivo: str | None = None

        try:
            hits = await self._buscar_en_red(norma, pais=pais)
        except Exception as exc:
            logger.exception("[SCRAPER] norma=%r error busqueda_red", norma)
            return NormaScraperResultado(
                norma=norma,
                estado="error",
                motivo=f"Error en búsqueda web: {exc}",
            )

        if not hits:
            logger.info("[SCRAPER] norma=%r fase=fin estado=no_encontrada", norma)
            motivo = "No se encontró la norma en SUIN-Juriscol (búsqueda web) ni en la búsqueda de PDFs."
            if db is not None:
                await self._registrar_catalogo_fallo(
                    db,
                    norma=norma,
                    territorio=[pais, None, None],
                    motivo=motivo,
                )
            return NormaScraperResultado(
                norma=norma,
                estado="no_encontrada",
                motivo=motivo,
                coleccion_id=collection_id_from_territorio([pais, None, None]),
                territorio=[pais, None, None],
            )

        total_candidatos = len(hits)
        for orden, hit in enumerate(hits, start=1):
            fuente = scraper_hit_source(hit.url, settings=self.settings)
            logger.info(
                "[SCRAPER] norma=%r fase=procesando_url orden=%d/%d fuente=%s url=%s titulo=%r",
                norma,
                orden,
                total_candidatos,
                fuente,
                hit.url,
                hit.title,
            )
            urls_intentadas.append(hit.url)
            indexado, validacion, motivo = await self._evaluar_candidato(
                norma, hit, db=db, pais=pais
            )
            if validacion is not None:
                ultima_validacion = validacion
            if motivo:
                ultimo_motivo = motivo
            if indexado is not None:
                return indexado

        logger.info("[SCRAPER] norma=%r fase=fin estado=no_indexada", norma)
        motivo = (
            ultimo_motivo
            or "Se encontraron enlaces pero ninguno pasó la validación o no tenía texto utilizable."
        )
        territorio_fallo = (
            ultima_validacion.territorio if ultima_validacion is not None else [pais, None, None]
        )
        territorio_fallo, _ = apply_pais_scope(territorio_fallo, pais)
        coleccion_fallo = collection_id_from_territorio(territorio_fallo)
        if db is not None:
            await self._registrar_catalogo_fallo(
                db,
                norma=norma,
                territorio=territorio_fallo,
                motivo=motivo,
                url=urls_intentadas[-1] if urls_intentadas else None,
            )
        return NormaScraperResultado(
            norma=norma,
            estado="no_indexada",
            motivo=motivo,
            urls_intentadas=urls_intentadas,
            validacion=ultima_validacion,
            coleccion_id=coleccion_fallo,
            territorio=territorio_fallo,
        )

    async def _evaluar_candidato(
        self,
        norma: str,
        hit: SearchHit,
        *,
        db: AsyncSession | None,
        pais: str,
    ) -> tuple[NormaScraperResultado | None, ValidacionNormaOut | None, str | None]:
        """
        Returns:
            (resultado indexado, None, None) si indexó;
            (None, validacion, motivo_fallo) si no.
        """
        logger.debug("[SCRAPER] norma=%r fase=candidato url=%s", norma, hit.url)
        try:
            fetched = await fetch_and_extract(
                hit.url,
                http=self._http,
                settings=self.settings,
            )
        except httpx.HTTPError as exc:
            info = classify_http_error(exc)
            logger.warning(
                "[SCRAPER] norma=%r descarga_fallo url=%s tipo=%s",
                norma,
                hit.url,
                info.kind.value,
            )
            return None, None, f"No se pudo descargar {hit.url} ({info.kind.value}): {info.message}"
        except ValueError as exc:
            logger.warning(
                "[SCRAPER] norma=%r extraccion_fallo url=%s error=%s", norma, hit.url, exc
            )
            return None, None, str(exc)
        except Exception as exc:
            logger.warning(
                "[SCRAPER] norma=%r extraccion_fallo url=%s error=%s", norma, hit.url, exc
            )
            return None, None, f"Error al extraer {hit.url}: {exc}"

        logger.info(
            "[SCRAPER] norma=%r fase=extraccion_ok fuente=%s url=%s chars=%d metodo=%s",
            norma,
            scraper_hit_source(hit.url, settings=self.settings),
            hit.url,
            fetched.char_count,
            fetched.extraction_method,
        )

        trusted_suin = suin_hit_is_trusted(norma, hit)
        if trusted_suin:
            logger.info(
                "[SCRAPER] norma=%r fase=validacion_suin confianza=alta url=%s "
                "(título coincide; se ingiere página SUIN sin LLM)",
                norma,
                hit.url,
            )
            pais_objetivo = resolve_scraper_pais(pais)
            validation = ValidationResult(
                outcome=ValidacionNormaOut(
                    es_documento_esperado=True,
                    confianza=0.95,
                    codigo_detectado=norma,
                    motivo="Documento oficial SUIN-Juriscol; título coincide con la norma solicitada.",
                    advertencias=[],
                    territorio=normalize_territorio([pais_objetivo, None, None]),
                ),
                accepted=True,
            )
        else:
            try:
                validation = await validate_norm_document(
                    http=self._http,
                    settings=self.settings,
                    norma_solicitada=norma,
                    texto=fetched.text,
                    url=hit.url,
                    titulo_resultado=hit.title,
                    pais_esperado=pais,
                    extraction_method=fetched.extraction_method,
                )
            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, OllamaError) as exc:
                info = classify_http_error(exc)
                logger.error(
                    "[SCRAPER] norma=%r validacion_llm_fallo url=%s tipo=%s error=%s",
                    norma,
                    hit.url,
                    info.kind.value,
                    info.message,
                )
                return (
                    None,
                    None,
                    f"Validación IA no disponible ({info.kind.value}): {info.message}",
                )
            except httpx.HTTPStatusError as exc:
                info = classify_http_error(exc)
                logger.error(
                    "[SCRAPER] norma=%r validacion_llm_fallo url=%s tipo=%s error=%s",
                    norma,
                    hit.url,
                    info.kind.value,
                    info.message,
                )
                return None, None, f"Error HTTP en validación IA: {info.message}"
            except Exception as exc:
                logger.exception(
                    "[SCRAPER] norma=%r validacion_error_inesperado url=%s", norma, hit.url
                )
                return None, None, f"Error inesperado en validación IA: {exc}"

        val_out = validation.outcome
        territorio, scope_warnings = apply_pais_scope(val_out.territorio, pais)
        if territorio != val_out.territorio or scope_warnings:
            val_out = val_out.model_copy(
                update={
                    "territorio": territorio,
                    "advertencias": [*val_out.advertencias, *scope_warnings],
                }
            )

        if not validation.accepted:
            motivo = val_out.motivo or "El documento no coincide con la norma solicitada."
            return None, val_out, motivo

        document_id = derive_document_id(norma)
        collection_id = collection_id_from_territorio(val_out.territorio)

        catalog_id: str | None = None
        if db is not None:
            try:
                catalog_id = await self._registrar_catalogo_pendiente(
                    db,
                    norma=norma,
                    document_id=document_id,
                    collection_id=collection_id,
                    url=hit.url,
                    territorio=val_out.territorio,
                )
            except Exception as exc:
                logger.warning(
                    "[SCRAPER] norma=%r catalogo_mysql_fallo (se indexa igual en Qdrant): %s",
                    norma,
                    exc,
                )
                catalog_id = None

        logger.info(
            "[SCRAPER] norma=%r fase=indexacion doc_id=%s collection=%s",
            norma,
            document_id,
            collection_id,
        )
        # --- TEMP_DEBUG_INDEX_DUMP: inicio (eliminar este bloque cuando ya no haga falta) ---
        # logger.info(
        #     "[SCRAPER][TEMP_DEBUG_INDEX_DUMP] norma=%r url=%s doc_id=%s collection=%s "
        #     "chars=%d metodo=%s\n--- INICIO CONTENIDO INDEXADO ---\n%s\n--- FIN CONTENIDO INDEXADO ---",
        #     norma,
        #     hit.url,
        #     document_id,
        #     collection_id,
        #     fetched.char_count,
        #     fetched.extraction_method,
        #     fetched.text,
        # )
        # --- TEMP_DEBUG_INDEX_DUMP: fin ---
        try:
            ingest = await self.rag.ingest_text(
                collection_id=collection_id,
                document_id=document_id,
                content=fetched.text,
                chunk_size=700,
                chunk_overlap=120,
                title=norma,
                source_filename=hit.url,
                chunk_strategy="adaptive",
                extraction_method=fetched.extraction_method,
                territorio=val_out.territorio,
            )
        except Exception as exc:
            if is_transient_network_error(exc):
                info = classify_http_error(exc)
                logger.error(
                    "[SCRAPER] norma=%r indexacion_red_fallo tipo=%s error=%s",
                    norma,
                    info.kind.value,
                    info.message,
                )
                motivo_idx = f"Error de red al indexar en Qdrant ({info.kind.value}): {info.message}"
            else:
                logger.exception("[SCRAPER] norma=%r indexacion_fallo", norma)
                motivo_idx = f"Error al indexar en RAG: {exc}"
            if db is not None and catalog_id:
                try:
                    await conocimiento_repo.update_doc(
                        db,
                        catalog_id,
                        ConocimientoUpdate(
                            estado="error",
                            error_mensaje=str(exc),
                        ),
                    )
                except Exception as cat_exc:
                    logger.warning(
                        "[SCRAPER] norma=%r catalogo_mysql_update_fallo: %s",
                        norma,
                        cat_exc,
                    )
            return (
                NormaScraperResultado(
                    norma=norma,
                    estado="error",
                    url=hit.url,
                    document_id=document_id,
                    coleccion_id=collection_id,
                    motivo=motivo_idx,
                    territorio=val_out.territorio,
                    validacion=val_out,
                ),
                val_out,
                motivo_idx,
            )

        if db is not None and catalog_id:
            try:
                await conocimiento_repo.update_doc(
                    db,
                    catalog_id,
                    ConocimientoUpdate(
                        estado="indexado",
                        chunk_count=ingest.chunks_indexed,
                        qdrant_doc_id=document_id,
                        error_mensaje=None,
                    ),
                )
            except Exception as exc:
                logger.warning(
                    "[SCRAPER] norma=%r catalogo_mysql_update_fallo: %s",
                    norma,
                    exc,
                )

        logger.info(
            "[SCRAPER] norma=%r fase=completada chunks=%d estado=indexada",
            norma,
            ingest.chunks_indexed,
        )
        return (
            NormaScraperResultado(
                norma=norma,
                estado="indexada",
                url=hit.url,
                document_id=document_id,
                coleccion_id=collection_id,
                chunks_indexados=ingest.chunks_indexed,
                territorio=val_out.territorio,
                validacion=val_out,
            ),
            val_out,
            None,
        )

    async def _registrar_catalogo_pendiente(
        self,
        db: AsyncSession,
        *,
        norma: str,
        document_id: str,
        collection_id: str,
        url: str,
        territorio: list[str | None],
    ) -> str:
        from app.slices.background_scraper.matching import clave_norma, normalizar_texto
        from app.slices.conocimiento.schemas import ConocimientoUpdate

        clave_nueva = clave_norma(norma) or normalizar_texto(norma)
        existentes = await conocimiento_repo.list_docs(db, coleccion_id=collection_id, limit=1000)
        for existente in existentes:
            clave_existente = clave_norma(existente.nombre) or normalizar_texto(existente.nombre)
            if clave_existente == clave_nueva:
                actualizado = await conocimiento_repo.update_doc(
                    db,
                    existente.id,
                    ConocimientoUpdate(
                        qdrant_doc_id=document_id,
                        estado="procesando",
                    ),
                )
                return (actualizado or existente).id

        doc = await conocimiento_repo.create_doc(
            db,
            ConocimientoCreate(
                nombre=norma,
                tipo=cast(TipoDocumento, infer_tipo_norma(norma)),
                coleccion_id=collection_id,
                descripcion=f"Indexado automáticamente por scraper desde {url}",
                archivo_nombre=url,
                qdrant_doc_id=document_id,
                estado="procesando",
                territorio=territorio,
            ),
        )
        return doc.id

    async def _registrar_catalogo_fallo(
        self,
        db: AsyncSession,
        *,
        norma: str,
        territorio: list[str | None] | None,
        motivo: str,
        url: str | None = None,
    ) -> None:
        """Registra en MySQL un intento fallido (sin chunks en Qdrant)."""
        collection_id = collection_id_from_territorio(territorio)
        try:
            await conocimiento_repo.create_doc(
                db,
                ConocimientoCreate(
                    nombre=norma,
                    tipo=cast(TipoDocumento, infer_tipo_norma(norma)),
                    coleccion_id=collection_id,
                    descripcion=motivo,
                    archivo_nombre=url,
                    qdrant_doc_id=derive_document_id(norma),
                    estado="error",
                    error_mensaje=motivo,
                    territorio=territorio,
                ),
            )
        except Exception as exc:
            logger.warning(
                "[SCRAPER] norma=%r catalogo_mysql_fallo_registro_error: %s",
                norma,
                exc,
            )

    async def _buscar_en_red(self, norma: str, *, pais: str) -> list[SearchHit]:
        """Búsqueda ``{norma} suin`` en SUIN primero; PDF solo si no hay viewDocument."""
        max_results = self.settings.scraper_search_max_results
        seen_urls: set[str] = set()
        suin_hits: list[SearchHit] = []

        if self.settings.scraper_suin_enabled and pais.upper() == "COLOMBIA":
            logger.info("[SCRAPER] norma=%r fase=busqueda_suin inicio", norma)
            try:
                suin_hits = await self._suin.search(norma, max_results=max_results)
            except Exception as exc:
                logger.warning(
                    "[SCRAPER] norma=%r suin_fallo error=%s; se continúa con búsqueda web",
                    norma,
                    exc,
                )
                suin_hits = []

        suin_view_hits = [
            hit
            for hit in dedupe_suin_search_hits(suin_hits, settings=self.settings)
            if scraper_hit_source(hit.url, settings=self.settings) == "suin_viewdocument"
            and suin_hit_is_trusted(norma, hit)
        ]
        if suin_view_hits:
            candidatos = sort_scraper_hits_prioritize_suin(
                suin_view_hits, settings=self.settings
            )[:1]
            logger.info(
                "[SCRAPER] norma=%r fase=cola_candidatos total=1 suin_viewdocument=1 "
                "(solo SUIN; sin búsqueda PDF)",
            )
            for orden, hit in enumerate(candidatos, start=1):
                logger.info(
                    "[SCRAPER] norma=%r fase=cola_candidatos orden=%d fuente=%s url=%s titulo=%r",
                    norma,
                    orden,
                    scraper_hit_source(hit.url, settings=self.settings),
                    hit.url,
                    hit.title,
                )
            return candidatos

        merged: list[SearchHit] = []
        for hit in suin_hits:
            if hit.url in seen_urls:
                continue
            seen_urls.add(hit.url)
            merged.append(hit)

        variants = build_search_query_variants(
            norma,
            suffix=self.settings.scraper_search_query_suffix,
            max_variants=self.settings.scraper_search_query_variants,
            pais=pais,
        )
        if variants:
            logger.info("[SCRAPER] norma=%r fase=busqueda_pdf inicio", norma)
            for query in variants:
                logger.info(
                    "[SCRAPER] norma=%r fase=busqueda_pdf variante=%r",
                    norma,
                    query,
                )
                batch = await self._search.search(query, max_results=max_results)
                for hit in batch:
                    if hit.url in seen_urls:
                        continue
                    seen_urls.add(hit.url)
                    merged.append(hit)
                if len(merged) >= max_results:
                    break

        merged = sort_scraper_hits_prioritize_suin(merged, settings=self.settings)
        candidatos = merged[:max_results]

        if candidatos:
            logger.info(
                "[SCRAPER] norma=%r fase=cola_candidatos total=%d suin_viewdocument=%d",
                norma,
                len(candidatos),
                sum(
                    1
                    for hit in candidatos
                    if scraper_hit_source(hit.url, settings=self.settings) == "suin_viewdocument"
                ),
            )
            for orden, hit in enumerate(candidatos, start=1):
                logger.info(
                    "[SCRAPER] norma=%r fase=cola_candidatos orden=%d fuente=%s url=%s titulo=%r",
                    norma,
                    orden,
                    scraper_hit_source(hit.url, settings=self.settings),
                    hit.url,
                    hit.title,
                )
        return candidatos
