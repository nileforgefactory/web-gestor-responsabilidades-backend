"""Generación de informe PDF detallado para análisis de planes de desarrollo."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ─── Paleta de colores ────────────────────────────────────────────────────────

_AZUL_OSCURO   = colors.HexColor("#1a2e4a")
_AZUL_MEDIO    = colors.HexColor("#2563eb")
_AZUL_CLARO    = colors.HexColor("#dbeafe")
_ROJO_CRITICO  = colors.HexColor("#dc2626")
_ROJO_CLARO    = colors.HexColor("#fee2e2")
_NARANJA       = colors.HexColor("#ea580c")
_NARANJA_CLARO = colors.HexColor("#ffedd5")
_AMARILLO      = colors.HexColor("#ca8a04")
_AMARILLO_CLARO= colors.HexColor("#fef9c3")
_VERDE         = colors.HexColor("#16a34a")
_VERDE_CLARO   = colors.HexColor("#dcfce7")
_GRIS_OSCURO   = colors.HexColor("#374151")
_GRIS_MEDIO    = colors.HexColor("#6b7280")
_GRIS_CLARO    = colors.HexColor("#f3f4f6")
_BLANCO        = colors.white

# ─── Estilos tipográficos ─────────────────────────────────────────────────────

def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()

    return {
        "portada_titulo": ParagraphStyle(
            "portada_titulo",
            fontName="Helvetica-Bold",
            fontSize=26,
            textColor=_BLANCO,
            alignment=TA_CENTER,
            spaceAfter=8,
            leading=32,
        ),
        "portada_sub": ParagraphStyle(
            "portada_sub",
            fontName="Helvetica",
            fontSize=13,
            textColor=colors.HexColor("#bfdbfe"),
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "portada_meta": ParagraphStyle(
            "portada_meta",
            fontName="Helvetica",
            fontSize=10,
            textColor=colors.HexColor("#93c5fd"),
            alignment=TA_CENTER,
            spaceAfter=2,
        ),
        "seccion_titulo": ParagraphStyle(
            "seccion_titulo",
            fontName="Helvetica-Bold",
            fontSize=16,
            textColor=_BLANCO,
            alignment=TA_LEFT,
            spaceBefore=4,
            spaceAfter=4,
            leftIndent=8,
        ),
        "subseccion": ParagraphStyle(
            "subseccion",
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=_AZUL_OSCURO,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "cuerpo": ParagraphStyle(
            "cuerpo",
            fontName="Helvetica",
            fontSize=9,
            textColor=_GRIS_OSCURO,
            alignment=TA_JUSTIFY,
            spaceAfter=4,
            leading=13,
        ),
        "cuerpo_bold": ParagraphStyle(
            "cuerpo_bold",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=_GRIS_OSCURO,
            spaceAfter=2,
        ),
        "tabla_header": ParagraphStyle(
            "tabla_header",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=_BLANCO,
            alignment=TA_CENTER,
        ),
        "tabla_cell": ParagraphStyle(
            "tabla_cell",
            fontName="Helvetica",
            fontSize=8,
            textColor=_GRIS_OSCURO,
            alignment=TA_LEFT,
            leading=11,
        ),
        "tabla_cell_bold": ParagraphStyle(
            "tabla_cell_bold",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=_GRIS_OSCURO,
            alignment=TA_LEFT,
        ),
        "alerta_critica": ParagraphStyle(
            "alerta_critica",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=_ROJO_CRITICO,
            alignment=TA_CENTER,
        ),
        "alerta_media": ParagraphStyle(
            "alerta_media",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=_NARANJA,
            alignment=TA_CENTER,
        ),
        "alerta_baja": ParagraphStyle(
            "alerta_baja",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=_AMARILLO,
            alignment=TA_CENTER,
        ),
        "nota_pie": ParagraphStyle(
            "nota_pie",
            fontName="Helvetica-Oblique",
            fontSize=7,
            textColor=_GRIS_MEDIO,
            alignment=TA_LEFT,
            spaceBefore=2,
        ),
        "matriz_p":   ParagraphStyle("matriz_p",  fontName="Helvetica-Bold", fontSize=8, textColor=_VERDE,   alignment=TA_CENTER),
        "matriz_c":   ParagraphStyle("matriz_c",  fontName="Helvetica-Bold", fontSize=8, textColor=_AZUL_MEDIO, alignment=TA_CENTER),
        "matriz_s":   ParagraphStyle("matriz_s",  fontName="Helvetica-Bold", fontSize=8, textColor=_NARANJA, alignment=TA_CENTER),
        "matriz_n":   ParagraphStyle("matriz_n",  fontName="Helvetica",      fontSize=8, textColor=_GRIS_MEDIO, alignment=TA_CENTER),
    }


# ─── Helpers de construcción ─────────────────────────────────────────────────

def _seccion_banner(titulo: str, numero: str, styles: dict) -> list:
    """Banda de color para encabezado de sección."""
    banner = Table(
        [[Paragraph(f"{numero}. {titulo}", styles["seccion_titulo"])]],
        colWidths=[17 * cm],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _AZUL_OSCURO),
        ("ROUNDEDCORNERS", [4]),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
    ]))
    return [Spacer(1, 0.3 * cm), banner, Spacer(1, 0.25 * cm)]


def _kv_row(label: str, value: str, styles: dict) -> Table:
    """Fila clave:valor en línea."""
    t = Table(
        [[Paragraph(label, styles["cuerpo_bold"]), Paragraph(value or "—", styles["cuerpo"])]],
        colWidths=[4.5 * cm, 12.5 * cm],
    )
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _badge_severidad(sev: str, styles: dict) -> Paragraph:
    mapa = {
        "alta":  ("CRÍTICA", styles["alerta_critica"]),
        "media": ("MEDIA",   styles["alerta_media"]),
        "baja":  ("BAJA",    styles["alerta_baja"]),
    }
    texto, st = mapa.get(sev, ("DESCONOCIDA", styles["alerta_baja"]))
    return Paragraph(texto, st)


def _tipo_responsabilidad(tipo: str) -> str:
    return {
        "P": "Principal",
        "C": "Concurrente",
        "S": "Subsidiaria",
        "N": "No aplica",
    }.get(tipo, tipo)


def _tipo_brecha(tipo: str) -> str:
    return {
        "critica":         "Brecha crítica",
        "duplicidad":      "Duplicidad",
        "sin_responsable": "Sin responsable",
        "indefinido":      "Indefinido",
    }.get(tipo, tipo)


def _matriz_cell(valor: str, styles: dict) -> Paragraph:
    estilo = {
        "P": styles["matriz_p"],
        "C": styles["matriz_c"],
        "S": styles["matriz_s"],
        "N": styles["matriz_n"],
    }.get(valor, styles["matriz_n"])
    etiqueta = {"P": "P", "C": "C", "S": "S", "N": "—"}.get(valor, valor)
    return Paragraph(etiqueta, estilo)


def _nivel_label(nivel: str) -> str:
    return {
        "nacional":       "Nacional",
        "departamental":  "Departamental",
        "municipal":      "Municipal",
        "sectorial":      "Sectorial",
    }.get(nivel, nivel.capitalize())


# ─── Secciones del documento ──────────────────────────────────────────────────

def _portada(plan: dict, styles: dict) -> list:
    titulo     = plan.get("titulo", "Plan de Desarrollo")
    entidad    = plan.get("entidad") or "Entidad territorial"
    nivel      = _nivel_label(plan.get("nivel", ""))
    periodo    = plan.get("periodo") or ""
    fecha_hoy  = datetime.now().strftime("%d de %B de %Y")
    descripcion= plan.get("descripcion") or ""

    fondo = Table(
        [
            [Paragraph("INFORME DE ANÁLISIS", styles["portada_sub"])],
            [Paragraph("DE PLAN DE DESARROLLO", styles["portada_sub"])],
            [Spacer(1, 0.4 * cm)],
            [Paragraph(titulo, styles["portada_titulo"])],
            [Spacer(1, 0.3 * cm)],
            [Paragraph(entidad, styles["portada_sub"])],
            [Paragraph(f"Nivel {nivel}  ·  {periodo}", styles["portada_meta"])],
            [Spacer(1, 0.6 * cm)],
            [HRFlowable(width="80%", thickness=1, color=colors.HexColor("#3b82f6"), spaceAfter=8)],
            [Paragraph(f"Generado el {fecha_hoy}", styles["portada_meta"])],
            [Paragraph("Sistema de Gestión de Responsabilidades — Análisis con IA", styles["portada_meta"])],
        ],
        colWidths=[17 * cm],
    )
    fondo.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _AZUL_OSCURO),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 20),
        ("ROUNDEDCORNERS", [6]),
    ]))

    resumen_bloque = []
    if descripcion:
        resumen_bloque = [
            Spacer(1, 0.5 * cm),
            Paragraph("Síntesis ejecutiva", styles["subseccion"]),
            Paragraph(descripcion, styles["cuerpo"]),
        ]

    # Métricas rápidas
    resp_total   = plan.get("resp_total", 0)
    leyes_total  = plan.get("leyes_total", 0)
    actores_total= plan.get("actores_total", 0)
    brechas_total= plan.get("brechas_total", 0)

    metricas = Table(
        [[
            _metric_box("Responsabilidades", str(resp_total),    _AZUL_MEDIO,   styles),
            _metric_box("Normas legales",     str(leyes_total),   _VERDE,        styles),
            _metric_box("Actores",            str(actores_total), _NARANJA,      styles),
            _metric_box("Brechas",            str(brechas_total), _ROJO_CRITICO, styles),
        ]],
        colWidths=[4.25 * cm, 4.25 * cm, 4.25 * cm, 4.25 * cm],
        hAlign="CENTER",
    )
    metricas.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ]))

    return [
        fondo,
        *resumen_bloque,
        Spacer(1, 0.4 * cm),
        metricas,
        PageBreak(),
    ]


def _metric_box(label: str, value: str, color: Any, styles: dict) -> Table:
    t = Table(
        [
            [Paragraph(value, ParagraphStyle("mv", fontName="Helvetica-Bold", fontSize=22, textColor=_BLANCO, alignment=TA_CENTER))],
            [Paragraph(label, ParagraphStyle("ml", fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#e2e8f0"), alignment=TA_CENTER))],
        ],
        colWidths=[4.0 * cm],
    )
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), color),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return t


def _seccion_responsabilidades(responsabilidades: list[dict], styles: dict) -> list:
    story = [*_seccion_banner("Responsabilidades identificadas", "1", styles)]

    if not responsabilidades:
        story.append(Paragraph("No se identificaron responsabilidades.", styles["cuerpo"]))
        return story

    # Agrupar por sector
    por_sector: dict[str, list[dict]] = {}
    for r in responsabilidades:
        s = r.get("sector") or "Sin sector"
        por_sector.setdefault(s, []).append(r)

    story.append(Paragraph(
        f"Se identificaron <b>{len(responsabilidades)}</b> responsabilidades distribuidas "
        f"en <b>{len(por_sector)}</b> sector(es). La siguiente tabla detalla cada una "
        "con su tipo de competencia, referencia legal y carácter de obligatoriedad.",
        styles["cuerpo"],
    ))
    story.append(Spacer(1, 0.2 * cm))

    for sector, items in sorted(por_sector.items()):
        story.append(Paragraph(f"Sector: {sector}", styles["subseccion"]))

        col_w = [1.1 * cm, 5.5 * cm, 3.5 * cm, 2.5 * cm, 4.4 * cm]
        encabezados = [
            Paragraph("#",            styles["tabla_header"]),
            Paragraph("Responsabilidad", styles["tabla_header"]),
            Paragraph("Tipo",         styles["tabla_header"]),
            Paragraph("Obligatoriedad", styles["tabla_header"]),
            Paragraph("Ref. Legal",   styles["tabla_header"]),
        ]
        filas = [encabezados]
        for i, r in enumerate(items, 1):
            tipo_txt = _tipo_responsabilidad(r.get("tipo", "P"))
            ref_leg  = r.get("referencia_legal") or r.get("ref_legal") or "—"
            oblig    = r.get("obligatoriedad") or ("Obligatoria" if r.get("tipo") == "P" else "Concurrente")
            desc     = r.get("descripcion") or ""
            titulo_txt = f"<b>{r.get('titulo','')}</b>"
            if desc:
                titulo_txt += f"<br/><font size='7' color='#6b7280'>{desc[:180]}{'…' if len(desc)>180 else ''}</font>"
            filas.append([
                Paragraph(str(i), styles["tabla_cell"]),
                Paragraph(titulo_txt, styles["tabla_cell"]),
                Paragraph(tipo_txt,  styles["tabla_cell"]),
                Paragraph(oblig,     styles["tabla_cell"]),
                Paragraph(ref_leg,   styles["tabla_cell"]),
            ])

        tabla = Table(filas, colWidths=col_w, repeatRows=1)
        tabla.setStyle(_estilo_tabla_alternada())
        story.append(tabla)
        story.append(Spacer(1, 0.3 * cm))

    # Análisis por tipo
    conteo_tipo = {}
    for r in responsabilidades:
        conteo_tipo[r.get("tipo", "P")] = conteo_tipo.get(r.get("tipo", "P"), 0) + 1

    story.append(Paragraph("Distribución por tipo de competencia", styles["subseccion"]))
    tipo_filas = [
        [Paragraph("Tipo", styles["tabla_header"]),
         Paragraph("Descripción", styles["tabla_header"]),
         Paragraph("Cantidad", styles["tabla_header"]),
         Paragraph("% del total", styles["tabla_header"])],
    ]
    total = len(responsabilidades)
    for tipo, desc in [("P","Principal — responsabilidad directa e indelegable"),
                       ("C","Concurrente — compartida con otro nivel"),
                       ("S","Subsidiaria — actúa ante ausencia del titular"),
                       ("N","No aplica")]:
        cnt = conteo_tipo.get(tipo, 0)
        pct = f"{cnt/total*100:.1f}%" if total else "0%"
        tipo_filas.append([
            Paragraph(tipo,  styles["tabla_cell_bold"]),
            Paragraph(desc,  styles["tabla_cell"]),
            Paragraph(str(cnt), styles["tabla_cell"]),
            Paragraph(pct,   styles["tabla_cell"]),
        ])
    t_tipo = Table(tipo_filas, colWidths=[1.5*cm, 8.5*cm, 2.5*cm, 2.5*cm], repeatRows=1)
    t_tipo.setStyle(_estilo_tabla_alternada())
    story.append(t_tipo)

    return story


def _seccion_marco_legal(normas: list[dict], styles: dict) -> list:
    story = [*_seccion_banner("Marco normativo aplicable", "2", styles)]

    if not normas:
        story.append(Paragraph("No se identificaron normas aplicables.", styles["cuerpo"]))
        return story

    story.append(Paragraph(
        f"Se identificaron <b>{len(normas)}</b> normas del ordenamiento jurídico colombiano "
        "aplicables a este plan. Se presentan ordenadas por relevancia y jerarquía normativa.",
        styles["cuerpo"],
    ))
    story.append(Spacer(1, 0.2 * cm))

    # Agrupar por tipo
    por_tipo: dict[str, list[dict]] = {}
    for n in normas:
        t = n.get("tipo") or "otro"
        por_tipo.setdefault(t, []).append(n)

    orden_tipo = ["ley", "decreto", "resolucion", "circular", "otro"]
    for tipo in orden_tipo:
        items = por_tipo.get(tipo, [])
        if not items:
            continue
        nombre_tipo = {"ley":"Leyes","decreto":"Decretos","resolucion":"Resoluciones",
                       "circular":"Circulares","otro":"Otras normas"}.get(tipo, tipo.capitalize())
        story.append(Paragraph(nombre_tipo, styles["subseccion"]))

        enc = [
            Paragraph("Código",    styles["tabla_header"]),
            Paragraph("Título",    styles["tabla_header"]),
            Paragraph("Artículos", styles["tabla_header"]),
            Paragraph("Vigente",   styles["tabla_header"]),
            Paragraph("Relevancia",styles["tabla_header"]),
        ]
        filas = [enc]
        for n in sorted(items, key=lambda x: -(x.get("relevancia") or 0)):
            codigo  = n.get("norma_codigo") or n.get("codigo") or "—"
            titulo  = n.get("titulo") or ""
            arts    = n.get("articulos") or "—"
            vigente = "Sí" if n.get("vigente", True) else "No"
            rel     = n.get("relevancia") or 0
            rel_txt = f"{rel}%"
            extracto= n.get("extracto") or ""
            titulo_txt = f"<b>{titulo[:120]}</b>"
            if extracto:
                titulo_txt += f"<br/><font size='7' color='#6b7280'>{extracto[:200]}{'…' if len(extracto)>200 else ''}</font>"
            advertencia = n.get("advertencia")
            if advertencia:
                titulo_txt += f"<br/><font size='7' color='#dc2626'>⚠ {advertencia}</font>"
            filas.append([
                Paragraph(codigo,    styles["tabla_cell_bold"]),
                Paragraph(titulo_txt,styles["tabla_cell"]),
                Paragraph(arts,      styles["tabla_cell"]),
                Paragraph(vigente,   styles["tabla_cell"]),
                Paragraph(rel_txt,   styles["tabla_cell"]),
            ])

        tabla = Table(filas, colWidths=[2.5*cm, 8.0*cm, 2.5*cm, 1.5*cm, 2.5*cm], repeatRows=1)
        tabla.setStyle(_estilo_tabla_alternada())
        story.append(tabla)
        story.append(Spacer(1, 0.3 * cm))

    return story


def _seccion_actores(actores: list[dict], styles: dict) -> list:
    story = [*_seccion_banner("Actores institucionales", "3", styles)]

    if not actores:
        story.append(Paragraph("No se identificaron actores institucionales.", styles["cuerpo"]))
        return story

    story.append(Paragraph(
        f"Se identificaron <b>{len(actores)}</b> actores institucionales con roles en la ejecución, "
        "seguimiento, financiación o control del plan. La tabla presenta su clasificación funcional "
        "y nivel territorial.",
        styles["cuerpo"],
    ))
    story.append(Spacer(1, 0.2 * cm))

    # Agrupar por nivel
    por_nivel: dict[str, list[dict]] = {}
    for a in actores:
        nv = a.get("nivel") or "sin_nivel"
        por_nivel.setdefault(nv, []).append(a)

    enc = [
        Paragraph("Actor",       styles["tabla_header"]),
        Paragraph("Tipo",        styles["tabla_header"]),
        Paragraph("Nivel",       styles["tabla_header"]),
        Paragraph("Competencias / Rol", styles["tabla_header"]),
    ]
    filas = [enc]
    # Orden de niveles conocidos primero; luego cualquier otro presente (ej. regional, especializado)
    _orden_niveles = ["nacional", "regional", "departamental", "municipal", "especializado", "sectorial", "sin_nivel"]
    claves_nivel = [k for k in _orden_niveles if k in por_nivel] + [k for k in por_nivel if k not in _orden_niveles]
    for nivel_key in claves_nivel:
        for a in por_nivel.get(nivel_key, []):
            nombre = a.get("nombre") or ""
            tipo   = a.get("tipo") or "otro"
            nivel  = _nivel_label(nivel_key)
            # competencias puede venir como lista de objetos {titulo,...} o como string
            comps_raw = a.get("competencias")
            if isinstance(comps_raw, list):
                comps = "; ".join(
                    (c.get("titulo", "") if isinstance(c, dict) else str(c)) for c in comps_raw
                )
            else:
                comps = comps_raw or a.get("badge_label") or ""
            comps = str(comps or "")
            filas.append([
                Paragraph(f"<b>{nombre}</b>", styles["tabla_cell"]),
                Paragraph(tipo,               styles["tabla_cell"]),
                Paragraph(nivel,              styles["tabla_cell"]),
                Paragraph(comps[:220],        styles["tabla_cell"]),
            ])

    tabla = Table(filas, colWidths=[4.5*cm, 2.5*cm, 2.5*cm, 7.5*cm], repeatRows=1)
    tabla.setStyle(_estilo_tabla_alternada())
    story.append(tabla)

    # Conteo por tipo
    story.append(Spacer(1, 0.3 * cm))
    conteo_tipo: dict[str, int] = {}
    for a in actores:
        t = a.get("tipo") or "otro"
        conteo_tipo[t] = conteo_tipo.get(t, 0) + 1

    story.append(Paragraph("Distribución por rol funcional", styles["subseccion"]))
    filas_tipo = [[Paragraph("Tipo de actor", styles["tabla_header"]),
                   Paragraph("Cantidad",      styles["tabla_header"])]]
    for tipo, cnt in sorted(conteo_tipo.items(), key=lambda x: -x[1]):
        filas_tipo.append([Paragraph(tipo, styles["tabla_cell"]), Paragraph(str(cnt), styles["tabla_cell"])])
    t_tipo = Table(filas_tipo, colWidths=[10*cm, 5*cm], repeatRows=1)
    t_tipo.setStyle(_estilo_tabla_alternada())
    story.append(t_tipo)

    return story


def _seccion_brechas(brechas: list[dict], styles: dict) -> list:
    story = [*_seccion_banner("Brechas, duplicidades y fallas detectadas", "4", styles)]

    if not brechas:
        story.append(Paragraph(
            "No se registraron brechas relevantes en el análisis. El plan presenta una cobertura "
            "normativa adecuada según las normas identificadas.",
            styles["cuerpo"],
        ))
        return story

    # Clasificar
    criticas      = [b for b in brechas if b.get("tipo") == "critica"]
    sin_resp      = [b for b in brechas if b.get("tipo") == "sin_responsable"]
    duplicidades  = [b for b in brechas if b.get("tipo") == "duplicidad"]
    indefinidas   = [b for b in brechas if b.get("tipo") == "indefinido"]

    story.append(Paragraph(
        f"Se detectaron <b>{len(brechas)}</b> brechas en el análisis: "
        f"<font color='#dc2626'><b>{len(criticas)} críticas</b></font>, "
        f"<font color='#ea580c'><b>{len(sin_resp)} sin responsable</b></font>, "
        f"<font color='#ca8a04'><b>{len(duplicidades)} duplicidades</b></font> e "
        f"<b>{len(indefinidas)} indefinidas</b>. "
        "Estas brechas representan riesgos para la ejecución efectiva del plan y "
        "deben atenderse mediante ajustes normativos o administrativos.",
        styles["cuerpo"],
    ))
    story.append(Spacer(1, 0.2 * cm))

    grupos = [
        ("critica",         "Brechas críticas — Obligaciones legales incumplidas",       _ROJO_CLARO,    criticas),
        ("sin_responsable", "Sin responsable — Funciones sin actor asignado",             _NARANJA_CLARO, sin_resp),
        ("duplicidad",      "Duplicidades — Competencias superpuestas entre niveles",     _AMARILLO_CLARO,duplicidades),
        ("indefinido",      "Indefinidas — Normas no referenciadas en el plan",           _GRIS_CLARO,    indefinidas),
    ]

    for tipo_key, titulo_grupo, color_fondo, items in grupos:
        if not items:
            continue
        story.append(Paragraph(titulo_grupo, styles["subseccion"]))

        enc = [
            Paragraph("Brecha",          styles["tabla_header"]),
            Paragraph("Tipo",            styles["tabla_header"]),
            Paragraph("Severidad",       styles["tabla_header"]),
            Paragraph("Norma base",      styles["tabla_header"]),
            Paragraph("Recomendación",   styles["tabla_header"]),
        ]
        filas = [enc]
        for b in sorted(items, key=lambda x: {"alta":0,"media":1,"baja":2}.get(x.get("severidad","baja"), 3)):
            desc_txt = b.get("descripcion") or ""
            titulo_b = f"<b>{b.get('titulo','')}</b>"
            if desc_txt:
                titulo_b += f"<br/><font size='7'>{desc_txt[:240]}{'…' if len(desc_txt)>240 else ''}</font>"
            norma_base   = b.get("norma_base") or b.get("referencia_legal") or b.get("ref_legal") or "—"
            recomendacion= b.get("recomendacion") or b.get("recomendacion_accion") or "Revisar asignación de responsabilidades."
            filas.append([
                Paragraph(titulo_b,                    styles["tabla_cell"]),
                Paragraph(_tipo_brecha(b.get("tipo","")), styles["tabla_cell"]),
                _badge_severidad(b.get("severidad","baja"), styles),
                Paragraph(norma_base[:120],            styles["tabla_cell"]),
                Paragraph(recomendacion[:180],         styles["tabla_cell"]),
            ])

        col_w = [5.0*cm, 2.2*cm, 1.8*cm, 3.5*cm, 4.5*cm]
        tabla = Table(filas, colWidths=col_w, repeatRows=1)
        base_style = _estilo_tabla_alternada()
        # Pintar fondo del grupo
        base_style.add("BACKGROUND", (0, 0), (-1, 0), _AZUL_OSCURO)
        tabla.setStyle(base_style)
        story.append(tabla)
        story.append(Spacer(1, 0.25 * cm))

    # Box de responsabilidades no identificadas (análisis normativo)
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("Análisis de responsabilidades obligatorias no identificadas", styles["subseccion"]))
    story.append(Paragraph(
        "Las brechas de tipo <i>crítica</i> y <i>sin_responsable</i> indican obligaciones que la normativa "
        "colombiana impone al nivel territorial pero que el plan no contempla explícitamente. "
        "Se recomienda al equipo técnico revisar cada brecha crítica contra las normas señaladas "
        "y definir el actor responsable, el mecanismo de ejecución y los indicadores de seguimiento "
        "antes de la aprobación del plan.",
        styles["cuerpo"],
    ))

    return story


def _seccion_matriz(matriz: list[dict], styles: dict) -> list:
    story = [*_seccion_banner("Matriz de competencias territoriales", "5", styles)]

    if not matriz:
        story.append(Paragraph("La matriz de competencias no fue generada (se requiere profundidad estándar o profunda).", styles["cuerpo"]))
        return story

    story.append(Paragraph(
        f"La matriz cruza <b>{len(matriz)}</b> competencias contra cuatro niveles territoriales "
        "(Nación, Departamento, Municipio, Especializado). Los valores P/C/S/— indican "
        "responsabilidad <b>P</b>rincipal, <b>C</b>oncurrente, <b>S</b>ubsidiaria o No aplica.",
        styles["cuerpo"],
    ))
    story.append(Spacer(1, 0.15 * cm))

    # Leyenda
    leyenda_data = [[
        Paragraph("<b>P</b> Principal", styles["matriz_p"]),
        Paragraph("<b>C</b> Concurrente", styles["matriz_c"]),
        Paragraph("<b>S</b> Subsidiaria", styles["matriz_s"]),
        Paragraph("<b>—</b> No aplica",  styles["matriz_n"]),
        Paragraph("<font color='#dc2626'>■</font> Brecha crítica", styles["tabla_cell"]),
        Paragraph("<font color='#ca8a04'>■</font> Duplicidad",     styles["tabla_cell"]),
    ]]
    leyenda = Table(leyenda_data, colWidths=[2.5*cm]*6)
    leyenda.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), _GRIS_CLARO),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("ROUNDEDCORNERS", [3]),
    ]))
    story.append(leyenda)
    story.append(Spacer(1, 0.2 * cm))

    enc = [
        Paragraph("Competencia",        styles["tabla_header"]),
        Paragraph("Sector",             styles["tabla_header"]),
        Paragraph("Ley base",           styles["tabla_header"]),
        Paragraph("Nación",             styles["tabla_header"]),
        Paragraph("Dpto.",              styles["tabla_header"]),
        Paragraph("Municipio",          styles["tabla_header"]),
        Paragraph("Esp.",               styles["tabla_header"]),
        Paragraph("Brecha",             styles["tabla_header"]),
        Paragraph("Actores vinculados", styles["tabla_header"]),
    ]
    filas = [enc]

    # Colores de fila por brecha
    brecha_colors: dict[int, Any] = {}
    for idx, m in enumerate(matriz, 1):
        brecha = m.get("brecha", "ok")
        if brecha == "critica":
            brecha_colors[idx] = _ROJO_CLARO
        elif brecha == "duplicidad":
            brecha_colors[idx] = _AMARILLO_CLARO

        actores_v = m.get("actores_vinculados") or []
        if isinstance(actores_v, list):
            actores_txt = ", ".join(
                a.get("nombre","") for a in actores_v[:4]
            ) + ("..." if len(actores_v) > 4 else "")
        else:
            actores_txt = str(actores_v)

        brecha_label = {"ok":"✓ OK","critica":"🚨 CRÍTICA","duplicidad":"⚠ DUPLICIDAD","indefinido":"? INDEF."}.get(brecha, brecha.upper())
        ley_base = m.get("ley_base") or "—"
        sector   = m.get("sector") or "—"

        filas.append([
            Paragraph(m.get("competencia","")[:100], styles["tabla_cell_bold"]),
            Paragraph(sector[:40],                   styles["tabla_cell"]),
            Paragraph(ley_base[:50],                 styles["tabla_cell"]),
            _matriz_cell(m.get("nacion","N"),         styles),
            _matriz_cell(m.get("departamento","N"),   styles),
            _matriz_cell(m.get("municipio","N"),      styles),
            _matriz_cell(m.get("especializado","N"),  styles),
            Paragraph(brecha_label,                  styles["tabla_cell_bold"]),
            Paragraph(actores_txt[:100],             styles["tabla_cell"]),
        ])

    tabla = Table(
        filas,
        colWidths=[3.5*cm, 1.8*cm, 2.2*cm, 1.1*cm, 1.1*cm, 1.5*cm, 1.2*cm, 1.6*cm, 3.0*cm],
        repeatRows=1,
    )
    estilo = _estilo_tabla_alternada()
    # Aplicar colores de brecha por fila
    for fila_idx, color in brecha_colors.items():
        estilo.add("BACKGROUND", (0, fila_idx), (-1, fila_idx), color)
    tabla.setStyle(estilo)
    story.append(tabla)

    # Resumen de brechas en matriz
    n_criticas    = sum(1 for m in matriz if m.get("brecha") == "critica")
    n_duplicidades= sum(1 for m in matriz if m.get("brecha") == "duplicidad")
    n_ok          = sum(1 for m in matriz if m.get("brecha") == "ok")

    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        f"Resumen de la matriz: {n_ok} competencias sin brecha, "
        f"{n_criticas} con brecha crítica, {n_duplicidades} con duplicidad de competencia.",
        styles["cuerpo"],
    ))

    return story


def _seccion_conclusiones(plan: dict, responsabilidades: list, brechas: list,
                           actores: list, normas: list, matriz: list, styles: dict) -> list:
    story = [*_seccion_banner("Conclusiones y recomendaciones para decisiones administrativas", "6", styles)]

    criticas      = [b for b in brechas if b.get("tipo") in ("critica","sin_responsable")]
    duplicidades  = [b for b in brechas if b.get("tipo") == "duplicidad"]
    altas         = [b for b in brechas if b.get("severidad") == "alta"]
    mat_criticas  = [m for m in matriz   if m.get("brecha") == "critica"]
    normas_no_vig = [n for n in normas   if not n.get("vigente", True)]

    story.append(Paragraph(
        "Este apartado sintetiza los hallazgos más relevantes del análisis para apoyar la toma "
        "de decisiones administrativas, técnicas y legales sobre el plan de desarrollo.",
        styles["cuerpo"],
    ))
    story.append(Spacer(1, 0.15*cm))

    # 1. Hallazgos críticos
    story.append(Paragraph("Hallazgos críticos", styles["subseccion"]))
    if criticas:
        for b in criticas[:10]:
            story.append(Paragraph(
                f"• <b>{b.get('titulo','')}</b> — {b.get('descripcion','')[:200]}",
                styles["cuerpo"],
            ))
    else:
        story.append(Paragraph("No se identificaron brechas críticas. El plan muestra una cobertura adecuada.", styles["cuerpo"]))

    # 2. Duplicidades de competencia
    story.append(Paragraph("Duplicidades de competencia", styles["subseccion"]))
    if duplicidades:
        story.append(Paragraph(
            f"Se detectaron {len(duplicidades)} duplicidades que pueden generar conflictos de autoridad "
            "o ineficiencia en la ejecución:",
            styles["cuerpo"],
        ))
        for d in duplicidades[:8]:
            story.append(Paragraph(f"• <b>{d.get('titulo','')}</b>: {d.get('descripcion','')[:180]}", styles["cuerpo"]))
    else:
        story.append(Paragraph("No se identificaron duplicidades de competencia entre niveles territoriales.", styles["cuerpo"]))

    # 3. Normas no vigentes referenciadas
    story.append(Paragraph("Normas con posibles problemas de vigencia", styles["subseccion"]))
    if normas_no_vig:
        story.append(Paragraph(
            f"El plan referencia {len(normas_no_vig)} norma(s) identificadas como no vigentes o con advertencias:",
            styles["cuerpo"],
        ))
        for n in normas_no_vig:
            adv = n.get("advertencia") or "Revisar vigencia."
            story.append(Paragraph(f"• <b>{n.get('norma_codigo','')} {n.get('titulo','')[:80]}</b>: {adv}", styles["cuerpo"]))
    else:
        story.append(Paragraph("Las normas identificadas se reportan como vigentes.", styles["cuerpo"]))

    # 4. Recomendaciones
    story.append(Paragraph("Recomendaciones prioritarias", styles["subseccion"]))

    recomendaciones = []
    if altas:
        recomendaciones.append(
            f"Atender con <b>prioridad alta</b> las {len(altas)} brecha(s) de severidad alta: "
            + "; ".join(b.get("titulo","") for b in altas[:4])
            + ("..." if len(altas) > 4 else ".")
        )
    if mat_criticas:
        recomendaciones.append(
            f"Revisar {len(mat_criticas)} competencia(s) de la matriz marcadas como críticas "
            "y asignar actor responsable con acto administrativo."
        )
    if duplicidades:
        recomendaciones.append(
            "Definir un mecanismo de articulación interinstitucional para las competencias duplicadas, "
            "preferiblemente mediante convenios o comités técnicos."
        )
    if not actores:
        recomendaciones.append("Identificar y formalizar los actores institucionales faltantes antes de la fase de ejecución.")
    if normas_no_vig:
        recomendaciones.append("Actualizar el marco normativo referenciado para asegurar que todas las leyes y decretos sean los vigentes.")
    recomendaciones.append(
        "Establecer indicadores de seguimiento específicos para las responsabilidades de tipo Principal (P) "
        "que no tengan referencia legal explícita."
    )
    recomendaciones.append(
        "Socializar este informe con los actores institucionales identificados para validar la asignación "
        "de competencias y compromisos."
    )

    for rec in recomendaciones:
        story.append(Paragraph(f"→ {rec}", styles["cuerpo"]))

    # 5. Tabla-resumen ejecutivo
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("Tablero ejecutivo de riesgos", styles["subseccion"]))
    resumen_data = [
        [Paragraph("Indicador", styles["tabla_header"]),
         Paragraph("Valor",     styles["tabla_header"]),
         Paragraph("Riesgo",    styles["tabla_header"])],
        ["Total responsabilidades",         str(len(responsabilidades)),          "Informativo"],
        ["Brechas críticas / sin responsable", str(len(criticas)),                "Alto" if criticas else "Bajo"],
        ["Duplicidades de competencia",     str(len(duplicidades)),               "Medio" if duplicidades else "Bajo"],
        ["Brechas de severidad alta",       str(len(altas)),                      "Alto" if altas else "Bajo"],
        ["Competencias críticas en matriz", str(len(mat_criticas)),               "Alto" if mat_criticas else "Bajo"],
        ["Normas sin vigencia confirmada",  str(len(normas_no_vig)),              "Medio" if normas_no_vig else "Bajo"],
        ["Actores identificados",           str(len(actores)),                    "Informativo"],
        ["Normas legales identificadas",    str(len(normas)),                     "Informativo"],
    ]
    tabla_res = Table(resumen_data, colWidths=[8.0*cm, 3.5*cm, 5.5*cm], repeatRows=1)
    estilo_res = _estilo_tabla_alternada()
    # Color riesgo
    for i, row in enumerate(resumen_data[1:], 1):
        riesgo = row[2] if isinstance(row[2], str) else ""
        if riesgo == "Alto":
            estilo_res.add("TEXTCOLOR", (2, i), (2, i), _ROJO_CRITICO)
            estilo_res.add("FONTNAME",  (2, i), (2, i), "Helvetica-Bold")
        elif riesgo == "Medio":
            estilo_res.add("TEXTCOLOR", (2, i), (2, i), _NARANJA)
            estilo_res.add("FONTNAME",  (2, i), (2, i), "Helvetica-Bold")

    tabla_res.setStyle(estilo_res)
    story.append(tabla_res)

    return story


def _seccion_analisis_ia(analisis_ia: dict[str, Any], styles: dict) -> list:
    """Sección generada por IA: qué hacer, presupuesto, suficiencia y fuentes de recursos."""
    story = [*_seccion_banner("Análisis estratégico IA — Viabilidad y recursos", "7", styles)]

    story.append(Paragraph(
        "Este capítulo es generado automáticamente por inteligencia artificial a partir del "
        "contenido del plan, las responsabilidades identificadas y el marco normativo. "
        "Sirve como insumo orientador para la gestión presupuestal y la búsqueda de recursos.",
        styles["cuerpo"],
    ))
    story.append(Spacer(1, 0.3*cm))

    # ── Qué debe hacer la entidad ──────────────────────────────────────────────
    que_hacer = analisis_ia.get("que_hacer", "")
    if que_hacer:
        story.append(Paragraph("¿Qué debe implementar esta entidad?", styles["subseccion"]))
        story.append(Paragraph(que_hacer, styles["cuerpo"]))
        story.append(Spacer(1, 0.2*cm))

    # ── Contexto legal ─────────────────────────────────────────────────────────
    contexto_legal = analisis_ia.get("contexto_legal", "")
    if contexto_legal:
        story.append(Paragraph("¿Bajo qué marco legal?", styles["subseccion"]))
        story.append(Paragraph(contexto_legal, styles["cuerpo"]))
        story.append(Spacer(1, 0.2*cm))

    # ── Presupuesto estimado ───────────────────────────────────────────────────
    presupuesto = analisis_ia.get("presupuesto_estimado", "")
    if presupuesto:
        story.append(Paragraph("Presupuesto estimado requerido", styles["subseccion"]))
        story.append(Paragraph(presupuesto, styles["cuerpo"]))
        story.append(Spacer(1, 0.2*cm))

    # ── Suficiencia presupuestal ───────────────────────────────────────────────
    suficiencia = analisis_ia.get("suficiencia", "")
    nivel_sfx   = analisis_ia.get("nivel_suficiencia", "indefinido")
    if suficiencia:
        color_sfx = {"suficiente": _VERDE_CLARO, "insuficiente": _ROJO_CLARO, "parcial": _AMARILLO_CLARO}.get(nivel_sfx, _GRIS_CLARO)
        label_sfx = {"suficiente": "✓ SUFICIENTE", "insuficiente": "✗ INSUFICIENTE", "parcial": "⚠ PARCIAL"}.get(nivel_sfx, "? INDEFINIDO")
        sfx_data = [[
            Paragraph(f"<b>{label_sfx}</b>", styles["tabla_cell_bold"]),
            Paragraph(suficiencia, styles["cuerpo"]),
        ]]
        sfx_tabla = Table(sfx_data, colWidths=[3*cm, 14*cm])
        sfx_tabla.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(0,0), color_sfx),
            ("BACKGROUND",    (1,0),(1,0), _BLANCO),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0),(-1,-1), 8),
            ("BOTTOMPADDING", (0,0),(-1,-1), 8),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
            ("BOX",           (0,0),(-1,-1), 0.5, _GRIS_MEDIO),
        ]))
        story.append(Paragraph("¿Alcanza el presupuesto disponible?", styles["subseccion"]))
        story.append(sfx_tabla)
        story.append(Spacer(1, 0.2*cm))

    # ── Fuentes de recursos recomendadas ──────────────────────────────────────
    fuentes = analisis_ia.get("fuentes_recursos", [])
    if fuentes:
        story.append(Paragraph("¿Con quién y dónde buscar recursos?", styles["subseccion"]))
        story.append(Paragraph(
            "Se identifican las siguientes fuentes de recursos monetarios, físicos y legales:",
            styles["cuerpo"],
        ))
        story.append(Spacer(1, 0.15*cm))

        enc_f = [
            Paragraph("Tipo",           styles["tabla_header"]),
            Paragraph("Fuente / Entidad", styles["tabla_header"]),
            Paragraph("Descripción y cómo acceder", styles["tabla_header"]),
        ]
        filas_f = [enc_f]
        tipo_color = {
            "monetario":  _AZUL_CLARO,
            "físico":     _VERDE_CLARO,
            "legal":      _AMARILLO_CLARO,
            "técnico":    _NARANJA_CLARO,
        }
        for f in fuentes:
            tipo = str(f.get("tipo","")).lower()
            filas_f.append([
                Paragraph(f.get("tipo","").upper(), styles["tabla_cell_bold"]),
                Paragraph(str(f.get("entidad",""))[:80],    styles["tabla_cell_bold"]),
                Paragraph(str(f.get("descripcion",""))[:250], styles["tabla_cell"]),
            ])

        tabla_f = Table(filas_f, colWidths=[2.2*cm, 4.5*cm, 10.3*cm], repeatRows=1)
        estilo_f = _estilo_tabla_alternada()
        for i, f in enumerate(fuentes, 1):
            tipo = str(f.get("tipo","")).lower()
            bg   = tipo_color.get(tipo, _GRIS_CLARO)
            estilo_f.add("BACKGROUND", (0, i), (0, i), bg)
        tabla_f.setStyle(estilo_f)
        story.append(tabla_f)
        story.append(Spacer(1, 0.3*cm))

    # ── Recomendaciones para mejorar el plan ───────────────────────────────────
    recomendaciones = analisis_ia.get("recomendaciones_mejora", []) or []
    if recomendaciones:
        story.append(Paragraph("¿Cómo mejorar el plan?", styles["subseccion"]))
        for rec in recomendaciones:
            story.append(Paragraph(f"→ {rec}", styles["cuerpo"]))
        story.append(Spacer(1, 0.3*cm))

    # ── Competencias que no recaen en la entidad ───────────────────────────────
    no_propias = analisis_ia.get("competencias_no_propias", []) or []
    if no_propias:
        story.append(Paragraph("Competencias que no recaen en esta entidad — cómo gestionarlas", styles["subseccion"]))
        story.append(Paragraph(
            "Las siguientes responsabilidades tienen como titular principal a otro nivel de gobierno. "
            "La entidad puede impulsarlas mediante cofinanciación, convenios o solicitudes formales:",
            styles["cuerpo"],
        ))
        story.append(Spacer(1, 0.15*cm))
        enc_np = [
            Paragraph("Competencia",      styles["tabla_header"]),
            Paragraph("Titular real",     styles["tabla_header"]),
            Paragraph("Cómo gestionarla", styles["tabla_header"]),
            Paragraph("Norma / Formato",  styles["tabla_header"]),
        ]
        filas_np = [enc_np]
        for c in no_propias:
            filas_np.append([
                Paragraph(str(c.get("competencia", ""))[:120],     styles["tabla_cell_bold"]),
                Paragraph(str(c.get("responsable", ""))[:80],      styles["tabla_cell"]),
                Paragraph(str(c.get("como_gestionar", ""))[:240],  styles["tabla_cell"]),
                Paragraph(str(c.get("norma_o_formato", ""))[:120], styles["tabla_cell"]),
            ])
        tabla_np = Table(filas_np, colWidths=[4.0*cm, 3.0*cm, 6.5*cm, 3.5*cm], repeatRows=1)
        tabla_np.setStyle(_estilo_tabla_alternada())
        story.append(tabla_np)
        story.append(Spacer(1, 0.3*cm))

    # ── Mitigación de brechas ──────────────────────────────────────────────────
    mitigacion = analisis_ia.get("mitigacion_brechas", []) or []
    if mitigacion:
        story.append(Paragraph("¿Cómo mitigar las brechas detectadas?", styles["subseccion"]))
        enc_m = [
            Paragraph("Brecha",     styles["tabla_header"]),
            Paragraph("Severidad",  styles["tabla_header"]),
            Paragraph("Acción de mitigación", styles["tabla_header"]),
            Paragraph("Norma base", styles["tabla_header"]),
        ]
        filas_m = [enc_m]
        for m in sorted(mitigacion, key=lambda x: {"alta":0,"media":1,"baja":2}.get(str(x.get("severidad","baja")).lower(), 3)):
            filas_m.append([
                Paragraph(str(m.get("brecha", ""))[:120],   styles["tabla_cell_bold"]),
                _badge_severidad(str(m.get("severidad", "baja")).lower(), styles),
                Paragraph(str(m.get("accion", ""))[:280],   styles["tabla_cell"]),
                Paragraph(str(m.get("norma_base", ""))[:120], styles["tabla_cell"]),
            ])
        tabla_m = Table(filas_m, colWidths=[4.0*cm, 1.8*cm, 7.7*cm, 3.5*cm], repeatRows=1)
        tabla_m.setStyle(_estilo_tabla_alternada())
        story.append(tabla_m)
        story.append(Spacer(1, 0.3*cm))

    return story


def _pie_pagina(plan: dict, styles: dict) -> list:
    fecha_hoy = datetime.now().strftime("%d/%m/%Y %H:%M")
    return [
        Spacer(1, 0.5*cm),
        HRFlowable(width="100%", thickness=0.5, color=_GRIS_MEDIO),
        Paragraph(
            f"Informe generado el {fecha_hoy} · "
            f"Plan: {plan.get('titulo','')[:60]} · "
            f"Sistema de Gestión de Responsabilidades",
            styles["nota_pie"],
        ),
        Paragraph(
            "Este informe es un insumo técnico generado con apoyo de inteligencia artificial. "
            "Las decisiones administrativas deben ser validadas por el equipo jurídico y técnico competente.",
            styles["nota_pie"],
        ),
    ]


# ─── Estilo de tabla genérico ─────────────────────────────────────────────────

def _estilo_tabla_alternada() -> TableStyle:
    return TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  _AZUL_OSCURO),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  _BLANCO),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  8),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_BLANCO, _GRIS_CLARO]),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
    ])


# ─── Función principal ────────────────────────────────────────────────────────

def generar_pdf_analisis(plan: dict[str, Any], analisis_ia: dict[str, Any] | None = None) -> bytes:
    """
    Genera el PDF detallado del análisis de un plan de desarrollo.

    Args:
        plan: dict con campos del PlanDetail (titulo, entidad, nivel, periodo,
              descripcion, responsabilidades, normas, actores, brechas, matriz, etc.)

    Returns:
        Bytes del PDF listo para enviar como respuesta HTTP.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=1.8 * cm,
        bottomMargin=2.0 * cm,
        title=f"Análisis — {plan.get('titulo', 'Plan')}",
        author="Sistema de Gestión de Responsabilidades",
        subject="Informe detallado de análisis de plan de desarrollo",
    )

    styles = _build_styles()

    responsabilidades = plan.get("responsabilidades") or []
    normas            = plan.get("normas") or []
    actores           = plan.get("actores") or []
    brechas           = plan.get("brechas") or []
    matriz            = plan.get("matriz") or []

    story: list = []
    story += _portada(plan, styles)
    story += _seccion_responsabilidades(responsabilidades, styles)
    story.append(PageBreak())
    story += _seccion_marco_legal(normas, styles)
    story.append(PageBreak())
    story += _seccion_actores(actores, styles)
    story.append(PageBreak())
    story += _seccion_brechas(brechas, styles)
    story.append(PageBreak())
    story += _seccion_matriz(matriz, styles)
    story.append(PageBreak())
    story += _seccion_conclusiones(plan, responsabilidades, brechas, actores, normas, matriz, styles)
    if analisis_ia:
        story.append(PageBreak())
        story += _seccion_analisis_ia(analisis_ia, styles)
    story += _pie_pagina(plan, styles)

    doc.build(story)
    return buffer.getvalue()
