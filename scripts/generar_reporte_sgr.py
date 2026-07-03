# -*- coding: utf-8 -*-
"""
Genera el reporte PDF: Análisis de Pivote - Caja de Herramientas SGR
Municipios Categoría 5 y 6 - Colombia
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus.flowables import BalancedColumns
from reportlab.lib import colors
import datetime

# ── Paleta corporativa ────────────────────────────────────────────────────────
AZUL_PRINCIPAL   = HexColor("#1A3A5C")   # Azul gobierno
AZUL_MEDIO       = HexColor("#2E6DA4")   # Azul medio
AZUL_CLARO       = HexColor("#D6E8F7")   # Fondo tabla header
VERDE_SGR        = HexColor("#2E7D32")   # Verde regalías
VERDE_CLARO      = HexColor("#E8F5E9")   # Fondo verde suave
NARANJA_ALERTA   = HexColor("#E65100")   # Alerta
NARANJA_CLARO    = HexColor("#FFF3E0")   # Fondo naranja suave
GRIS_OSCURO      = HexColor("#37474F")
GRIS_MEDIO       = HexColor("#90A4AE")
GRIS_CLARO       = HexColor("#ECEFF1")
GRIS_LINEA       = HexColor("#CFD8DC")

W = A4[0] - 4*cm   # ancho útil

# ── Estilos ───────────────────────────────────────────────────────────────────
def build_styles():
    base = getSampleStyleSheet()

    s = {}

    s["portada_titulo"] = ParagraphStyle("portada_titulo",
        fontName="Helvetica-Bold", fontSize=24, textColor=white,
        alignment=TA_CENTER, spaceAfter=8, leading=30)

    s["portada_subtitulo"] = ParagraphStyle("portada_subtitulo",
        fontName="Helvetica", fontSize=14, textColor=HexColor("#B3D4F0"),
        alignment=TA_CENTER, spaceAfter=6, leading=18)

    s["portada_meta"] = ParagraphStyle("portada_meta",
        fontName="Helvetica", fontSize=10, textColor=HexColor("#CFD8DC"),
        alignment=TA_CENTER, spaceAfter=4)

    s["h1"] = ParagraphStyle("h1",
        fontName="Helvetica-Bold", fontSize=16, textColor=AZUL_PRINCIPAL,
        spaceBefore=18, spaceAfter=6, leading=20,
        borderPad=4)

    s["h2"] = ParagraphStyle("h2",
        fontName="Helvetica-Bold", fontSize=13, textColor=AZUL_MEDIO,
        spaceBefore=14, spaceAfter=4, leading=17)

    s["h3"] = ParagraphStyle("h3",
        fontName="Helvetica-Bold", fontSize=11, textColor=GRIS_OSCURO,
        spaceBefore=10, spaceAfter=3, leading=14)

    s["body"] = ParagraphStyle("body",
        fontName="Helvetica", fontSize=9.5, textColor=GRIS_OSCURO,
        spaceBefore=3, spaceAfter=3, leading=14, alignment=TA_JUSTIFY)

    s["body_bold"] = ParagraphStyle("body_bold",
        fontName="Helvetica-Bold", fontSize=9.5, textColor=GRIS_OSCURO,
        spaceBefore=2, spaceAfter=2, leading=14)

    s["bullet"] = ParagraphStyle("bullet",
        fontName="Helvetica", fontSize=9.5, textColor=GRIS_OSCURO,
        spaceBefore=2, spaceAfter=2, leading=13,
        leftIndent=14, bulletIndent=0)

    s["code"] = ParagraphStyle("code",
        fontName="Courier", fontSize=8.5, textColor=AZUL_PRINCIPAL,
        spaceBefore=2, spaceAfter=2, leading=12,
        leftIndent=10, backColor=GRIS_CLARO)

    s["caption"] = ParagraphStyle("caption",
        fontName="Helvetica-Oblique", fontSize=8, textColor=GRIS_MEDIO,
        alignment=TA_CENTER, spaceBefore=2, spaceAfter=6)

    s["tag_verde"] = ParagraphStyle("tag_verde",
        fontName="Helvetica-Bold", fontSize=8.5, textColor=VERDE_SGR,
        spaceBefore=1, spaceAfter=1)

    s["tag_naranja"] = ParagraphStyle("tag_naranja",
        fontName="Helvetica-Bold", fontSize=8.5, textColor=NARANJA_ALERTA,
        spaceBefore=1, spaceAfter=1)

    s["footer"] = ParagraphStyle("footer",
        fontName="Helvetica", fontSize=7.5, textColor=GRIS_MEDIO,
        alignment=TA_CENTER)

    return s

S = build_styles()


# ── Helpers visuales ──────────────────────────────────────────────────────────
def hr(color=GRIS_LINEA, thickness=0.5, space=4):
    return HRFlowable(width="100%", thickness=thickness, color=color,
                      spaceAfter=space, spaceBefore=space)

def section_box(title, color=AZUL_CLARO, text_color=AZUL_PRINCIPAL):
    """Encabezado de sección con fondo coloreado."""
    data = [[Paragraph(f"<b>{title}</b>",
                       ParagraphStyle("sh", fontName="Helvetica-Bold",
                                      fontSize=11, textColor=text_color))]]
    t = Table(data, colWidths=[W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), color),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("LINEBELOW", (0,-1), (-1,-1), 1.5, AZUL_MEDIO),
    ]))
    return t

def info_box(text, bg=AZUL_CLARO, border=AZUL_MEDIO):
    data = [[Paragraph(text, S["body"])]]
    t = Table(data, colWidths=[W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg),
        ("BOX", (0,0), (-1,-1), 1, border),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
    ]))
    return t

def alert_box(text, bg=NARANJA_CLARO, border=NARANJA_ALERTA):
    return info_box(text, bg=bg, border=border)

def two_col_table(rows, w1=7*cm, w2=None):
    w2 = w2 or (W - w1)
    rows = [[_p(c) for c in row] for row in rows]
    t = Table(rows, colWidths=[w1, w2])
    t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("TEXTCOLOR", (0,0), (-1,-1), GRIS_OSCURO),
        ("VALIGN",   (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [white, GRIS_CLARO]),
        ("LINEBELOW", (0,0), (-1,-2), 0.3, GRIS_LINEA),
    ]))
    return t

def _p(v):
    """Wrap plain string in Paragraph; pass anything else through."""
    if isinstance(v, str):
        return Paragraph(v, S["body"])
    return v

def _wrap_rows(rows):
    return [[_p(c) for c in row] for row in rows]

def header_table(headers, rows, col_widths=None):
    # headers is a list-of-rows (usually 1 row); rows is the body rows
    headers = _wrap_rows(headers)
    rows    = _wrap_rows(rows)
    n_cols  = len(headers[0]) if headers else 1
    col_widths = col_widths or [W / n_cols] * n_cols
    data = headers + rows
    t = Table(data, colWidths=col_widths, repeatRows=len(headers))
    nh = len(headers)  # number of header rows
    t.setStyle(TableStyle([
        # Header rows
        ("BACKGROUND",   (0,0), (-1, nh-1), AZUL_PRINCIPAL),
        ("TEXTCOLOR",    (0,0), (-1, nh-1), white),
        ("FONTNAME",     (0,0), (-1, nh-1), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1, nh-1), 9),
        ("ALIGN",        (0,0), (-1, nh-1), "CENTER"),
        # Body
        ("FONTNAME",     (0, nh), (-1,-1), "Helvetica"),
        ("FONTSIZE",     (0, nh), (-1,-1), 8.5),
        ("TEXTCOLOR",    (0, nh), (-1,-1), GRIS_OSCURO),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("ROWBACKGROUNDS", (0, nh), (-1,-1), [white, GRIS_CLARO]),
        ("GRID", (0,0), (-1,-1), 0.3, GRIS_LINEA),
        ("LINEBELOW", (0, nh-1), (-1, nh-1), 1.5, AZUL_MEDIO),
    ]))
    return t

def score_bar(label, pct, color=VERDE_SGR):
    """Barra de progreso visual en tabla."""
    filled = int(pct / 5)  # 20 bloques = 100%
    bar = "█" * filled + "░" * (20 - filled)
    rows = [[
        Paragraph(f"<b>{label}</b>", S["body_bold"]),
        Paragraph(f'<font color="#{color.hexval()[2:]}"><b>{bar}</b></font> {pct}%', S["body"]),
    ]]
    t = Table(rows, colWidths=[5.5*cm, W - 5.5*cm])
    t.setStyle(TableStyle([
        ("TOPPADDING",    (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    return t


# ── Portada ───────────────────────────────────────────────────────────────────
def build_portada():
    elements = []

    # Bloque de color superior
    header_data = [[
        Paragraph("REPÚBLICA DE COLOMBIA", S["portada_meta"]),
    ]]
    header_t = Table(header_data, colWidths=[W])
    header_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), AZUL_PRINCIPAL),
        ("TOPPADDING",    (0,0), (-1,-1), 40),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING",   (0,0), (-1,-1), 20),
        ("RIGHTPADDING",  (0,0), (-1,-1), 20),
    ]))
    elements.append(header_t)

    title_data = [[
        Paragraph("Caja de Herramientas SGR", S["portada_titulo"]),
    ]]
    title_t = Table(title_data, colWidths=[W])
    title_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), AZUL_PRINCIPAL),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 20),
        ("RIGHTPADDING",  (0,0), (-1,-1), 20),
    ]))
    elements.append(title_t)

    sub_data = [[
        Paragraph("Municipios de Categoría 5 y 6", S["portada_subtitulo"]),
    ]]
    sub_t = Table(sub_data, colWidths=[W])
    sub_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), AZUL_PRINCIPAL),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 20),
        ("RIGHTPADDING",  (0,0), (-1,-1), 20),
    ]))
    elements.append(sub_t)

    sub2_data = [[
        Paragraph("Sistema General de Regalías — Formulación y Guía de Proyectos", S["portada_subtitulo"]),
    ]]
    sub2_t = Table(sub2_data, colWidths=[W])
    sub2_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), AZUL_PRINCIPAL),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 40),
        ("LEFTPADDING",   (0,0), (-1,-1), 20),
        ("RIGHTPADDING",  (0,0), (-1,-1), 20),
    ]))
    elements.append(sub2_t)

    elements.append(Spacer(1, 1*cm))

    # Recuadro de descripción
    elements.append(info_box(
        "<b>Documento:</b> Análisis de Pivote Estratégico — Transformación del Sistema "
        "Gestor de Responsabilidades hacia una plataforma especializada en formulación "
        "de proyectos SGR para municipios pequeños de Colombia. Incluye diagnóstico del "
        "sistema actual, análisis de requerimientos específicos del SGR, arquitectura "
        "de la solución propuesta y hoja de ruta de implementación."
    ))

    elements.append(Spacer(1, 0.8*cm))

    # Metadatos
    fecha = datetime.date.today().strftime("%d de %B de %Y")
    meta_rows = [
        ["Fecha de emisión", fecha],
        ["Sistema base", "Web Gestor de Responsabilidades v1.0"],
        ["Enfoque nuevo", "SGR — Categorías 5 y 6 Colombia"],
        ["Marco normativo", "Ley 2056/2020 · Ley 1551/2012 · Ley 617/2000"],
        ["Herramienta obligatoria", "MGA Web — DNP Colombia"],
        ["Clasificación", "Documento de análisis técnico interno"],
    ]
    elements.append(two_col_table(
        [[Paragraph(r[0], S["body_bold"]), Paragraph(r[1], S["body"])] for r in meta_rows]
    ))

    elements.append(Spacer(1, 1*cm))
    elements.append(hr(AZUL_MEDIO, 1))
    elements.append(Paragraph(
        "Generado por el sistema de análisis inteligente de planes territoriales · "
        f"Darwin Fierro Ramírez © {datetime.date.today().year}",
        S["footer"]
    ))

    elements.append(PageBreak())
    return elements


# ── Índice ────────────────────────────────────────────────────────────────────
def build_indice():
    elements = []
    elements.append(section_box("TABLA DE CONTENIDO"))
    elements.append(Spacer(1, 0.3*cm))

    secciones = [
        ("1.", "Contexto: Municipios de Categoría 5 y 6 en Colombia"),
        ("2.", "El Sistema General de Regalías (SGR)"),
        ("3.", "Diagnóstico del Sistema Actual"),
        ("4.", "El Insight Central: Brechas → Proyectos SGR"),
        ("5.", "Los 5 Problemas Específicos y Soluciones"),
        ("6.", "Arquitectura de la Solución Propuesta"),
        ("7.", "Nuevos Agentes de IA"),
        ("8.", "Modelos de Datos Nuevos"),
        ("9.", "Lo que NO cambia (Reutilización)"),
        ("10.", "Lo que SÍ cambia"),
        ("11.", "Propuesta de Valor para el DNP"),
        ("12.", "Prioridad y Hoja de Ruta"),
        ("13.", "Riesgos y Mitigación"),
        ("14.", "Conclusión"),
        ("15.", "Modelo de Acceso: Verificación Cat. 5 y 6"),
        ("16.", "Onboarding Obligatorio: Contraseña + Plan de Desarrollo"),
        ("17.", "Flujo Completo del Producto (Modos 1 y 2 corregidos)"),
        ("18.", "Modo 2 Corregido: Evaluación + ¿Incluir en el Plan?"),
    ]

    for num, titulo in secciones:
        row = Table(
            [[Paragraph(f"<b>{num}</b>", S["body_bold"]),
              Paragraph(titulo, S["body"]),
              Paragraph("···", S["body"])]],
            colWidths=[1*cm, W - 2.5*cm, 1.5*cm]
        )
        row.setStyle(TableStyle([
            ("LEFTPADDING",   (0,0), (-1,-1), 4),
            ("RIGHTPADDING",  (0,0), (-1,-1), 4),
            ("TOPPADDING",    (0,0), (-1,-1), 3),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
            ("LINEBELOW",     (0,0), (-1,-1), 0.3, GRIS_LINEA),
            ("ALIGN", (2,0), (2,0), "RIGHT"),
        ]))
        elements.append(row)

    elements.append(PageBreak())
    return elements


# ── Sección 1: Contexto municipios ───────────────────────────────────────────
def build_s1():
    e = []
    e.append(section_box("1. CONTEXTO: MUNICIPIOS DE CATEGORÍA 5 Y 6 EN COLOMBIA"))
    e.append(Spacer(1, 0.3*cm))

    e.append(Paragraph("1.1 Clasificación Legal", S["h2"]))
    e.append(Paragraph(
        "En Colombia, la clasificación de municipios está establecida por la <b>Ley 617 de 2000</b> y "
        "reglamentada por la <b>Ley 1551 de 2012</b>. Los municipios de categoría 5 y 6 son las "
        "entidades territoriales de menor tamaño en términos poblacionales y de capacidad fiscal.",
        S["body"]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(header_table(
        [["Categoría", "Población", "ICLD (SMMLV)", "Característica principal"]],
        [
            ["Categoría 5", "10.001 – 20.000 hab.", "15.001 – 30.000", "Municipios pequeños con ICLD bajo"],
            ["Categoría 6", "Menos de 10.000 hab.", "Hasta 15.000", "Municipios rurales, mayor vulnerabilidad"],
        ],
        col_widths=[3*cm, 4*cm, 4*cm, W - 11*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("1.2 Características Críticas", S["h2"]))

    items = [
        ("<b>Capacidad técnica limitada:</b> No cuentan con funcionarios especializados en formulación de proyectos de inversión. La Secretaría de Planeación frecuentemente tiene 1–2 funcionarios para todas las funciones técnicas.",
        ),
        ("<b>NBI (Necesidades Básicas Insatisfechas):</b> El indicador de NBI ≤ 35% es un criterio de referencia para priorización en programas del SGR, especialmente para los fondos de equidad territorial. Municipios con NBI más alto tienen mayor urgencia de inversión.",
        ),
        ("<b>Dependencia de transferencias:</b> El SGP (Sistema General de Participaciones) y el SGR son sus principales fuentes de inversión. Los ICLD son muy bajos para financiar proyectos de infraestructura por cuenta propia.",
        ),
        ("<b>Dificultad técnica en formulación:</b> La MGA Web exige niveles de detalle técnico (árbol de problemas, indicadores de producto y resultado, análisis financiero) que superan la capacidad técnica instalada del municipio.",
        ),
        ("<b>Riesgo de inelegibilidad:</b> Proyectos rechazados en el OCAD por falta de requisitos formales, duplicidad o costos no acordes al promedio regional representan pérdida de tiempo y oportunidad de financiación.",
        ),
    ]
    for item in items:
        e.append(Paragraph(f"• {item[0]}", S["bullet"]))
        e.append(Spacer(1, 0.15*cm))

    e.append(Spacer(1, 0.3*cm))
    e.append(alert_box(
        "<b>⚠ Problema central:</b> Los municipios de categoría 5 y 6 son los que más necesitan "
        "recursos del SGR pero son los que menos capacidad tienen para formular proyectos "
        "que cumplan los requisitos técnicos para su aprobación en el OCAD."
    ))

    e.append(PageBreak())
    return e


# ── Sección 2: SGR ───────────────────────────────────────────────────────────
def build_s2():
    e = []
    e.append(section_box("2. EL SISTEMA GENERAL DE REGALÍAS (SGR)"))
    e.append(Spacer(1, 0.3*cm))

    e.append(Paragraph(
        "El SGR es el conjunto de ingresos, asignaciones, órganos, procedimientos y regulaciones "
        "mediante los cuales se distribuyen los ingresos provenientes de la explotación de recursos "
        "naturales no renovables. Está regulado principalmente por el <b>Acto Legislativo 05 de 2011</b>, "
        "la <b>Ley 2056 de 2020</b> y el <b>Decreto 1821 de 2020</b>.",
        S["body"]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("2.1 Asignaciones Relevantes para Cat. 5 y 6", S["h2"]))

    e.append(header_table(
        [["Asignación", "Porcentaje", "Acceso Cat. 5 y 6", "OCAD competente"]],
        [
            ["Asignación para la Paz", "7%", "Directo", "OCAD Paz"],
            ["Asignación Regional", "34.5%", "Via departamento", "OCAD Regional"],
            ["Asignación Local", "5%", "Directo (productores)", "OCAD Municipal"],
            ["Fondo de Ciencia y Tecnología", "10%", "Indirecto", "OCAD CTeI"],
            ["Asignación Ambiental", "1%", "Via corporaciones", "OCAD Ambiental"],
        ],
        col_widths=[5*cm, 2.5*cm, 3.5*cm, W - 11*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("2.2 Requisitos para Proyectos SGR", S["h2"]))

    requisitos = [
        ("Formulación MGA Web", "Obligatorio", "Metodología General Ajustada del DNP. Secciones: Identificación, Preparación, Evaluación, Programación."),
        ("Plan de Desarrollo", "Obligatorio", "El proyecto debe estar incluido en el Plan de Desarrollo del municipio vigente."),
        ("No duplicidad", "Obligatorio", "No puede haber otro proyecto con el mismo objeto ya financiado. Verificación en SUIFP-SGR / MapaInversiones."),
        ("Costos regionales", "Obligatorio", "Los valores unitarios deben corresponder al promedio regional, no pueden estar inflados."),
        ("Competencia territorial", "Obligatorio", "El municipio debe tener competencia legal para ejecutar el tipo de inversión."),
        ("Indicadores MGA", "Obligatorio", "Indicadores de producto y resultado alineados con el Marco de Gasto de Mediano Plazo."),
        ("NBI / focalización", "Recomendado", "Proyectos en municipios con mayor NBI tienen prioridad en evaluación OCAD."),
        ("Viabilidad técnica", "Recomendado", "Concepto de la entidad sectorial competente (MVCT, Min. Educación, etc.)"),
    ]

    e.append(header_table(
        [["Requisito", "Carácter", "Descripción"]],
        [[r[0], r[1], r[2]] for r in requisitos],
        col_widths=[4.5*cm, 2.5*cm, W - 7*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(info_box(
        "<b>El 15% SGR de referencia:</b> La norma establece que del presupuesto bienal del SGR, "
        "el 15% de las asignaciones directas regresa como 'Asignación de Paz'. Los costos de "
        "referencia para verificar el promedio regional se toman del histórico de proyectos "
        "aprobados en el OCAD departamental y los precios unitarios del DNP por sector y región "
        "geográfica (Andes, Caribe, Pacífico, Amazonía, Orinoquia)."
    ))

    e.append(PageBreak())
    return e


# ── Sección 3: Diagnóstico sistema actual ────────────────────────────────────
def build_s3():
    e = []
    e.append(section_box("3. DIAGNÓSTICO DEL SISTEMA ACTUAL"))
    e.append(Spacer(1, 0.3*cm))

    e.append(Paragraph(
        "El sistema 'Gestor de Responsabilidades' es una plataforma de análisis inteligente "
        "de planes de desarrollo territorial construida sobre una arquitectura RAG + multi-agente. "
        "A continuación se evalúa su estado actual y la alineación con el nuevo enfoque SGR.",
        S["body"]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("3.1 Stack Tecnológico", S["h2"]))

    e.append(header_table(
        [["Componente", "Tecnología", "Estado"]],
        [
            ["API Backend", "FastAPI (Python 3.12, async)", "✅ Producción"],
            ["Base de datos vectorial", "Qdrant — similitud coseno", "✅ Producción"],
            ["LLM local", "Ollama (llama3.1:8b)", "✅ Activo"],
            ["Embeddings", "nomic-embed-text (768d)", "✅ Calibrado para español legal"],
            ["Base de datos relacional", "MySQL 8.0", "✅ Producción"],
            ["Caché / SSE sessions", "Redis 7", "✅ Activo"],
            ["OCR", "pytesseract + pdf2image", "✅ Activo"],
            ["Frontend", "Angular 20 (Standalone)", "✅ MVP completo"],
            ["Contenedores", "Docker Compose", "✅ Dev + Prod"],
            ["Auth", "JWT + 3 roles (RBAC)", "✅ Activo"],
            ["Proveedor LLM alternativo", "Gemini / OpenAI / OpenRouter", "🟡 Configurado, no activo"],
        ],
        col_widths=[5*cm, 6*cm, W - 11*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("3.2 Agentes de IA Actuales", S["h2"]))

    e.append(header_table(
        [["Agente", "Propósito actual", "Aprovechamiento en SGR"]],
        [
            ["responsabilidades", "Extrae obligaciones del plan por tipo P/C/S/N", "Alto — identifica competencias municipales"],
            ["leyes", "Identifica normas aplicables con jerarquía jurídica", "Alto — marco legal del proyecto"],
            ["actores", "Mapea instituciones nacionales/depto/municipal", "Medio — identifica entidades cofinanciadoras"],
            ["brechas", "Audita gaps de cobertura y cumplimiento", "Muy alto — las brechas SON las oportunidades SGR"],
            ["matriz", "Consolida en MatrizCompetencia (P/C/S/N por nivel)", "Medio — valida competencia territorial"],
        ],
        col_widths=[3.5*cm, 6*cm, W - 9.5*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("3.3 Modelos de Datos Actuales (MVP)", S["h2"]))

    e.append(header_table(
        [["Modelo", "Campos clave", "Relevancia para SGR"]],
        [
            ["Plane", "titulo, nivel, estado, brechas_total, avance_pct", "Base — el plan de desarrollo es el input"],
            ["Brecha", "titulo, tipo, severidad, recomendacion, chunk_ids", "Central — seed de proyectos SGR"],
            ["Responsabilidad", "sector, tipo, referencia_legal, confidence_score", "Alta — valida competencia"],
            ["MatrizCompetencia", "nacion/depto/mpio (P/C/S/N), ley_base, brecha", "Alta — verifica quién puede ejecutar"],
            ["PlanNorma", "norma_codigo, tipo, vigente, relevancia", "Alta — marco normativo del proyecto"],
            ["BaseConocimiento", "qdrant_doc_id, estado, territorio", "Alta — base normativa SGR indexada"],
            ["User / Role", "email, rol_id, territorio, coleccion_id", "Sin cambios — RBAC por municipio"],
            ["AlertaNormativa", "norma_id, tipo_alerta, leida", "Útil — alertas de cambios SGR"],
        ],
        col_widths=[3.5*cm, 5.5*cm, W - 9*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("3.4 Madurez del Sistema", S["h2"]))
    e.append(Spacer(1, 0.2*cm))

    barras = [
        ("Infraestructura RAG", 95, VERDE_SGR),
        ("Orquestación multi-agente", 85, VERDE_SGR),
        ("Análisis de planes de desarrollo", 80, VERDE_SGR),
        ("Detección de brechas", 78, VERDE_SGR),
        ("Auth y multi-tenant básico", 85, VERDE_SGR),
        ("Frontend Angular (MVP)", 75, AZUL_MEDIO),
        ("Integración fuentes SGR externas", 5, NARANJA_ALERTA),
        ("Agente MGA Web", 0, NARANJA_ALERTA),
        ("Verificación de duplicidad", 0, NARANJA_ALERTA),
        ("Validación de costos regionales", 0, NARANJA_ALERTA),
    ]
    for label, pct, color in barras:
        e.append(score_bar(label, pct, color))

    e.append(PageBreak())
    return e


# ── Sección 4: Insight central ───────────────────────────────────────────────
def build_s4():
    e = []
    e.append(section_box("4. EL INSIGHT CENTRAL: BRECHAS → PROYECTOS SGR", VERDE_CLARO, VERDE_SGR))
    e.append(Spacer(1, 0.3*cm))

    e.append(Paragraph(
        "El descubrimiento más importante del análisis es que los dos sistemas — "
        "el análisis de responsabilidades y la formulación SGR — comparten exactamente "
        "el mismo punto de partida y el mismo insumo crítico:",
        S["body"]
    ))

    e.append(Spacer(1, 0.4*cm))

    # Flujo visual
    flujo = [
        ["Plan de Desarrollo\nMunicipal (PDF)", "→", "Sistema analiza\n(RAG + 5 agentes)", "→", "BRECHAS\ndetectadas"],
        ["", "", "", "", "↓"],
        ["", "", "", "", "Filtro SGR\nCat. 5/6"],
        ["", "", "", "", "↓"],
        ["", "", "", "", "Proyectos SGR\nelegibles"],
        ["", "", "", "", "↓"],
        ["", "", "", "", "Guía MGA Web\n(output final)"],
    ]

    t = Table([
        [
            Paragraph("<b>Plan de Desarrollo\nMunicipal</b>", ParagraphStyle("f", fontName="Helvetica-Bold", fontSize=9, alignment=TA_CENTER, textColor=white)),
            Paragraph("→", ParagraphStyle("ar", fontName="Helvetica-Bold", fontSize=16, alignment=TA_CENTER, textColor=AZUL_MEDIO)),
            Paragraph("<b>Sistema analiza\n(RAG + Agentes)</b>", ParagraphStyle("f", fontName="Helvetica-Bold", fontSize=9, alignment=TA_CENTER, textColor=white)),
            Paragraph("→", ParagraphStyle("ar", fontName="Helvetica-Bold", fontSize=16, alignment=TA_CENTER, textColor=AZUL_MEDIO)),
            Paragraph("<b>BRECHAS\ndetectadas</b>", ParagraphStyle("f", fontName="Helvetica-Bold", fontSize=9, alignment=TA_CENTER, textColor=white)),
            Paragraph("→", ParagraphStyle("ar", fontName="Helvetica-Bold", fontSize=16, alignment=TA_CENTER, textColor=AZUL_MEDIO)),
            Paragraph("<b>Filtro SGR\nCat. 5/6</b>", ParagraphStyle("f", fontName="Helvetica-Bold", fontSize=9, alignment=TA_CENTER, textColor=white)),
            Paragraph("→", ParagraphStyle("ar", fontName="Helvetica-Bold", fontSize=16, alignment=TA_CENTER, textColor=AZUL_MEDIO)),
            Paragraph("<b>Guía MGA Web\n(output final)</b>", ParagraphStyle("f", fontName="Helvetica-Bold", fontSize=9, alignment=TA_CENTER, textColor=white)),
        ]
    ], colWidths=[3.2*cm, 0.8*cm, 3.2*cm, 0.8*cm, 3.2*cm, 0.8*cm, 3.2*cm, 0.8*cm, 3.2*cm])

    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,0), AZUL_MEDIO),
        ("BACKGROUND", (2,0), (2,0), AZUL_MEDIO),
        ("BACKGROUND", (4,0), (4,0), VERDE_SGR),
        ("BACKGROUND", (6,0), (6,0), AZUL_MEDIO),
        ("BACKGROUND", (8,0), (8,0), VERDE_SGR),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
    ]))
    e.append(t)

    e.append(Spacer(1, 0.4*cm))
    e.append(Paragraph(
        "La clave es que una <b>brecha</b> detectada en el plan de desarrollo es, por definición, "
        "una necesidad insatisfecha del municipio que:",
        S["body"]
    ))
    e.append(Spacer(1, 0.15*cm))

    puntos = [
        "Ya está documentada en el instrumento de planeación vigente (cumple el requisito de estar en el Plan de Desarrollo)",
        "Tiene referencia legal que la sustenta (cumple el requisito de marco normativo de la MGA)",
        "Tiene un sector identificado (permite clasificar en los sectores SGR)",
        "Tiene una severidad asignada (permite priorizar por impacto)",
        "Tiene trazabilidad de chunk (evidencia documental para el expediente del proyecto)",
    ]
    for p in puntos:
        e.append(Paragraph(f"✓  {p}", S["bullet"]))

    e.append(Spacer(1, 0.3*cm))
    e.append(info_box(
        "<b>Conclusión del insight:</b> El sistema ya tiene el 60% del trabajo del formulador "
        "de proyectos SGR completado. Lo que falta es un capa de especialización que tome "
        "las brechas existentes, las filtre por elegibilidad SGR, y estructure el texto "
        "en formato MGA Web. Esto NO es una reescritura — es una extensión con alto retorno."
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("4.1 Mapeo Brecha → Sección MGA", S["h2"]))

    e.append(header_table(
        [["Campo actual (Brecha)", "Campo nuevo (ProyectoSGR)", "Sección MGA Web"]],
        [
            ["brecha.titulo", "proyecto.nombre", "1.1 Nombre del proyecto"],
            ["brecha.descripcion", "proyecto.descripcion_problema", "2.1 Descripción del problema central"],
            ["brecha.referencia_legal", "proyecto.marco_normativo", "2.3 Marco legal y normativo"],
            ["brecha.sector", "proyecto.sector_sgr", "1.3 Sector y subsector de inversión"],
            ["responsabilidad.tipo (P/C/S/N)", "proyecto.competencia_mpio", "1.4 Justificación de competencia"],
            ["brecha.severidad (alta/media/baja)", "proyecto.prioridad_sgr", "Criterio de priorización OCAD"],
            ["brecha.chunk_ids", "proyecto.fuentes_evidencia", "Anexo documental del expediente"],
            ["plan.titulo + fecha", "proyecto.inclusion_plan", "1.5 Vinculación Plan de Desarrollo"],
        ],
        col_widths=[5*cm, 5*cm, W - 10*cm]
    ))

    e.append(PageBreak())
    return e


# ── Sección 5: 5 problemas ───────────────────────────────────────────────────
def build_s5():
    e = []
    e.append(section_box("5. LOS 5 PROBLEMAS ESPECÍFICOS DE CAT. 5/6 Y SOLUCIONES"))
    e.append(Spacer(1, 0.3*cm))

    problemas = [
        {
            "num": "5.1",
            "titulo": "Formulación obligatoria en MGA Web",
            "problema": "La MGA Web del DNP es una herramienta técnicamente exigente que requiere estructurar el proyecto en secciones específicas: identificación del problema, árbol de causas y efectos, análisis de alternativas, indicadores de producto y resultado, presupuesto por fuentes, cronograma de actividades. Los municipios cat. 5/6 no tienen personal con ese nivel técnico.",
            "solucion": "El sistema genera automáticamente el texto de cada sección MGA a partir de la brecha detectada. El formulador copia/pega el texto generado en la MGA Web. No se reemplaza la MGA — se alimenta inteligentemente.",
            "nuevo": "agente_mga — toma brecha elegible y genera texto estructurado por sección MGA",
            "impacto": "Alto",
        },
        {
            "num": "5.2",
            "titulo": "No duplicidad con proyectos ya financiados",
            "problema": "Uno de los principales motivos de rechazo en el OCAD es la duplicidad con proyectos ya financiados con SGR, SGP u otras fuentes. El municipio no siempre tiene acceso ágil al SUIFP-SGR o MapaInversiones para verificar esto antes de formular.",
            "solucion": "El agente de duplicidad consulta MapaInversiones y SUIFP-SGR por municipio + sector + tipo de inversión. Usa similitud semántica en Qdrant para detectar proyectos similares aunque tengan nombres diferentes. Emite un veredicto con porcentaje de similitud.",
            "nuevo": "agente_duplicidad — integración MapaInversiones + similitud semántica Qdrant",
            "impacto": "Crítico (bloquea aprobación si no se detecta a tiempo)",
        },
        {
            "num": "5.3",
            "titulo": "Costos deben corresponder al promedio regional",
            "problema": "El OCAD rechaza proyectos con costos inflados o que no corresponden al promedio regional. No existe una fuente consolidada y de fácil acceso para municipios pequeños con los precios de referencia por tipo de inversión y región geográfica.",
            "solucion": "El agente de costos consulta: (1) el histórico de proyectos aprobados en el OCAD departamental por sector, (2) los índices del DANE por región, (3) los precios unitarios de referencia del DNP. Valida que el presupuesto esté dentro del ±20% del promedio regional.",
            "nuevo": "agente_costos — validador de presupuesto contra benchmarks DNP/DANE/histórico OCAD",
            "impacto": "Alto",
        },
        {
            "num": "5.4",
            "titulo": "El proyecto debe estar en el Plan de Desarrollo",
            "problema": "Muchos municipios formulan proyectos que no tienen respaldo explícito en su Plan de Desarrollo, lo que los hace inelegibles. La conexión entre el plan y el proyecto debe ser trazable y documentada.",
            "solucion": "El sistema parte precisamente del Plan de Desarrollo. Cada proyecto SGR generado lleva la referencia exacta al apartado del plan que lo sustenta (chunk_id, página, sector). Esto es evidencia directa para el expediente del OCAD.",
            "nuevo": "No requiere nuevo agente — el sistema ya lo hace. Solo ajuste de output para incluir referencia explícita.",
            "impacto": "Ya resuelto por la arquitectura actual",
        },
        {
            "num": "5.5",
            "titulo": "Asistencia técnica del DNP puede rechazar el proyecto",
            "problema": "El DNP ofrece asistencia técnica gratuita pero si el proyecto no cumple los requisitos básicos, el proceso técnico termina rápidamente ('puede morir el proyecto rápidamente'). La asistencia del DNP está diseñada para revisar, no para construir desde cero.",
            "solucion": "El sistema funciona como pre-validador antes de llegar al DNP. El municipio llega con: (1) duplicidad verificada, (2) costos validados, (3) competencia legal confirmada, (4) texto MGA pre-estructurado. El DNP solo revisa y perfecciona. Esto también hace al sistema candidato para ser adoptado como herramienta oficial de asistencia del DNP.",
            "nuevo": "Dashboard de pre-validación SGR — semáforo de requisitos antes de enviar al DNP",
            "impacto": "Muy alto — diferenciador estratégico",
        },
    ]

    for p in problemas:
        e.append(KeepTogether([
            Paragraph(f"{p['num']} {p['titulo']}", S["h2"]),
            Spacer(1, 0.15*cm),
        ]))

        rows = [
            [Paragraph("<b>Problema</b>", S["body_bold"]),
             Paragraph(p["problema"], S["body"])],
            [Paragraph("<b>Solución</b>", S["body_bold"]),
             Paragraph(p["solucion"], S["body"])],
            [Paragraph("<b>Nuevo componente</b>", S["body_bold"]),
             Paragraph(f'<font color="#2E7D32"><b>{p["nuevo"]}</b></font>', S["body"])],
            [Paragraph("<b>Impacto</b>", S["body_bold"]),
             Paragraph(p["impacto"], S["body"])],
        ]
        t = Table(rows, colWidths=[3.5*cm, W - 3.5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (0,-1), GRIS_CLARO),
            ("VALIGN",    (0,0), (-1,-1), "TOP"),
            ("TOPPADDING",    (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
            ("RIGHTPADDING",  (0,0), (-1,-1), 8),
            ("GRID", (0,0), (-1,-1), 0.3, GRIS_LINEA),
            ("LINEBELOW", (0,-1), (-1,-1), 1.5, AZUL_MEDIO),
        ]))
        e.append(t)
        e.append(Spacer(1, 0.4*cm))

    e.append(PageBreak())
    return e


# ── Sección 6: Arquitectura ──────────────────────────────────────────────────
def build_s6():
    e = []
    e.append(section_box("6. ARQUITECTURA DE LA SOLUCIÓN PROPUESTA"))
    e.append(Spacer(1, 0.3*cm))

    e.append(Paragraph(
        "La arquitectura mantiene el núcleo existente (RAG + orquestador) y agrega un nuevo "
        "<b>slice SGR</b> con agentes especializados. La separación en slices verticales asegura "
        "que el nuevo código no afecte la funcionalidad existente.",
        S["body"]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("6.1 Estructura de Directorios Nueva", S["h2"]))

    estructura = [
        ("app/slices/sgr/", "Nuevo slice vertical para toda la lógica SGR"),
        ("app/slices/sgr/agents/", "Los 4 nuevos agentes especializados"),
        ("app/slices/sgr/agents/agente_elegibilidad.py", "Criterios específicos cat. 5/6"),
        ("app/slices/sgr/agents/agente_mga.py", "Generador de texto para secciones MGA"),
        ("app/slices/sgr/agents/agente_duplicidad.py", "Cruce con MapaInversiones + Qdrant"),
        ("app/slices/sgr/agents/agente_costos.py", "Validador de presupuesto regional"),
        ("app/slices/sgr/models.py", "ProyectoSGR, FichaMGA, ResultadoDuplicidad"),
        ("app/slices/sgr/service.py", "Pipeline de evaluación completo"),
        ("app/slices/sgr/router.py", "Endpoints: /sgr/evaluar, /sgr/ficha, /sgr/dashboard"),
        ("app/slices/sgr/prompts/", "Templates para agentes SGR"),
        ("app/slices/sgr/prompts/elegibilidad_sgr.md", "Criterios de elegibilidad SGR cat. 5/6"),
        ("app/slices/sgr/prompts/formulacion_mga.md", "Estructura de secciones MGA"),
        ("app/slices/sgr/prompts/scoring_aprobacion.md", "Criterios de probabilidad OCAD"),
        ("app/slices/sgr/external/", "Integraciones con fuentes externas"),
        ("app/slices/sgr/external/mapa_inversiones.py", "Cliente MapaInversiones DNP"),
        ("app/slices/sgr/external/costos_dnp.py", "Precios unitarios DNP/DANE"),
    ]

    for path, desc in estructura:
        nivel = path.count("/") - path.replace("app/slices/sgr/", "").count("/") - 1
        indent = "  " * min(nivel, 3)
        is_dir = path.endswith("/")
        color = AZUL_PRINCIPAL if is_dir else GRIS_OSCURO
        font = "Helvetica-Bold" if is_dir else "Helvetica"
        e.append(Paragraph(
            f'<font name="{font}" color="#{color.hexval()[2:]}">{indent}{"📁 " if is_dir else "📄 "}{path.split("/")[-1] or path.split("/")[-2]+"/"}   <font name="Helvetica" size="8" color="#90A4AE">→ {desc}</font></font>',
            ParagraphStyle("code2", fontName="Courier", fontSize=8, leading=13, spaceBefore=1, spaceAfter=1)
        ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("6.2 Flujo de Procesamiento SGR", S["h2"]))

    pasos = [
        ("1", "Carga Plan de Desarrollo", "PDF del municipio → OCR → indexación Qdrant (EXISTENTE)"),
        ("2", "Análisis multi-agente", "5 agentes actuales → brechas, responsabilidades, leyes (EXISTENTE)"),
        ("3", "Evaluación de elegibilidad SGR", "agente_elegibilidad filtra brechas por criterios SGR cat. 5/6 (NUEVO)"),
        ("4", "Verificación de duplicidad", "agente_duplicidad consulta MapaInversiones + similitud semántica (NUEVO)"),
        ("5", "Validación de costos", "agente_costos compara con benchmarks regionales DNP/DANE (NUEVO)"),
        ("6", "Scoring de viabilidad", "Ponderación: severidad + elegibilidad + duplicidad + costos (NUEVO)"),
        ("7", "Generación MGA", "agente_mga estructura texto por sección MGA Web (NUEVO)"),
        ("8", "Dashboard pre-validación", "Semáforo de requisitos + ficha lista para ingresar al DNP (NUEVO)"),
    ]

    e.append(header_table(
        [["#", "Paso", "Descripción"]],
        pasos,
        col_widths=[0.7*cm, 5.3*cm, W - 6*cm]
    ))

    e.append(PageBreak())
    return e


# ── Sección 7: Nuevos agentes ────────────────────────────────────────────────
def build_s7():
    e = []
    e.append(section_box("7. NUEVOS AGENTES DE IA"))
    e.append(Spacer(1, 0.3*cm))

    agentes = [
        {
            "nombre": "agente_elegibilidad",
            "descripcion": "Evalúa si una brecha detectada en el plan de desarrollo cumple los criterios para ser financiada con recursos SGR para municipios de categoría 5 y 6.",
            "inputs": "brecha (titulo, descripcion, sector, severidad, referencia_legal), datos_municipio (categoria, NBI, ICLD, departamento)",
            "outputs": "elegible: bool, razon: str, sector_sgr: str, subsector: str, tipo_inversion: str, condiciones: list",
            "criterios": [
                "Sector habilitado por SGR (infraestructura, educación, salud, agua potable, etc.)",
                "Competencia del municipio confirmada (MatrizCompetencia existente)",
                "Municipio categoría 5 o 6 verificado",
                "Inversión no excede topes SGR por categoría",
                "Brecha no está cubierta por SGP obligatorio",
            ],
            "prompt_key": "elegibilidad_sgr.md",
        },
        {
            "nombre": "agente_duplicidad",
            "descripcion": "Verifica que no exista un proyecto con el mismo objeto ya financiado con recursos del SGR u otras fuentes en el mismo municipio o área de influencia.",
            "inputs": "brecha elegible, municipio_codigo (DIVIPOLA), sector_sgr, tipo_inversion, alcance_geografico",
            "outputs": "tiene_duplicidad: bool, similitud_max: float, proyectos_similares: list[{nombre, fuente, año, similitud}], veredicto: str",
            "criterios": [
                "Consulta MapaInversiones DNP por municipio + sector",
                "Similitud semántica en Qdrant contra proyectos indexados",
                "Umbral de duplicidad: similitud > 0.85 = bloqueante",
                "Rango medio: 0.60–0.85 = requiere diferenciación",
                "Considera proyectos de los últimos 6 años",
            ],
            "prompt_key": "duplicidad.md",
        },
        {
            "nombre": "agente_mga",
            "descripcion": "Genera el texto estructurado para cada sección de la MGA Web, tomando como insumo la brecha elegible y los datos del municipio.",
            "inputs": "brecha elegible, datos_municipio, resultado_duplicidad, contexto_plan (chunks relevantes)",
            "outputs": "ficha_mga: {identificacion, preparacion, evaluacion, programacion} — texto listo para copiar en MGA Web",
            "criterios": [
                "Sección 1: Identificación — nombre, sector, municipio, justificación de competencia",
                "Sección 2: Preparación — problema central, árbol de causas/efectos, población objetivo",
                "Sección 3: Evaluación — indicadores de producto y resultado, costo por beneficiario",
                "Sección 4: Programación — fuentes de financiación, actividades, cronograma, sostenibilidad",
            ],
            "prompt_key": "formulacion_mga.md",
        },
        {
            "nombre": "agente_costos",
            "descripcion": "Valida que el presupuesto estimado del proyecto corresponda al promedio regional, usando referencias del DNP, DANE e histórico de proyectos aprobados en el OCAD departamental.",
            "inputs": "tipo_inversion, unidad_medida, cantidad, departamento, region_geografica (Andes/Caribe/Pacífico/Amazonía/Orinoquia)",
            "outputs": "costo_referencia: {minimo, promedio, maximo}, estado: str (ok/alerta/bloqueante), recomendacion: str, fuente: str",
            "criterios": [
                "Precio unitario DNP por tipo de inversión y región",
                "Índice de Costos de Construcción DANE por departamento",
                "Histórico proyectos aprobados OCAD (últimos 3 años, mismo departamento)",
                "Tolerancia: ±20% del promedio = aceptable",
                "Mayor a +20%: alerta; mayor a +40%: bloqueante",
            ],
            "prompt_key": "validacion_costos.md",
        },
    ]

    for ag in agentes:
        e.append(KeepTogether([
            Paragraph(f'7.x <font color="#2E7D32"><b>{ag["nombre"]}</b></font>', S["h2"]),
        ]))
        e.append(Paragraph(ag["descripcion"], S["body"]))
        e.append(Spacer(1, 0.2*cm))

        detail_rows = [
            [Paragraph("<b>Inputs</b>", S["body_bold"]), Paragraph(ag["inputs"], S["body"])],
            [Paragraph("<b>Outputs</b>", S["body_bold"]), Paragraph(ag["outputs"], S["body"])],
        ]
        dt = Table(detail_rows, colWidths=[3*cm, W - 3*cm])
        dt.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (0,-1), VERDE_CLARO),
            ("VALIGN",    (0,0), (-1,-1), "TOP"),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
            ("RIGHTPADDING",  (0,0), (-1,-1), 8),
            ("GRID", (0,0), (-1,-1), 0.3, GRIS_LINEA),
        ]))
        e.append(dt)
        e.append(Spacer(1, 0.15*cm))

        e.append(Paragraph("<b>Criterios de evaluación:</b>", S["body_bold"]))
        for criterio in ag["criterios"]:
            e.append(Paragraph(f"• {criterio}", S["bullet"]))
        e.append(Spacer(1, 0.4*cm))

    e.append(PageBreak())
    return e


# ── Sección 8: Nuevos modelos ────────────────────────────────────────────────
def build_s8():
    e = []
    e.append(section_box("8. MODELOS DE DATOS NUEVOS"))
    e.append(Spacer(1, 0.3*cm))

    e.append(Paragraph("8.1 ProyectoSGR", S["h2"]))
    e.append(header_table(
        [["Campo", "Tipo", "Descripción"]],
        [
            ["id", "UUID PK", "Identificador único del proyecto"],
            ["brecha_id", "UUID FK → Brecha", "Brecha origen del proyecto"],
            ["plan_id", "UUID FK → Plane", "Plan de desarrollo fuente"],
            ["municipio_codigo", "VARCHAR(8)", "Código DIVIPOLA del municipio"],
            ["nombre", "TEXT", "Nombre del proyecto (generado)"],
            ["sector_sgr", "VARCHAR(50)", "Sector SGR clasificado"],
            ["tipo_inversion", "VARCHAR(80)", "Tipo específico de inversión"],
            ["score_sgr", "FLOAT", "Score de viabilidad 0-1"],
            ["elegible", "BOOLEAN", "Cumple criterios SGR cat. 5/6"],
            ["razon_inelegibilidad", "TEXT", "Si no elegible, por qué"],
            ["resultado_duplicidad", "JSON", "Resultado verificación duplicidad"],
            ["validacion_costos", "JSON", "Resultado validación presupuesto"],
            ["ficha_mga", "JSON", "Texto de secciones MGA generado"],
            ["estado", "ENUM", "borrador | listo | enviado_dnp | aprobado | rechazado"],
            ["creado_en", "TIMESTAMP", "Fecha de generación"],
            ["actualizado_en", "TIMESTAMP", "Última modificación"],
        ],
        col_widths=[4*cm, 3.5*cm, W - 7.5*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("8.2 FichaMGA (JSON embebido en ProyectoSGR)", S["h2"]))

    e.append(header_table(
        [["Sección MGA", "Subsección", "Contenido generado"]],
        [
            ["1. Identificación", "1.1 Nombre", "Nombre técnico del proyecto"],
            ["1. Identificación", "1.3 Sector/Subsector", "Clasificación SGR"],
            ["1. Identificación", "1.4 Competencia", "Justificación legal del municipio"],
            ["1. Identificación", "1.5 Plan Desarrollo", "Referencia con página/capítulo"],
            ["2. Preparación", "2.1 Problema", "Descripción del problema central"],
            ["2. Preparación", "2.2 Árbol causas", "Causas directas e indirectas"],
            ["2. Preparación", "2.3 Marco legal", "Normas identificadas por agente_leyes"],
            ["2. Preparación", "2.4 Población", "Población afectada y beneficiaria"],
            ["3. Evaluación", "3.1 Indicadores", "Producto y resultado con línea base"],
            ["3. Evaluación", "3.2 Costo/beneficiario", "Presupuesto validado agente_costos"],
            ["4. Programación", "4.1 Fuentes", "SGR + cofinanciación + aporte mpio"],
            ["4. Programación", "4.2 Actividades", "Cronograma básico de ejecución"],
        ],
        col_widths=[3.5*cm, 3.5*cm, W - 7*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("8.3 Scoring de Viabilidad SGR", S["h2"]))
    e.append(Paragraph(
        "El score_sgr (0.0 – 1.0) se calcula como una ponderación de cuatro factores:",
        S["body"]
    ))

    e.append(header_table(
        [["Factor", "Peso", "Fuente del dato", "Rango"]],
        [
            ["Severidad de la brecha", "30%", "agente_brechas (existente)", "alta=1.0 / media=0.6 / baja=0.3"],
            ["Alineación Plan Desarrollo", "25%", "agente_responsabilidades (existente)", "0.0 – 1.0 (confidence)"],
            ["Elegibilidad SGR cat. 5/6", "25%", "agente_elegibilidad (nuevo)", "elegible=1.0 / no=0.0"],
            ["Probabilidad aprobación", "20%", "histórico OCAD + similitud", "0.0 – 1.0 basado en historico"],
        ],
        col_widths=[4.5*cm, 1.5*cm, 5*cm, W - 11*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(info_box(
        "<b>Ejemplo:</b> Una brecha de severidad alta (1.0 × 0.30 = 0.30) con alta alineación "
        "al plan (0.85 × 0.25 = 0.21), elegible para SGR (1.0 × 0.25 = 0.25) y con media "
        "probabilidad histórica (0.65 × 0.20 = 0.13) obtiene un score total de 0.89/1.0 — "
        "clasificado como ALTA VIABILIDAD."
    ))

    e.append(PageBreak())
    return e


# ── Sección 9: Qué no cambia ─────────────────────────────────────────────────
def build_s9():
    e = []
    e.append(section_box("9. LO QUE NO CAMBIA — REUTILIZACIÓN", VERDE_CLARO, VERDE_SGR))
    e.append(Spacer(1, 0.3*cm))

    e.append(Paragraph(
        "Una de las principales fortalezas del pivote es que el 70% de la infraestructura "
        "existente se reutiliza sin modificaciones. Esto reduce drásticamente el riesgo técnico "
        "y el tiempo de implementación.",
        S["body"]
    ))
    e.append(Spacer(1, 0.3*cm))

    reutilizacion = [
        ("RAG (Qdrant + embeddings nomic)", "Sin cambios", "Verde"),
        ("OCR híbrido (pytesseract + PDF nativo)", "Sin cambios", "Verde"),
        ("JWT Auth + RBAC 3 roles", "Sin cambios", "Verde"),
        ("Docker Compose (todos los servicios)", "Sin cambios", "Verde"),
        ("SSE streaming con Redis sessions", "Sin cambios", "Verde"),
        ("Agente responsabilidades", "Sin cambios", "Verde"),
        ("Agente leyes", "Sin cambios", "Verde"),
        ("Agente actores", "Sin cambios", "Verde"),
        ("Coordinador (coordinator.py)", "Sin cambios", "Verde"),
        ("Pipeline de análisis (service.py)", "Sin cambios", "Verde"),
        ("Modelos Plane, Responsabilidad, PlanNorma", "Sin cambios", "Verde"),
        ("Frontend: login, biblioteca, cargar-plan", "Sin cambios", "Verde"),
        ("Frontend: busqueda-raag, base-conocimiento", "Sin cambios", "Verde"),
        ("Scraper de normas (web_search.py)", "Sin cambios — se reutiliza para SGR", "Verde"),
        ("Agente brechas", "Ajuste de prompts (+2 campos SGR)", "Amarillo"),
        ("Modelo Brecha", "Agregar elegibilidad_sgr + sector_sgr", "Amarillo"),
        ("Base de conocimiento", "Agregar documentos SGR específicos", "Amarillo"),
    ]

    for comp, estado, nivel in reutilizacion:
        color = VERDE_SGR if nivel == "Verde" else HexColor("#F57F17")
        icono = "✅" if nivel == "Verde" else "🟡"
        e.append(Paragraph(
            f'{icono}  <b>{comp}</b> — <font color="#{color.hexval()[2:]}">{estado}</font>',
            S["bullet"]
        ))

    e.append(Spacer(1, 0.3*cm))
    e.append(info_box(
        "<b>Resumen de reutilización:</b> 14 componentes sin cambios, 3 con ajustes menores. "
        "Los 4 nuevos agentes SGR y los nuevos modelos son adiciones puras — "
        "no modifican código existente. Esto garantiza que el sistema actual sigue "
        "funcionando mientras se construye la capa SGR."
    ))

    e.append(PageBreak())
    return e


# ── Sección 10: Qué cambia ───────────────────────────────────────────────────
def build_s10():
    e = []
    e.append(section_box("10. LO QUE SÍ CAMBIA"))
    e.append(Spacer(1, 0.3*cm))

    cambios = [
        {
            "titulo": "Nuevo prompt: agente_brechas (data/prompts/brechas.md)",
            "detalle": "Agregar instrucción para que el agente clasifique cada brecha según sectores SGR habilitados y asigne sector_sgr + subsector_sgr. Cambio de ~8 líneas en el template existente."
        },
        {
            "titulo": "Nuevo campo en modelo Brecha",
            "detalle": "Agregar elegibilidad_sgr (bool nullable), sector_sgr (varchar nullable) a la tabla brechas. Requiere migración Alembic simple (ALTER TABLE)."
        },
        {
            "titulo": "Nuevo slice: app/slices/sgr/ (8 archivos nuevos)",
            "detalle": "Slice completamente nuevo: models.py, service.py, router.py, 4 agentes, 4 templates de prompts, 2 clientes externos. No modifica ningún slice existente."
        },
        {
            "titulo": "Nueva feature frontend: formulador-sgr/",
            "detalle": "4 componentes nuevos Angular: evaluacion-brechas (lista con scores), ficha-proyecto (preview MGA), duplicidad-check (resultado verificación), calculadora-costos (validador presupuesto). Ruta: /sgr/formulador."
        },
        {
            "titulo": "Base de conocimiento SGR",
            "detalle": "Indexar en Qdrant los documentos base del SGR: Ley 2056/2020, Decreto 1821/2020, Circular DNP MGA, precios unitarios DNP por región. Colección separada: 'SGR_COLOMBIA'."
        },
        {
            "titulo": "Datos de referencia de costos (nueva tabla)",
            "detalle": "Tabla costos_referencia_sgr: tipo_inversion, region_geografica, unidad, valor_min, valor_promedio, valor_max, fuente, año. Inicial: cargado desde Excel DNP."
        },
        {
            "titulo": "Integración MapaInversiones (cliente HTTP)",
            "detalle": "Cliente Python para consultar la API pública de MapaInversiones del DNP. Búsqueda por código DIVIPOLA + sector + tipo inversión. Cache Redis 24h para evitar rate limiting."
        },
        {
            "titulo": "Variable de perfil: categoria_municipio",
            "detalle": "Agregar al modelo User/territorio: categoria (5|6), nbi, icld. Se usa para validar elegibilidad y personalizar los criterios del agente_elegibilidad."
        },
    ]

    for c in cambios:
        e.append(KeepTogether([
            Paragraph(f"▶  {c['titulo']}", S["body_bold"]),
            Paragraph(c["detalle"], S["body"]),
            Spacer(1, 0.15*cm),
        ]))

    e.append(PageBreak())
    return e


# ── Sección 11: Propuesta DNP ────────────────────────────────────────────────
def build_s11():
    e = []
    e.append(section_box("11. PROPUESTA DE VALOR PARA EL DNP", VERDE_CLARO, VERDE_SGR))
    e.append(Spacer(1, 0.3*cm))

    e.append(Paragraph(
        "El DNP (Departamento Nacional de Planeación) ofrece asistencia técnica gratuita "
        "a municipios pequeños para la formulación de proyectos SGR. Esta asistencia tiene "
        "alta demanda y capacidad limitada. El sistema puede convertirse en un multiplicador "
        "de esa capacidad técnica.",
        S["body"]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("11.1 Comparativa: Asistencia Actual vs. Con el Sistema", S["h2"]))

    e.append(header_table(
        [["Aspecto", "Asistencia técnica actual DNP", "Con el sistema SGR"]],
        [
            ["Punto de partida", "El municipio llega con idea vaga del proyecto", "El municipio llega con TOP 3 proyectos viables identificados"],
            ["Tiempo de estructuración", "4–8 semanas por proyecto", "1–2 semanas (texto MGA pre-generado)"],
            ["Verificación duplicidad", "Manual en SUIFP (días)", "Automática en segundos"],
            ["Validación de costos", "Criterio del asesor DNP", "Automática contra benchmarks DNP/DANE"],
            ["Capacidad simultánea", "1 asesor ≈ 5-8 municipios/año", "Sistema atiende ilimitado en paralelo"],
            ["Calidad del proyecto", "Depende de experiencia del asesor", "Estandarizada con criterios DNP"],
            ["Costo operativo DNP", "Alta (horas asesor por municipio)", "Baja (revisión sobre borrador generado)"],
            ["Trazabilidad normativa", "Manual", "Automática con chunks y confidence"],
        ],
        col_widths=[4*cm, 6*cm, W - 10*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("11.2 Modelo de Adopción Propuesto", S["h2"]))

    pasos = [
        ("Piloto", "3 municipios cat. 5/6 voluntarios formulan 1 proyecto cada uno con el sistema. Se mide tiempo, calidad y tasa de aprobación OCAD vs. control."),
        ("Validación DNP", "DNP revisa los proyectos generados. Se reciben retroalimentaciones para ajustar los agentes y los templates de prompts."),
        ("Integración como herramienta DNP", "El DNP adopta el sistema como canal digital de pre-formulación para municipios cat. 5/6 antes de solicitar asistencia técnica."),
        ("Escalamiento", "Extensión a otros programas: SGP, OCAD Paz, Asignación CTeI. Ampliación a municipios de otras categorías."),
    ]

    for titulo, desc in pasos:
        e.append(Paragraph(f"<b>{titulo}:</b> {desc}", S["bullet"]))
        e.append(Spacer(1, 0.1*cm))

    e.append(Spacer(1, 0.3*cm))
    e.append(alert_box(
        "<b>Diferenciador estratégico:</b> El sistema no compite con el DNP — lo potencia. "
        "Al estandarizar la pre-formulación, el DNP puede enfocar su capacidad técnica "
        "en los casos más complejos y en la revisión de calidad, no en la formulación desde cero."
    ))

    e.append(PageBreak())
    return e


# ── Sección 12: Hoja de ruta ─────────────────────────────────────────────────
def build_s12():
    e = []
    e.append(section_box("12. PRIORIDAD Y HOJA DE RUTA"))
    e.append(Spacer(1, 0.3*cm))

    e.append(header_table(
        [["Fase", "Duración", "Componentes", "Resultado"]],
        [
            [
                "Fase 1\nReutilización",
                "2–3 semanas",
                "• Ajuste prompt agente_brechas (+sector_sgr)\n• Migración Alembic (+2 campos Brecha)\n• Agente elegibilidad (criterios cat. 5/6)\n• Ruta /sgr/evaluar-plan/{id}\n• Scoring simple viabilidad SGR",
                "Sistema clasifica brechas por elegibilidad SGR. Output: TOP N brechas con score."
            ],
            [
                "Fase 2\nNuevas capacidades",
                "3–4 semanas",
                "• Agente MGA (text generation)\n• Integración MapaInversiones\n• Agente duplicidad\n• Modelos ProyectoSGR + FichaMGA\n• Frontend: evaluacion-brechas + ficha-proyecto",
                "Sistema genera ficha MGA completa y verifica duplicidad automáticamente."
            ],
            [
                "Fase 3\nDiferenciación",
                "4–5 semanas",
                "• Agente costos (benchmarks DNP/DANE)\n• Tabla costos_referencia_sgr\n• Dashboard pre-validación (semáforo)\n• Frontend: duplicidad-check + calculadora\n• Ranking probabilidad aprobación OCAD",
                "Pre-validador completo. Municipio llega al DNP con proyecto 95% listo."
            ],
            [
                "Fase 4\nPiloto DNP",
                "4–6 semanas",
                "• Piloto con 3 municipios reales\n• Retroalimentación DNP en prompts\n• Ajuste modelos scoring\n• Documentación técnica para DNP\n• Export Word/Excel compatible MGA",
                "Propuesta formal al DNP como herramienta de asistencia técnica oficial."
            ],
        ],
        col_widths=[2.5*cm, 2.5*cm, 7.5*cm, W - 12.5*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("12.1 Dependencias Críticas", S["h2"]))

    deps = [
        ("API MapaInversiones DNP", "Crítica", "El agente_duplicidad requiere acceso a datos de proyectos financiados. Si no hay API pública, se puede usar scraping o carga manual periódica del SUIFP-SGR."),
        ("Precios unitarios DNP", "Alta", "El agente_costos necesita tabla de referencia. Disponible en portal DNP como Excel descargable. Carga inicial manual, actualización semestral."),
        ("Documentos SGR en Qdrant", "Alta", "La base de conocimiento debe incluir Ley 2056/2020, Decreto 1821/2020, circulares DNP y MGA. Indexación única al inicio."),
        ("LLM con contexto largo", "Media", "La generación MGA puede requerir contexto > 8k tokens. Validar con llama3.1:8b o considerar llama3.3:70b para mayor calidad de texto."),
        ("Datos municipio (categoria, NBI)", "Media", "Necesarios para elegibilidad. Disponibles en DIVIPOLA DNP y Terridata. Carga al crear usuario-municipio."),
    ]

    for dep, criticidad, desc in deps:
        color = NARANJA_ALERTA if criticidad == "Crítica" else (AZUL_MEDIO if criticidad == "Alta" else GRIS_MEDIO)
        e.append(Paragraph(
            f'<b>{dep}</b> — <font color="#{color.hexval()[2:]}">Prioridad: {criticidad}</font>',
            S["body_bold"]
        ))
        e.append(Paragraph(desc, S["body"]))
        e.append(Spacer(1, 0.15*cm))

    e.append(PageBreak())
    return e


# ── Sección 13: Riesgos ───────────────────────────────────────────────────────
def build_s13():
    e = []
    e.append(section_box("13. RIESGOS Y MITIGACIÓN"))
    e.append(Spacer(1, 0.3*cm))

    riesgos = [
        ("Duplicidad no detectada llega al OCAD", "Crítico", "Alto", "El agente_duplicidad falle por falta de datos o similitud mal calibrada. Proyectos duplicados son rechazados y generan pérdida de credibilidad.",
         "Umbral de similitud conservador (0.70 = alerta, 0.85 = bloqueo). Verificación manual obligatoria antes de envío. Avisos claros en el dashboard."),
        ("Datos de costos desactualizados", "Alto", "Medio", "Si los precios de referencia no se actualizan, el agente puede validar presupuestos inflados o subestimados.",
         "Fecha de vigencia visible en cada validación. Alerta automática si datos > 6 meses. Proceso semestral de actualización de tabla costos_referencia_sgr."),
        ("Calidad del texto MGA insuficiente", "Alto", "Medio", "El agente_mga puede generar texto genérico que el OCAD rechace por no tener el nivel técnico requerido.",
         "Validación con técnico DNP antes de Fase 3. Iteración de prompts basada en retroalimentación real. Marcar claramente que el texto es un borrador inicial."),
        ("Plan de desarrollo de baja calidad", "Medio", "Alto", "Municipios cat. 5/6 pueden tener planes de desarrollo muy genéricos, con pocas brechas detectables, limitando el output del sistema.",
         "Agregar base de conocimiento sectorial SGR para complementar análisis cuando el plan es pobre. Instrucciones en onboarding sobre requisitos mínimos del plan."),
        ("Resistencia institucional DNP", "Medio", "Bajo", "El DNP puede no adoptar una herramienta no desarrollada internamente.",
         "Comenzar como herramienta de los municipios, no del DNP. El DNP solo se propone como aliado en Fase 4, con evidencia de pilotos exitosos."),
        ("Cambios normativos SGR", "Bajo", "Permanente", "El SGR cambia frecuentemente por CONPES, circulares y decretos. Los agentes y criterios pueden quedar desactualizados.",
         "Usar el scraper existente para monitorear cambios en normativa SGR. Alertas automáticas al detectar nuevas normas relevantes. Base de conocimiento versionada."),
    ]

    e.append(header_table(
        [["Riesgo", "Impacto", "Prob.", "Descripción", "Mitigación"]],
        [[r[0], r[1], r[2], r[3], r[4]] for r in riesgos],
        col_widths=[3.5*cm, 1.5*cm, 1.5*cm, 6*cm, W - 12.5*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(alert_box(
        "<b>Riesgo prioritario:</b> La verificación de duplicidad es el módulo más crítico "
        "y debe ser el primero en completarse y el más rigurosamente probado. Un falso negativo "
        "(no detectar duplicidad real) puede comprometer la credibilidad del sistema ante el OCAD "
        "y el municipio."
    ))

    e.append(PageBreak())
    return e


# ── Sección 14: Conclusión ───────────────────────────────────────────────────
def build_s14():
    e = []
    e.append(section_box("14. CONCLUSIÓN", AZUL_CLARO, AZUL_PRINCIPAL))
    e.append(Spacer(1, 0.4*cm))

    e.append(Paragraph(
        "El pivote de 'Gestor de Responsabilidades' hacia 'Caja de Herramientas SGR para "
        "Municipios Cat. 5 y 6' es una extensión arquitectónicamente natural del sistema existente, "
        "no una reescritura. El análisis demuestra que:",
        S["body"]
    ))

    conclusiones = [
        "El sistema ya hace el 60% del trabajo del formulador: análisis del plan de desarrollo, detección de brechas, extracción de referencias normativas.",
        "Las brechas detectadas son exactamente las oportunidades de proyectos SGR — el vínculo conceptual es directo y ya está implementado.",
        "Los 5 problemas específicos de municipios cat. 5/6 tienen solución técnica clara y factible dentro de la arquitectura actual.",
        "El 70% del código existente se reutiliza sin modificaciones. Solo se agregan 4 nuevos agentes y un nuevo slice SGR.",
        "El riesgo técnico es bajo porque el núcleo (RAG + orquestador + OCR + auth) está probado y funcionando.",
        "La propuesta de valor para el DNP es concreta: multiplica la capacidad de asistencia técnica sin incrementar el costo operativo.",
        "El sistema puede posicionarse como infraestructura pública de soporte a la gestión territorial, con potencial de escalamiento a otros fondos y categorías municipales.",
    ]

    for c in conclusiones:
        e.append(Paragraph(f"✓  {c}", S["bullet"]))
        e.append(Spacer(1, 0.1*cm))

    e.append(Spacer(1, 0.4*cm))
    e.append(Paragraph("Resumen Ejecutivo del Pivote", S["h2"]))

    e.append(header_table(
        [["Dimensión", "Antes (actual)", "Después (SGR)"]],
        [
            ["Enfoque", "Análisis de responsabilidades general", "Formulación SGR para cat. 5 y 6"],
            ["Usuario principal", "Analista territorial general", "Secretario de Planeación municipal"],
            ["Input principal", "Plan de Desarrollo (análisis)", "Plan de Desarrollo (formulación)"],
            ["Output principal", "Matriz de competencias + brechas", "Ficha MGA + pre-validación SGR"],
            ["Impacto medible", "Calidad del análisis normativo", "Proyectos SGR aprobados por OCAD"],
            ["Aliado estratégico", "N/A", "DNP — asistencia técnica oficial"],
            ["Tiempo de valor", "Inmediato (análisis)", "8–12 semanas (piloto completo)"],
            ["Código nuevo", "N/A", "~30% del total (4 agentes + slice)"],
            ["Código reutilizado", "100%", "70% sin cambios, 30% con ajustes menores"],
        ],
        col_widths=[4*cm, 5.5*cm, W - 9.5*cm]
    ))

    e.append(Spacer(1, 0.5*cm))
    e.append(hr(AZUL_PRINCIPAL, 2))
    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph(
        f"Documento generado por el sistema de análisis inteligente · Darwin Fierro Ramírez · "
        f"{datetime.date.today().strftime('%d de %B de %Y')}",
        S["footer"]
    ))

    return e


# ── Sección 15: Modo 2 — Evaluación Inversa ──────────────────────────────────
def build_s15():
    e = []
    e.append(section_box("15. MODO 2: EVALUACIÓN INVERSA DE PROYECTOS EXISTENTES", AZUL_CLARO, AZUL_PRINCIPAL))
    e.append(Spacer(1, 0.3*cm))

    e.append(Paragraph(
        "Además del flujo de <b>descubrimiento</b> (Plan → brechas → proyectos SGR sugeridos), "
        "el sistema opera en un segundo modo: el municipio ya tiene un proyecto en mente o en borrador "
        "y quiere saber cómo está parado antes de comprometer esfuerzo técnico o acudir al DNP. "
        "Este modo invierte el flujo: el proyecto entra como input y el sistema lo evalúa contra "
        "el plan de desarrollo y los criterios SGR.",
        S["body"]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("15.1 Comparativa de los Dos Modos", S["h2"]))

    e.append(header_table(
        [["Dimensión", "Modo 1: Descubrimiento", "Modo 2: Evaluación Inversa"]],
        [
            ["Punto de partida", "Plan de Desarrollo (PDF)", "Proyecto existente o borrador (texto / PDF)"],
            ["Pregunta central", "¿Qué proyectos SGR puedo formular desde mi plan?", "¿Este proyecto que tengo califica para SGR?"],
            ["Dirección del análisis", "Plan → Brechas → Proyectos", "Proyecto → Cruce con Plan → Diagnóstico"],
            ["Output principal", "TOP N proyectos SGR viables con ficha MGA", "Reporte de diagnóstico con semáforo y recomendaciones"],
            ["Usuario típico", "Municipio sin proyecto definido, busca oportunidades", "Municipio con proyecto en borrador o idea concreta"],
            ["Valor principal", "Identificar la oportunidad más rentable en regalías", "Evitar rechazo en el OCAD antes de invertir tiempo"],
        ],
        col_widths=[3.5*cm, 6*cm, W - 9.5*cm]
    ))

    e.append(Spacer(1, 0.35*cm))
    e.append(Paragraph("15.2 El Análisis Bidireccional Estratégico", S["h2"]))
    e.append(Paragraph(
        "La diferencia clave del Modo 2 es que el sistema no solo verifica cumplimiento de requisitos "
        "— da <b>consejería estratégica</b> en cuatro dimensiones simultáneas:",
        S["body"]
    ))
    e.append(Spacer(1, 0.2*cm))

    dimensiones = [
        ("A", "¿Llena un hueco real del plan?",
         "El sistema cruza el proyecto contra las brechas detectadas en el plan. Si el proyecto "
         "atiende una brecha de severidad alta, tiene justificación sólida ante el OCAD. Si el plan "
         "ya tiene esa necesidad cubierta parcialmente, la justificación es más débil y el sistema "
         "advierte sobre ello.",
         AZUL_CLARO, AZUL_MEDIO),
        ("B", "¿Cuántas regalías puede atraer este proyecto?",
         "No todos los proyectos elegibles tienen el mismo potencial de financiación. El sistema evalúa "
         "el sector de inversión, el histórico de aprobación del OCAD departamental en ese sector, y "
         "si el municipio tiene NBI o condiciones que activan priorización automática en ciertos fondos SGR.",
         VERDE_CLARO, VERDE_SGR),
        ("C", "¿El proyecto es estratégicamente óptimo?",
         "El sistema puede detectar que el municipio está formulando un proyecto pequeño cuando existe "
         "una brecha mayor sin atender. O que el alcance actual podría ampliarse para incluir una "
         "brecha de mayor impacto. O que existe una alternativa de proyecto diferente que llena el "
         "mismo hueco pero con mayor probabilidad de aprobación OCAD.",
         NARANJA_CLARO, NARANJA_ALERTA),
        ("D", "¿Cumple los criterios MGA?",
         "Análisis estructural del proyecto contra las secciones obligatorias de la MGA Web: "
         "¿está bien definido el problema central?, ¿tiene indicadores de producto y resultado?, "
         "¿la población objetivo está justificada?, ¿el presupuesto tiene costos unitarios dentro "
         "del rango regional?. Se señalan campos débiles o faltantes antes de que el DNP los rechace.",
         GRIS_CLARO, GRIS_OSCURO),
    ]

    for letra, titulo, desc, bg, border in dimensiones:
        bloque = Table([
            [
                Paragraph(f"<b>{letra}</b>", ParagraphStyle("ltr", fontName="Helvetica-Bold",
                    fontSize=14, textColor=border, alignment=TA_CENTER)),
                Table([
                    [Paragraph(f"<b>{titulo}</b>", S["body_bold"])],
                    [Paragraph(desc, S["body"])],
                ], colWidths=[W - 2.5*cm]),
            ]
        ], colWidths=[1.2*cm, W - 1.2*cm])
        bloque.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), bg),
            ("BOX", (0,0), (-1,-1), 1, border),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("TOPPADDING",    (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
            ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ]))
        e.append(bloque)
        e.append(Spacer(1, 0.2*cm))

    e.append(Spacer(1, 0.2*cm))
    e.append(Paragraph("15.3 Los 4 Cuadrantes de Recomendación Estratégica", S["h2"]))
    e.append(Paragraph(
        "El cruce de dos variables — alineación con el plan y potencial de regalías — "
        "genera cuatro tipos de situación, cada una con una recomendación específica:",
        S["body"]
    ))
    e.append(Spacer(1, 0.2*cm))

    cuadrantes = [
        ("✅ ÓPTIMO",
         "Alta alineación con el plan + Alto potencial de regalías",
         "El proyecto llena una brecha real Y es atractivo para el OCAD. "
         "Proceder con la formulación MGA completa. El sistema genera la ficha automáticamente.",
         VERDE_CLARO, VERDE_SGR),
        ("🟡 BIEN JUSTIFICADO, POCO ATRACTIVO",
         "Alta alineación con el plan + Bajo potencial de regalías",
         "El proyecto atiende una necesidad real del municipio pero es de un sector con "
         "poca financiación histórica SGR o monto muy pequeño. Recomendación: reformular "
         "para ampliar el alcance o incorporar un componente adicional que lo haga más "
         "atractivo para el fondo SGR correspondiente.",
         AZUL_CLARO, AZUL_MEDIO),
        ("🟡 ATRACTIVO PERO CON RIESGO DE RECHAZO",
         "Baja alineación con el plan + Alto potencial de regalías",
         "El proyecto puede conseguir regalías pero tiene riesgo de rechazo por no tener "
         "respaldo claro en el Plan de Desarrollo. Recomendación: identificar qué artículo "
         "o programa del plan se puede invocar para justificarlo, o ajustar el objeto del "
         "proyecto para vincularlo a una brecha existente.",
         NARANJA_CLARO, NARANJA_ALERTA),
        ("🔴 REFORMULAR COMPLETAMENTE",
         "Baja alineación con el plan + Bajo potencial de regalías",
         "El proyecto tiene poca justificación en el plan Y escaso atractivo para el OCAD. "
         "Alta probabilidad de rechazo. El sistema sugiere los TOP 3 proyectos alternativos "
         "que sí tienen alta viabilidad, derivados de las brechas detectadas en el plan.",
         HexColor("#FFEBEE"), HexColor("#C62828")),
    ]

    for titulo_c, condicion, recomendacion, bg, border in cuadrantes:
        t = Table([
            [Paragraph(f"<b>{titulo_c}</b>", ParagraphStyle("qt", fontName="Helvetica-Bold",
                fontSize=10, textColor=border))],
            [Paragraph(f"<i>Condición:</i> {condicion}", S["body"])],
            [Paragraph(f"<i>Recomendación:</i> {recomendacion}", S["body"])],
        ], colWidths=[W])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), bg),
            ("BOX", (0,0), (-1,-1), 1.5, border),
            ("TOPPADDING",    (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING",   (0,0), (-1,-1), 10),
            ("RIGHTPADDING",  (0,0), (-1,-1), 10),
            ("LINEBELOW", (0,0), (-1,0), 0.5, border),
            ("LINEBELOW", (0,1), (-1,1), 0.3, GRIS_LINEA),
        ]))
        e.append(t)
        e.append(Spacer(1, 0.2*cm))

    e.append(PageBreak())

    e.append(section_box("15.4 Nuevo Agente: agente_evaluador_proyecto", VERDE_CLARO, VERDE_SGR))
    e.append(Spacer(1, 0.3*cm))

    e.append(Paragraph(
        "El Modo 2 requiere un nuevo agente especializado que realiza el análisis bidireccional. "
        "A diferencia de los agentes del Modo 1 (que extraen información del plan), este agente "
        "<b>evalúa un input externo (el proyecto) contra el plan ya indexado</b>.",
        S["body"]
    ))
    e.append(Spacer(1, 0.25*cm))

    e.append(header_table(
        [["Propiedad", "Detalle"]],
        [
            ["Nombre", "agente_evaluador_proyecto"],
            ["Archivo", "app/slices/sgr/agents/agente_evaluador.py"],
            ["Prompt template", "data/prompts/sgr/evaluacion_proyecto.md"],
            ["Input principal", "Texto/PDF del proyecto + plan_id del plan de desarrollo ya indexado"],
            ["Input opcional", "Presupuesto estimado, sector declarado, municipio (DIVIPOLA)"],
            ["RAG Dual", "Busca el proyecto contra chunks del plan (detecta brechas que cubre) + base normativa SGR (valida elegibilidad)"],
            ["Output: diagnostico_mga", "Secciones MGA evaluadas: ok | debil | faltante + sugerencia de mejora por sección"],
            ["Output: alineacion_plan", "Brechas que llena (con chunk_ids), brechas ignoradas relevantes, score_alineacion 0-1"],
            ["Output: analisis_estrategico", "tipo (llena_hueco_real | cubre_algo_existente | fuera_del_plan | hibrido), potencial_regalias, recomendacion_principal, alternativas[]"],
            ["Output: calificacion_sgr", "elegible (bool), score_aprobacion (0-1), observaciones por criterio"],
            ["Output: semaforo", "verde | amarillo | rojo — síntesis ejecutiva para mostrar en el dashboard"],
        ],
        col_widths=[4*cm, W - 4*cm]
    ))

    e.append(Spacer(1, 0.35*cm))
    e.append(Paragraph("15.5 Estructura del Output: EvaluacionProyecto", S["h2"]))

    e.append(header_table(
        [["Campo (modelo MySQL)", "Tipo", "Descripción"]],
        [
            ["id", "UUID PK", "Identificador de la evaluación"],
            ["plan_id", "UUID FK → Plane", "Plan de desarrollo contra el que se evaluó"],
            ["proyecto_texto", "TEXT", "Descripción o texto del proyecto evaluado"],
            ["proyecto_nombre", "VARCHAR(300)", "Nombre extraído o declarado del proyecto"],
            ["sector_declarado", "VARCHAR(100)", "Sector que declaró el formulador"],
            ["tipo_resultado", "ENUM", "llena_hueco_real | cubre_algo_existente | fuera_del_plan | hibrido"],
            ["potencial_regalias", "ENUM", "alto | medio | bajo"],
            ["score_alineacion", "FLOAT", "0.0–1.0 alineación con el plan"],
            ["score_aprobacion_sgr", "FLOAT", "0.0–1.0 probabilidad de aprobación OCAD"],
            ["semaforo", "ENUM", "verde | amarillo | rojo"],
            ["diagnostico_mga", "JSON", "Por sección MGA: {estado, sugerencia}"],
            ["brechas_que_llena", "JSON", "Lista de brechas del plan que el proyecto atiende"],
            ["brechas_ignoradas", "JSON", "Brechas relevantes que el proyecto ignora"],
            ["recomendacion_principal", "TEXT", "Consejo estratégico principal del sistema"],
            ["alternativas_sugeridas", "JSON", "TOP 3 proyectos alternativos más viables"],
            ["elegible_sgr", "BOOLEAN", "Cumple criterios básicos de elegibilidad SGR"],
            ["observaciones_sgr", "JSON", "Observaciones por criterio SGR (cumple/no/parcial)"],
            ["creado_en", "TIMESTAMP", "Fecha de la evaluación"],
        ],
        col_widths=[4.5*cm, 3*cm, W - 7.5*cm]
    ))

    e.append(Spacer(1, 0.35*cm))
    e.append(Paragraph("15.6 Flujo del Modo 2", S["h2"]))

    pasos2 = [
        ("1", "Municipio ingresa el proyecto", "Pega el texto del proyecto o sube un PDF borrador. Declara el sector y puede incluir presupuesto estimado."),
        ("2", "Selecciona su plan", "Elige el plan de desarrollo municipal ya indexado en el sistema (del Modo 1 o cargado independientemente)."),
        ("3", "RAG bidireccional", "El sistema busca el texto del proyecto contra los chunks del plan para detectar qué brechas existentes atiende, y lo cruza con la base normativa SGR para verificar elegibilidad."),
        ("4", "Agente evaluador", "agente_evaluador_proyecto recibe el proyecto + contexto RAG y produce el diagnóstico en las 4 dimensiones (MGA, alineación, estratégico, SGR)."),
        ("5", "Clasificación en cuadrante", "El sistema determina en cuál de los 4 cuadrantes cae el proyecto y selecciona la recomendación estratégica correspondiente."),
        ("6", "Dashboard de diagnóstico", "Semáforo visual, score de alineación, score SGR, lista de brechas que atiende vs. brechas ignoradas relevantes, y recomendaciones accionables."),
        ("7", "Alternativas sugeridas", "Si el semáforo es amarillo o rojo, el sistema presenta los TOP 3 proyectos alternativos más viables derivados de las brechas del plan."),
    ]

    e.append(header_table(
        [["#", "Paso", "Descripción"]],
        pasos2,
        col_widths=[0.7*cm, 5*cm, W - 5.7*cm]
    ))

    e.append(Spacer(1, 0.35*cm))
    e.append(Paragraph("15.7 Ejemplos de Salidas del Sistema", S["h2"]))

    ejemplos = [
        {
            "titulo": "Caso 1: Proyecto de acueducto veredal",
            "situacion": "El municipio quiere construir un acueducto veredal para 200 familias.",
            "brechas_cubre": "Sí — el plan tiene brecha de 'Déficit de agua potable en zona rural' de severidad alta.",
            "potencial_regalias": "Alto — el sector de agua potable y saneamiento básico tiene alta aprobación histórica en el OCAD Paz.",
            "semaforo": "VERDE",
            "recomendacion": "Proyecto óptimo. Proceder con formulación MGA. El sistema genera la ficha completa. "
                             "Verificar duplicidad en SUIFP antes de radicar.",
        },
        {
            "titulo": "Caso 2: Proyecto de dotación de tablets para estudiantes",
            "situacion": "El municipio quiere comprar tablets para una escuela rural.",
            "brechas_cubre": "Parcialmente — hay brecha de 'calidad educativa' pero la dotación de tecnología no es la inversión prioritaria señalada.",
            "potencial_regalias": "Bajo — proyectos de dotación tecnológica tienen historial bajo de aprobación en OCAD regional para municipios cat. 6.",
            "semaforo": "AMARILLO",
            "recomendacion": "El proyecto tiene justificación débil. Sugerencia: ampliar el alcance para incluir mejoramiento "
                             "de infraestructura física educativa (la brecha de mayor severidad en el plan), lo que elevaría "
                             "el potencial de aprobación y el monto elegible.",
        },
        {
            "titulo": "Caso 3: Proyecto de parque recreativo urbano",
            "situacion": "El municipio quiere construir un parque recreativo en el casco urbano.",
            "brechas_cubre": "No — el plan no tiene brechas de espacio público priorizadas. La inversión principal del plan es en vías terciarias y saneamiento.",
            "potencial_regalias": "Bajo — proyectos de recreación y deporte tienen baja tasa de aprobación para municipios cat. 6 sin NBI crítico.",
            "semaforo": "ROJO",
            "recomendacion": "Proyecto con alta probabilidad de rechazo. No está en el plan de desarrollo y es de bajo potencial "
                             "de regalías. El sistema sugiere: (1) Mejoramiento vía terciaria rural [score 0.91], "
                             "(2) Sistema de alcantarillado sector sur [score 0.87], (3) Salón comunal vereda La Esperanza [score 0.79].",
        },
    ]

    for ej in ejemplos:
        titulo_col = HexColor("#1565C0") if "VERDE" in ej["semaforo"] else (
            NARANJA_ALERTA if "ROJO" in ej["semaforo"] else HexColor("#F57F17")
        )
        bg_col = VERDE_CLARO if "VERDE" in ej["semaforo"] else (
            HexColor("#FFEBEE") if "ROJO" in ej["semaforo"] else NARANJA_CLARO
        )

        rows_ej = [
            [Paragraph("<b>Situación</b>", S["body_bold"]),
             Paragraph(ej["situacion"], S["body"])],
            [Paragraph("<b>Brechas que cubre</b>", S["body_bold"]),
             Paragraph(ej["brechas_cubre"], S["body"])],
            [Paragraph("<b>Potencial regalías</b>", S["body_bold"]),
             Paragraph(ej["potencial_regalias"], S["body"])],
            [Paragraph("<b>Semáforo</b>", S["body_bold"]),
             Paragraph(f'<b><font color="#{titulo_col.hexval()[2:]}">{ej["semaforo"]}</font></b>', S["body"])],
            [Paragraph("<b>Recomendación</b>", S["body_bold"]),
             Paragraph(ej["recomendacion"], S["body"])],
        ]

        header_ej = Table(
            [[Paragraph(f"<b>{ej['titulo']}</b>", ParagraphStyle("ht", fontName="Helvetica-Bold",
                fontSize=10, textColor=white))]],
            colWidths=[W]
        )
        header_ej.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), titulo_col),
            ("TOPPADDING",    (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ]))

        body_ej = Table(rows_ej, colWidths=[3.5*cm, W - 3.5*cm])
        body_ej.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), bg_col),
            ("BACKGROUND", (0,0), (0,-1), HexColor("#E0E0E0")),
            ("FONTNAME",   (0,0), (0,-1), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,-1), 9),
            ("VALIGN",     (0,0), (-1,-1), "TOP"),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
            ("RIGHTPADDING",  (0,0), (-1,-1), 8),
            ("LINEBELOW",  (0,0), (-1,-2), 0.3, GRIS_LINEA),
            ("BOX",        (0,0), (-1,-1), 1, titulo_col),
        ]))

        e.append(KeepTogether([header_ej, body_ej]))
        e.append(Spacer(1, 0.3*cm))

    e.append(Spacer(1, 0.2*cm))
    e.append(Paragraph("15.8 Integración con el Modo 1", S["h2"]))
    e.append(Paragraph(
        "Los dos modos son complementarios y comparten la misma infraestructura. "
        "Un municipio puede usar ambos en la misma sesión:",
        S["body"]
    ))
    e.append(Spacer(1, 0.15*cm))

    integracion = [
        "El Modo 1 entrega el TOP 3 de proyectos sugeridos desde las brechas del plan.",
        "El municipio toma uno de esos proyectos y lo trabaja con sus propias ideas adicionales.",
        "El Modo 2 evalúa la versión modificada del municipio antes de llevarlo al DNP.",
        "El sistema detecta si las modificaciones del municipio mejoraron o empeoraron la viabilidad.",
        "El resultado final es un proyecto co-formulado entre la IA y el técnico municipal.",
    ]
    for i in integracion:
        e.append(Paragraph(f"• {i}", S["bullet"]))

    e.append(Spacer(1, 0.3*cm))
    e.append(info_box(
        "<b>Valor diferenciador:</b> Ninguna herramienta del mercado colombiano combina "
        "análisis del Plan de Desarrollo + verificación SGR + consejería estratégica en "
        "un solo flujo. El Modo 2 convierte el sistema en un <b>asesor técnico disponible "
        "24/7</b> para municipios que no tienen ese perfil en su planta de personal, "
        "siendo esto exactamente el tipo de herramienta que el DNP necesita para "
        "escalar su asistencia técnica gratuita."
    ))

    e.append(PageBreak())
    return e


# ── Sección 15: Modelo de acceso Cat. 5/6 ────────────────────────────────────
def build_s15_acceso():
    e = []
    e.append(section_box("15. MODELO DE ACCESO: VERIFICACIÓN CATEGORÍA 5 Y 6", AZUL_CLARO, AZUL_PRINCIPAL))
    e.append(Spacer(1, 0.3*cm))

    e.append(Paragraph(
        "El sistema está diseñado exclusivamente para municipios de categoría 5 y 6 de Colombia. "
        "Esto no es solo una restricción de negocio — es una decisión de diseño que garantiza "
        "que los criterios de elegibilidad SGR, los benchmarks de costos y las recomendaciones "
        "estratégicas sean precisas para este perfil específico de entidad territorial. "
        "Abrir el sistema a otras categorías sin adaptar los módulos comprometería la calidad "
        "de las recomendaciones.",
        S["body"]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("15.1 Dos Canales de Onboarding", S["h2"]))

    canales = [
        {
            "titulo": "Canal A — Adopción por el DNP",
            "desc": (
                "El DNP ofrece el sistema como parte de su programa de asistencia técnica "
                "gratuita a municipios pequeños. En este canal, el DNP valida previamente "
                "la categoría del municipio y crea la cuenta en el sistema. El municipio "
                "recibe sus credenciales iniciales por correo institucional o en una sesión "
                "de asistencia técnica. Es el canal de mayor confianza institucional y "
                "garantiza que todos los usuarios del sistema son efectivamente Cat. 5/6."
            ),
            "ventaja": "Validación previa por el DNP · Mayor adopción institucional · Credibilidad ante el OCAD",
            "bg": AZUL_CLARO, "border": AZUL_MEDIO,
        },
        {
            "titulo": "Canal B — Registro directo del municipio",
            "desc": (
                "El municipio se registra directamente en el sistema proporcionando su "
                "código DIVIPOLA. El sistema consulta automáticamente la base de datos "
                "del DNP (Terridata / clasificación anual de municipios) para verificar "
                "que el código DIVIPOLA corresponde a un municipio de categoría 5 o 6 "
                "en el año fiscal vigente. Si la categoría no corresponde, el registro "
                "es rechazado con un mensaje explicativo. La cuenta queda pendiente de "
                "activación hasta que un administrador (DNP u operador del sistema) confirme."
            ),
            "ventaja": "Autoservicio · Mayor cobertura · Verificación automática via API Terridata DNP",
            "bg": VERDE_CLARO, "border": VERDE_SGR,
        },
    ]

    for c in canales:
        t = Table([
            [Paragraph(f"<b>{c['titulo']}</b>", ParagraphStyle("ct", fontName="Helvetica-Bold",
                fontSize=10, textColor=white))],
            [Paragraph(c["desc"], S["body"])],
            [Paragraph(f"<b>Ventajas:</b> {c['ventaja']}", S["body"])],
        ], colWidths=[W])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (0,0), c["border"]),
            ("BACKGROUND", (0,1), (0,-1), c["bg"]),
            ("BOX", (0,0), (-1,-1), 1.5, c["border"]),
            ("TOPPADDING",    (0,0), (-1,-1), 7),
            ("BOTTOMPADDING", (0,0), (-1,-1), 7),
            ("LEFTPADDING",   (0,0), (-1,-1), 10),
            ("RIGHTPADDING",  (0,0), (-1,-1), 10),
            ("LINEBELOW", (0,0), (0,0), 0, c["border"]),
        ]))
        e.append(t)
        e.append(Spacer(1, 0.25*cm))

    e.append(Spacer(1, 0.1*cm))
    e.append(Paragraph("15.2 Datos Verificados en el Registro", S["h2"]))

    e.append(header_table(
        [["Dato", "Fuente de verificación", "Obligatorio", "Uso en el sistema"]],
        [
            ["Código DIVIPOLA (8 dígitos)", "DANE / DNP", "Sí", "Identifica el municipio de forma única y determina departamento y región geográfica"],
            ["Categoría municipal (5 o 6)", "Decreto anual DNP clasificación", "Sí", "Valida el acceso y calibra los criterios de elegibilidad SGR"],
            ["NBI del municipio (%)", "DANE Terridata", "Automático", "Activa priorización automática en fondos SGR si NBI > 35%"],
            ["ICLD vigente (SMMLV)", "Resolución Minhacienda", "Automático", "Confirma categoría y define topes de inversión aplicables"],
            ["Nombre del alcalde / secretario", "Declarado por el usuario", "Sí", "Auditoría y responsabilidad institucional del uso del sistema"],
            ["Correo institucional (@municipio.gov.co)", "Verificación de dominio", "Sí", "Previene registro de actores no institucionales"],
            ["Vigencia del Plan de Desarrollo", "Declarado + validado", "Sí", "Define el marco temporal de análisis (ej: 2024–2027)"],
        ],
        col_widths=[4*cm, 3.5*cm, 2*cm, W - 9.5*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(alert_box(
        "<b>Regla de negocio crítica:</b> Si el municipio cambia de categoría en un año fiscal "
        "(por variación de ICLD o población), el sistema notifica al usuario pero mantiene el "
        "acceso durante el año vigente. Al inicio del siguiente año fiscal se re-verifica "
        "la categoría automáticamente. Un municipio que asciende a Cat. 4 pierde el acceso "
        "al inicio del siguiente período — sus datos y planes quedan preservados para consulta."
    ))

    e.append(PageBreak())
    return e


# ── Sección 16: Onboarding obligatorio ───────────────────────────────────────
def build_s16_onboarding():
    e = []
    e.append(section_box("16. ONBOARDING OBLIGATORIO: CONTRASEÑA + PLAN DE DESARROLLO", VERDE_CLARO, VERDE_SGR))
    e.append(Spacer(1, 0.3*cm))

    e.append(Paragraph(
        "Las dos primeras acciones después del primer login son <b>bloqueantes</b>: "
        "el sistema no permite acceder a ninguna funcionalidad hasta que ambas se completen. "
        "Esta decisión de diseño garantiza la integridad de la experiencia y la seguridad "
        "de la cuenta institucional.",
        S["body"]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("16.1 Paso 1 — Cambio Obligatorio de Contraseña", S["h2"]))

    e.append(Paragraph(
        "Al ingresar por primera vez con las credenciales provisionales entregadas por el DNP "
        "o generadas en el registro, el sistema redirige inmediatamente a la pantalla de cambio "
        "de contraseña. No hay opción de omitir este paso.",
        S["body"]
    ))
    e.append(Spacer(1, 0.15*cm))

    requisitos_pass = [
        "Mínimo 10 caracteres",
        "Al menos una mayúscula, una minúscula y un número",
        "No puede ser igual a la contraseña provisional",
        "No puede contener el nombre del municipio o el código DIVIPOLA",
        "Se registra timestamp y IP del primer cambio (auditoría)",
    ]
    for r in requisitos_pass:
        e.append(Paragraph(f"• {r}", S["bullet"]))

    e.append(Spacer(1, 0.25*cm))
    e.append(Paragraph("16.2 Paso 2 — Carga Obligatoria del Plan de Desarrollo", S["h2"]))

    e.append(Paragraph(
        "Después del cambio de contraseña, el sistema muestra una pantalla de bienvenida "
        "con un único botón: <b>'Cargar Plan de Desarrollo Municipal'</b>. "
        "Todo el resto de la interfaz permanece bloqueado con un mensaje explicativo: "
        "<i>'Para comenzar, debes cargar el Plan de Desarrollo de tu municipio. "
        "Es el documento base que permite al sistema identificar oportunidades de regalías.'</i>",
        S["body"]
    ))
    e.append(Spacer(1, 0.2*cm))

    e.append(info_box(
        "<b>¿Por qué es bloqueante?</b> El Plan de Desarrollo es el insumo fundamental de todo "
        "el sistema. Sin él, no hay brechas que detectar, no hay proyectos que sugerir y no hay "
        "base normativa sobre qué evaluar un proyecto. Forzar su carga en el onboarding garantiza "
        "que el municipio no use el sistema parcialmente y evita que llegue a conclusiones "
        "incorrectas por falta de contexto."
    ))

    e.append(Spacer(1, 0.2*cm))
    e.append(Paragraph("Validaciones durante la carga del plan:", S["h3"]))

    e.append(header_table(
        [["Validación", "Qué verifica", "Si falla"]],
        [
            ["Formato de archivo", "PDF, máximo 50 MB", "Rechaza con mensaje de formato"],
            ["Extractabilidad", "OCR o texto nativo extraíble", "Advertencia + reintento con OCR forzado"],
            ["Vigencia declarada", "Período 2024–2027 o el vigente", "Alerta si el plan parece vencido"],
            ["Coincidencia con municipio", "El documento menciona el nombre del municipio", "Advertencia — puede ser un plan equivocado"],
            ["Longitud mínima", "Al menos 5.000 palabras extraídas", "Alerta de plan muy corto / incompleto"],
        ],
        col_widths=[3.5*cm, 5*cm, W - 8.5*cm]
    ))

    e.append(Spacer(1, 0.25*cm))
    e.append(Paragraph("16.3 Análisis Automático Post-Carga", S["h2"]))

    e.append(Paragraph(
        "Una vez cargado el plan, el sistema inicia automáticamente el pipeline de análisis "
        "(los 5 agentes actuales: responsabilidades, leyes, actores, brechas, matriz). "
        "El usuario ve una pantalla de progreso en tiempo real (SSE). Al finalizar, se "
        "desbloquea la interfaz completa y el sistema muestra directamente el "
        "<b>Dashboard de Oportunidades SGR</b> con las primeras recomendaciones de proyectos.",
        S["body"]
    ))

    e.append(Spacer(1, 0.2*cm))

    estados_onboarding = [
        ("credenciales_provisionales", "Usuario recibe credenciales del DNP o se registra", "Acceso bloqueado"),
        ("contrasena_cambiada", "Primer login + cambio de contraseña completado", "Solo pantalla de carga del plan"),
        ("plan_cargando", "Plan subido — análisis en progreso (SSE)", "Pantalla de progreso bloqueante"),
        ("plan_analizado", "Análisis completado — brechas detectadas", "Acceso completo al sistema"),
    ]

    e.append(header_table(
        [["Estado", "Evento", "Acceso"]],
        estados_onboarding,
        col_widths=[4*cm, 7*cm, W - 11*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("16.4 Gestión del Plan de Desarrollo como Documento Vivo", S["h2"]))

    e.append(Paragraph(
        "El Plan de Desarrollo no es estático. Los municipios pueden actualizarlo (ej: "
        "modificaciones al plan aprobadas por el Concejo). El sistema permite:",
        S["body"]
    ))
    e.append(Spacer(1, 0.1*cm))

    plan_vivo = [
        "<b>Reemplazar el plan</b>: cargar una nueva versión. El sistema crea una versión nueva y re-analiza. Las evaluaciones de proyectos anteriores se mantienen vinculadas a la versión del plan con la que fueron evaluadas.",
        "<b>Versioning</b>: el sistema guarda la fecha de cada versión del plan y permite comparar qué brechas nuevas aparecieron o cuáles se cerraron.",
        "<b>Alerta de plan vencido</b>: si el período del plan venció (ej: plan 2020-2023 en 2025), el sistema alerta que las recomendaciones pueden no ser válidas para el nuevo período de gobierno.",
        "<b>Actualización por inclusión de proyecto</b>: si el sistema recomienda incluir un proyecto nuevo en el plan (Modo 2), el municipio puede registrar en el sistema que ese artículo del plan fue modificado por el Concejo, lo que actualiza el análisis de brechas.",
    ]
    for item in plan_vivo:
        e.append(Paragraph(f"• {item}", S["bullet"]))
        e.append(Spacer(1, 0.1*cm))

    e.append(PageBreak())
    return e


# ── Sección 17: Flujo completo del producto ──────────────────────────────────
def build_s17_flujo():
    e = []
    e.append(section_box("17. FLUJO COMPLETO DEL PRODUCTO (MODOS 1 Y 2 CORREGIDOS)"))
    e.append(Spacer(1, 0.3*cm))

    e.append(Paragraph(
        "El siguiente esquema representa el flujo completo desde el acceso inicial "
        "hasta los dos modos de uso, incluyendo el punto de convergencia donde ambos "
        "modos comparten el paso de vinculación con el Plan de Desarrollo:",
        S["body"]
    ))

    e.append(Spacer(1, 0.35*cm))

    # Diagrama de flujo como tabla visual
    def nodo(texto, bg, border, w=None):
        t = Table([[Paragraph(texto, ParagraphStyle("nd", fontName="Helvetica-Bold",
            fontSize=8.5, textColor=white if bg != GRIS_CLARO else GRIS_OSCURO,
            alignment=TA_CENTER, leading=12))]],
            colWidths=[w or 4.5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), bg),
            ("BOX",           (0,0), (-1,-1), 1.5, border),
            ("TOPPADDING",    (0,0), (-1,-1), 7),
            ("BOTTOMPADDING", (0,0), (-1,-1), 7),
            ("LEFTPADDING",   (0,0), (-1,-1), 5),
            ("RIGHTPADDING",  (0,0), (-1,-1), 5),
        ]))
        return t

    def flecha_v(texto="↓"):
        return Paragraph(f"<b>{texto}</b>", ParagraphStyle("fv",
            fontName="Helvetica-Bold", fontSize=14, textColor=AZUL_MEDIO,
            alignment=TA_CENTER, spaceBefore=3, spaceAfter=3))

    etapas = [
        ("ACCESO", "Municipio Cat. 5/6 verificado\n(Canal DNP o Registro directo\ncon verificación DIVIPOLA)", AZUL_PRINCIPAL, AZUL_PRINCIPAL),
        ("PASO 1", "Cambio obligatorio de contraseña\n(Bloqueante — primer login)", AZUL_MEDIO, AZUL_MEDIO),
        ("PASO 2", "Carga obligatoria del Plan\nde Desarrollo (PDF)\n(Bloqueante — sin esto no hay acceso)", VERDE_SGR, VERDE_SGR),
        ("ANÁLISIS", "Sistema analiza el plan\nautomáticamente (5 agentes)\nDetecta brechas y oportunidades", AZUL_MEDIO, AZUL_MEDIO),
        ("DASHBOARD", "Dashboard de Oportunidades SGR\nTOP proyectos recomendados por\nbrechas detectadas en el plan", VERDE_SGR, VERDE_SGR),
    ]

    for label, desc, bg, border in etapas:
        row = Table([
            [Paragraph(f"<b>{label}</b>", ParagraphStyle("lb", fontName="Helvetica-Bold",
                fontSize=9, textColor=white, alignment=TA_CENTER)),
             Paragraph(desc, ParagraphStyle("dc", fontName="Helvetica", fontSize=9,
                textColor=GRIS_OSCURO, leading=13))],
        ], colWidths=[2.5*cm, W - 2.5*cm])
        row.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (0,0), bg),
            ("BACKGROUND", (1,0), (1,0), GRIS_CLARO),
            ("BOX",   (0,0), (-1,-1), 1, border),
            ("TOPPADDING",    (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
            ("RIGHTPADDING",  (0,0), (-1,-1), 8),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ]))
        e.append(row)
        e.append(flecha_v())

    # Bifurcación
    bifurcacion = Table([[
        nodo("MODO 1\nDescubrimiento\n\nEl sistema sugiere\nproyectos desde\nlas brechas del plan", AZUL_MEDIO, AZUL_PRINCIPAL, 7*cm),
        Paragraph("<b>o</b>", ParagraphStyle("o", fontName="Helvetica-Bold",
            fontSize=16, textColor=GRIS_MEDIO, alignment=TA_CENTER)),
        nodo("MODO 2\nEvaluación Inversa\n\nEl municipio ingresa\nun proyecto propio\npara verificarlo", VERDE_SGR, VERDE_SGR, 7*cm),
    ]], colWidths=[7*cm, W - 14*cm, 7*cm])
    bifurcacion.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0), (-1,-1), 0),
    ]))
    e.append(bifurcacion)

    e.append(Spacer(1, 0.2*cm))
    e.append(flecha_v("↓                                                              ↓"))
    e.append(Spacer(1, 0.1*cm))

    resultado = Table([[
        nodo("Ficha MGA\npre-generada\n\nLista para ingresar\na MGA Web DNP", AZUL_MEDIO, AZUL_PRINCIPAL, 7*cm),
        Paragraph("", S["body"]),
        nodo("Diagnóstico del\nproyecto (4 dims)\n\n¿Está bien para\nSGR? ¿Califica?", VERDE_SGR, VERDE_SGR, 7*cm),
    ]], colWidths=[7*cm, W - 14*cm, 7*cm])
    resultado.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0), (-1,-1), 0),
    ]))
    e.append(resultado)

    e.append(Spacer(1, 0.15*cm))
    e.append(flecha_v("↓                                                              ↓"))
    e.append(Spacer(1, 0.1*cm))

    convergencia = Table([[
        nodo("Verificación duplicidad\n+ costos regionales\n+ elegibilidad Cat. 5/6", AZUL_MEDIO, AZUL_PRINCIPAL, 7*cm),
        Paragraph("", S["body"]),
        nodo("SI está todo bien:\n¿Incluir el proyecto\nen el Plan de\nDesarrollo?", NARANJA_ALERTA, NARANJA_ALERTA, 7*cm),
    ]], colWidths=[7*cm, W - 14*cm, 7*cm])
    convergencia.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0), (-1,-1), 0),
    ]))
    e.append(convergencia)

    e.append(Spacer(1, 0.15*cm))
    e.append(flecha_v("↓                                                              ↓"))
    e.append(Spacer(1, 0.1*cm))

    punto_convergencia = Table([[
        nodo("PROYECTO LISTO PARA DNP\n\nPre-validado, con ficha MGA,\ncosteado y sin duplicidad.\nListo para asistencia técnica.", VERDE_SGR, VERDE_SGR, W),
    ]], colWidths=[W])
    punto_convergencia.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0), (-1,-1), 0),
    ]))
    e.append(punto_convergencia)

    e.append(Spacer(1, 0.4*cm))
    e.append(Paragraph("17.1 Principio de Diseño: El Plan de Desarrollo es el Ancla", S["h2"]))
    e.append(Paragraph(
        "Ambos modos convergen en el mismo punto: el Plan de Desarrollo del municipio. "
        "En el Modo 1 es el punto de partida (de ahí nacen los proyectos sugeridos). "
        "En el Modo 2 es el punto de llegada (el proyecto evaluado debe ser incluido en el plan "
        "si aún no está, porque es requisito SGR obligatorio). "
        "Esto convierte al sistema en un <b>gestor activo del plan de desarrollo</b>, "
        "no solo un analizador pasivo.",
        S["body"]
    ))

    e.append(PageBreak())
    return e


# ── Sección 18: Modo 2 corregido ─────────────────────────────────────────────
def build_s18_modo2():
    e = []
    e.append(section_box("18. MODO 2 CORREGIDO: EVALUACIÓN + ¿INCLUIR EN EL PLAN?", NARANJA_CLARO, NARANJA_ALERTA))
    e.append(Spacer(1, 0.3*cm))

    e.append(Paragraph(
        "La corrección fundamental al Modo 2 es que el flujo no termina con el diagnóstico del "
        "proyecto. Después de que el sistema verifica que el proyecto califica para SGR "
        "(estructura MGA, elegibilidad, costos, duplicidad), realiza una verificación adicional "
        "crítica: <b>¿este proyecto ya está incluido en el Plan de Desarrollo?</b> "
        "Si no lo está, el sistema guía al municipio en el proceso de incluirlo, "
        "porque sin ese paso el proyecto no puede ser radicado ante el OCAD.",
        S["body"]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(Paragraph("18.1 Flujo Detallado del Modo 2 (Corregido)", S["h2"]))

    pasos_modo2 = [
        ("1", "Ingreso del proyecto",
         "El municipio pega el texto del proyecto o sube un PDF borrador. Puede ser una idea "
         "expresada en texto libre, un borrador de ficha MGA incompleto, o un documento "
         "técnico preliminar. También puede declarar el sector y un presupuesto estimado.",
         AZUL_CLARO, AZUL_MEDIO, False),
        ("2", "Análisis RAG bidireccional",
         "El sistema cruza el proyecto contra: (a) los chunks del Plan de Desarrollo ya "
         "indexado — para detectar qué brechas del plan atiende y si está mencionado; "
         "(b) la base normativa SGR — para verificar elegibilidad por sector y tipo de inversión.",
         AZUL_CLARO, AZUL_MEDIO, False),
        ("3", "Diagnóstico en 4 dimensiones",
         "El agente_evaluador_proyecto produce el análisis completo: estructura MGA "
         "(campos ok/débil/faltante), alineación con el plan (brechas que atiende y brechas "
         "importantes que ignora), análisis estratégico (cuadrante de recomendación) y "
         "calificación SGR (elegibilidad + score de aprobación OCAD).",
         AZUL_CLARO, AZUL_MEDIO, False),
        ("4", "Verificación: ¿Está en el Plan de Desarrollo?",
         "PASO NUEVO: El sistema verifica si el proyecto o un proyecto similar está mencionado "
         "en el Plan de Desarrollo ya indexado. Usa búsqueda semántica en Qdrant con el "
         "texto del proyecto contra los chunks del plan. Hay tres resultados posibles:",
         NARANJA_CLARO, NARANJA_ALERTA, True),
        ("5a — Si SÍ está en el plan",
         "Confirmación automática",
         "El sistema muestra los chunks del plan que respaldan el proyecto (con número de página "
         "y sección). Esto se agrega como evidencia al expediente del proyecto para el OCAD. "
         "El municipio puede continuar directamente a la formulación MGA completa.",
         VERDE_CLARO, VERDE_SGR, False),
        ("5b — Si NO está en el plan",
         "Guía de inclusión en el plan",
         "El sistema activa el sub-flujo de inclusión en el Plan de Desarrollo (ver 18.2). "
         "El proyecto queda en estado 'pendiente de inclusión en plan' y NO puede avanzar "
         "a la formulación MGA completa hasta que el municipio registre que el Concejo "
         "aprobó la modificación al plan.",
         NARANJA_CLARO, NARANJA_ALERTA, False),
        ("5c — Si PARCIALMENTE está en el plan",
         "Orientación de fortalecimiento",
         "El proyecto está vagamente mencionado en el plan pero no de forma explícita como "
         "programa o proyecto. El sistema sugiere el texto exacto que debería incluirse en "
         "la modificación del plan para fortalecer el respaldo normativo del proyecto ante el OCAD.",
         AZUL_CLARO, AZUL_MEDIO, False),
        ("6", "Verificación de duplicidad y costos",
         "Si el proyecto está (o queda) en el plan: verificación automática en MapaInversiones "
         "por municipio + sector y validación del presupuesto contra benchmarks regionales DNP/DANE.",
         AZUL_CLARO, AZUL_MEDIO, False),
        ("7", "Proyecto listo para DNP",
         "Con el plan verificado, la duplicidad revisada y los costos validados, el sistema "
         "entrega la ficha MGA pre-estructurada lista para ingresar a la MGA Web del DNP. "
         "El municipio llega al DNP con el proyecto 95% formulado.",
         VERDE_CLARO, VERDE_SGR, False),
    ]

    for num, titulo, desc, bg, border, es_nuevo in pasos_modo2:
        badge = ""
        if es_nuevo:
            badge = ' <font color="#E65100"><b>[NUEVO]</b></font>'
        t = Table([
            [Paragraph(f"<b>Paso {num}: {titulo}</b>{badge}",
                ParagraphStyle("ph", fontName="Helvetica-Bold", fontSize=9.5,
                    textColor=border)),
            ],
            [Paragraph(desc, S["body"])],
        ], colWidths=[W])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), bg),
            ("BACKGROUND", (0,1), (-1,-1), HexColor("#FAFAFA")),
            ("BOX", (0,0), (-1,-1), 1, border),
            ("LINEBELOW", (0,0), (0,0), 1, border),
            ("TOPPADDING",    (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING",   (0,0), (-1,-1), 10),
            ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ]))
        e.append(t)
        e.append(Spacer(1, 0.15*cm))

    e.append(Spacer(1, 0.2*cm))
    e.append(Paragraph("18.2 Sub-flujo: Inclusión en el Plan de Desarrollo", S["h2"]))

    e.append(Paragraph(
        "Cuando el sistema detecta que el proyecto no está en el Plan de Desarrollo, "
        "activa este sub-flujo de orientación. El proceso en Colombia para modificar un "
        "plan de desarrollo municipal requiere aprobación del Concejo Municipal, lo que "
        "el sistema no puede hacer por el municipio, pero sí puede facilitar:",
        S["body"]
    ))
    e.append(Spacer(1, 0.15*cm))

    subflujo = [
        ("Texto sugerido para el plan",
         "El sistema genera el texto exacto que debe añadirse al plan de desarrollo para "
         "incluir el proyecto: nombre del programa, objetivo, meta, indicador y fuente de "
         "financiación (SGR). Este texto está redactado en el lenguaje del DNP para "
         "facilitar su aprobación por el Concejo."),
        ("Artículo de inclusión",
         "Identifica en qué parte del plan (por sectores y capítulos ya existentes) "
         "debería insertarse el nuevo proyecto, para que sea coherente con la estructura "
         "del plan y no parezca un añadido desconectado."),
        ("Checklist para el Concejo",
         "Lista de documentos y pasos necesarios para someter la modificación al Concejo "
         "Municipal: proyecto de Acuerdo, exposición de motivos, concepto del Consejo "
         "Territorial de Planeación si aplica, plazo máximo según el POT vigente."),
        ("Estado en el sistema",
         "El proyecto queda marcado como 'Pendiente de inclusión en plan'. Cuando el "
         "municipio registra que el Concejo aprobó la modificación (sube el Acuerdo), "
         "el sistema actualiza el estado a 'En plan' y habilita continuar la formulación MGA."),
        ("Re-análisis del plan",
         "Cuando se sube el Acuerdo de modificación del plan, el sistema puede indexar "
         "ese documento y re-analizar las brechas para verificar que el nuevo proyecto "
         "efectivamente aparece y que no genera contradicciones con otras metas del plan."),
    ]

    for titulo_sf, desc_sf in subflujo:
        e.append(Paragraph(f"<b>▶  {titulo_sf}:</b>", S["body_bold"]))
        e.append(Paragraph(desc_sf, S["body"]))
        e.append(Spacer(1, 0.15*cm))

    e.append(Spacer(1, 0.2*cm))
    e.append(Paragraph("18.3 Estados del Proyecto en el Sistema", S["h2"]))

    e.append(header_table(
        [["Estado", "Descripción", "Siguiente paso"]],
        [
            ["borrador", "Proyecto ingresado, diagnóstico en proceso", "Esperar resultado del agente evaluador"],
            ["diagnosticado", "Diagnóstico completo en 4 dimensiones", "Revisar recomendaciones + verificar inclusión en plan"],
            ["pendiente_plan", "El proyecto NO está en el Plan de Desarrollo", "Presentar modificación al Concejo Municipal"],
            ["en_plan", "Incluido en el Plan de Desarrollo (verificado)", "Proceder con verificación duplicidad + costos"],
            ["pre_validado", "Duplicidad ok + costos validados + en plan", "Generar ficha MGA completa para MGA Web"],
            ["listo_dnp", "Ficha MGA generada, listo para asistencia técnica", "Radicar ante el DNP / OCAD correspondiente"],
            ["enviado_dnp", "Radicado — seguimiento externo al sistema", "Registrar resultado OCAD cuando se notifique"],
            ["aprobado", "OCAD aprobó el proyecto", "Proyecto pasa a fase de ejecución"],
            ["rechazado", "OCAD rechazó el proyecto", "Análisis de causas + reformulación o nuevo proyecto"],
        ],
        col_widths=[3.5*cm, 7*cm, W - 10.5*cm]
    ))

    e.append(Spacer(1, 0.3*cm))
    e.append(alert_box(
        "<b>Regla de negocio crítica:</b> Un proyecto NO puede pasar al estado 'pre_validado' "
        "ni 'listo_dnp' si su estado no es 'en_plan'. El sistema bloquea la generación "
        "de la ficha MGA final si el proyecto no tiene respaldo verificado en el Plan de "
        "Desarrollo. Esta restricción refleja el requisito obligatorio del SGR y protege "
        "al municipio de formular un proyecto que será rechazado en el primer filtro del OCAD."
    ))

    e.append(PageBreak())
    return e


# ── Footer en cada página ─────────────────────────────────────────────────────
def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GRIS_MEDIO)

    # Línea separadora footer
    canvas.setStrokeColor(GRIS_LINEA)
    canvas.setLineWidth(0.5)
    canvas.line(2*cm, 1.6*cm, A4[0] - 2*cm, 1.6*cm)

    # Texto izquierda
    canvas.drawString(2*cm, 1.1*cm, "Caja de Herramientas SGR — Municipios Cat. 5 y 6 Colombia")

    # Número de página derecha
    canvas.drawRightString(A4[0] - 2*cm, 1.1*cm, f"Página {doc.page}")

    canvas.restoreState()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    output = "/tmp/reporte_sgr_municipios_cat5_6.pdf"

    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=2*cm,
        rightMargin=2*cm,
        topMargin=2.2*cm,
        bottomMargin=2.5*cm,
        title="Caja de Herramientas SGR — Municipios Cat. 5 y 6",
        author="Darwin Fierro Ramírez",
        subject="Análisis de Pivote Estratégico — Sistema General de Regalías",
    )

    story = []
    story += build_portada()
    story += build_indice()
    story += build_s1()
    story += build_s2()
    story += build_s3()
    story += build_s4()
    story += build_s5()
    story += build_s6()
    story += build_s7()
    story += build_s8()
    story += build_s9()
    story += build_s10()
    story += build_s11()
    story += build_s12()
    story += build_s13()
    story += build_s14()
    story += build_s15()          # Modo 2 — Evaluación Inversa (análisis técnico)
    story += build_s15_acceso()   # Modelo de acceso Cat. 5/6
    story += build_s16_onboarding()
    story += build_s17_flujo()
    story += build_s18_modo2()    # Modo 2 corregido con paso de inclusión en plan

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"PDF generado: {output}")
    return output


if __name__ == "__main__":
    main()
