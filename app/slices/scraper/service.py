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
from app.slices.rag.service import RagService
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
from app.slices.scraper.validator import validate_norm_document
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

    async def buscar_normas(self, normas: list[str]) -> ScraperBuscarResponse:
        """
        Procesa las normas en paralelo (asyncio) con límite de concurrencia.

        Cada norma usa su propia sesión MySQL cuando el catálogo está activo.
        """
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
            "[SCRAPER] lote normas=%d concurrencia=%d (paralelo asyncio)",
            len(items),
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
                            resultado = await self._procesar_norma(nombre, db=db)
                    else:
                        resultado = await self._procesar_norma(nombre, db=None)
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
                concurrencia=concurrencia,
            ),
            resultados=resultados,
        )

    async def _procesar_norma(
        self,
        norma: str,
        *,
        db: AsyncSession | None,
    ) -> NormaScraperResultado:
        logger.info("[SCRAPER] norma=%r fase=inicio", norma)
        urls_intentadas: list[str] = []
        ultima_validacion: ValidacionNormaOut | None = None
        ultimo_motivo: str | None = None

        try:
            hits = await self._buscar_en_red(norma)
        except Exception as exc:
            logger.exception("[SCRAPER] norma=%r error busqueda_red", norma)
            return NormaScraperResultado(
                norma=norma,
                estado="error",
                motivo=f"Error en búsqueda web: {exc}",
            )

        if not hits:
            logger.info("[SCRAPER] norma=%r fase=fin estado=no_encontrada", norma)
            return NormaScraperResultado(
                norma=norma,
                estado="no_encontrada",
                motivo="La búsqueda en red no devolvió resultados.",
            )

        for hit in hits:
            urls_intentadas.append(hit.url)
            indexado, validacion, motivo = await self._evaluar_candidato(norma, hit, db=db)
            if validacion is not None:
                ultima_validacion = validacion
            if motivo:
                ultimo_motivo = motivo
            if indexado is not None:
                return indexado

        logger.info("[SCRAPER] norma=%r fase=fin estado=no_indexada", norma)
        return NormaScraperResultado(
            norma=norma,
            estado="no_indexada",
            motivo=ultimo_motivo
            or "Se encontraron enlaces pero ninguno pasó la validación o no tenía texto utilizable.",
            urls_intentadas=urls_intentadas,
            validacion=ultima_validacion,
        )

    async def _evaluar_candidato(
        self,
        norma: str,
        hit: SearchHit,
        *,
        db: AsyncSession | None,
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
            logger.warning(
                "[SCRAPER] norma=%r descarga_fallo url=%s error=%s", norma, hit.url, exc
            )
            return None, None, f"No se pudo descargar {hit.url}: {exc}"
        except ValueError as exc:
            logger.warning(
                "[SCRAPER] norma=%r extraccion_fallo url=%s error=%s", norma, hit.url, exc
            )
            return None, None, str(exc)

        try:
            validation = await validate_norm_document(
                http=self._http,
                settings=self.settings,
                norma_solicitada=norma,
                texto=fetched.text,
                url=hit.url,
                titulo_resultado=hit.title,
            )
        except Exception as exc:
            logger.exception("[SCRAPER] norma=%r validacion_error url=%s", norma, hit.url)
            return None, None, f"Error en validación IA: {exc}"

        val_out = validation.outcome
        if not validation.accepted:
            motivo = val_out.motivo or "El documento no coincide con la norma solicitada."
            return None, val_out, motivo

        document_id = derive_document_id(norma)
        collection_id = self.settings.scraper_collection_id

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
            logger.exception("[SCRAPER] norma=%r indexacion_fallo", norma)
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
                    motivo=f"Error al indexar en RAG: {exc}",
                    validacion=val_out,
                ),
                val_out,
                str(exc),
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

    async def _buscar_en_red(self, norma: str) -> list[SearchHit]:
        """Prueba varias formulaciones de consulta hasta obtener enlaces."""
        variants = build_search_query_variants(
            norma,
            suffix=self.settings.scraper_search_query_suffix,
            max_variants=self.settings.scraper_search_query_variants,
        )
        if not variants:
            return []

        seen_urls: set[str] = set()
        merged: list[SearchHit] = []
        max_results = self.settings.scraper_search_max_results

        for query in variants:
            logger.debug("[SCRAPER] norma=%r fase=busqueda_red variante=%r", norma, query)
            batch = await self._search.search(query, max_results=max_results)
            for hit in batch:
                if hit.url in seen_urls:
                    continue
                seen_urls.add(hit.url)
                merged.append(hit)
            if len(merged) >= max_results:
                break

        if merged:
            logger.info(
                "[SCRAPER] norma=%r fase=busqueda_red enlaces=%d variantes=%d",
                norma,
                len(merged),
                len(variants),
            )
        return merged[:max_results]
