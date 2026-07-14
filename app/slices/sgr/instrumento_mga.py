"""Instrumento de formulación MGA — 50 preguntas clave por módulo.

Extraído de Instrumento_MGA_Municipios_Cat5y6.xlsx (DNP, Manual conceptual MGA v1.0).
Cada pregunta guía la generación de la sección MGA correspondiente y sirve de
base para la verificación de cobertura (qué quedó sin responder / débil) tras
generar la Ficha MGA con IA.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PreguntaMGA:
    numero: int
    modulo: int  # 1-4, o 5 = Presentación
    seccion: str  # subsección temática (ej. "2.1 PLAN DE DESARROLLO")
    pregunta: str
    que_busca: str
    como_responder: str
    alerta_cat56: str


PREGUNTAS_MGA: list[PreguntaMGA] = [
    PreguntaMGA(
        numero=1, modulo=1, seccion="""2.1 PLAN DE DESARROLLO – Articulación con la política pública""",
        pregunta="""¿Cuál es el nombre del Plan Nacional de Desarrollo vigente y en cuál de sus estrategias encaja tu proyecto?""",
        que_busca="""La MGA exige que todo proyecto esté alineado con el PND, planes sectoriales y el Plan de Desarrollo Territorial.""",
        como_responder="""Consulta el PND vigente en el sitio del DNP. Busca la estrategia o programa que más se relacione con el problema que vas a resolver. Copia el nombre exacto en los campos de la herramienta.""",
        alerta_cat56="""El municipio cat. 5 y 6 debe alinear el proyecto con el Plan de Desarrollo Municipal aprobado. Si no hay BPIN municipal activo, apóyate en la secretaría de planeación para identificar el programa presupuestal.""",
    ),
    PreguntaMGA(
        numero=2, modulo=1, seccion="""2.1 PLAN DE DESARROLLO – Articulación con la política pública""",
        pregunta="""¿En cuál programa del Plan de Desarrollo Municipal aparece este problema o necesidad?""",
        que_busca="""Demuestra pertinencia territorial, requisito clave para viabilización en el SGR.""",
        como_responder="""Lee el Plan de Desarrollo del municipio (disponible en la alcaldía o en el SIGOB). Identifica el eje estratégico, programa y subprograma que se relaciona con tu proyecto.""",
        alerta_cat56="""En municipios pequeños el Plan de Desarrollo puede ser muy general. Usa el programa más cercano y documenta la relación con argumentos de diagnóstico.""",
    ),
    PreguntaMGA(
        numero=3, modulo=1, seccion="""2.2 PROBLEMÁTICA – Identificación y descripción del problema""",
        pregunta="""¿Cuál es la situación negativa concreta que afecta a la comunidad? (NO empieces con 'falta de...')""",
        que_busca="""El problema central es el núcleo del árbol de problemas. Debe expresarse como situación negativa, no como ausencia de solución.""",
        como_responder="""Describe en 2-3 oraciones qué está pasando, dónde ocurre y cuándo se detectó. Ejemplo: 'El 80% de los hogares del área urbana no tienen acceso continuo al servicio de agua potable.'""",
        alerta_cat56="""Apóyate en el diagnóstico del Plan de Desarrollo y estadísticas del DANE, SISPRO, DNP Terridata u otras fuentes oficiales. En municipios pequeños, un diagnóstico participativo con la comunidad también es válido como evidencia.""",
    ),
    PreguntaMGA(
        numero=4, modulo=1, seccion="""2.2 PROBLEMÁTICA – Identificación y descripción del problema""",
        pregunta="""¿Con qué número o dato concreto puedes medir qué tan grave es el problema? (línea de base)""",
        que_busca="""La línea de base es el valor actual del indicador del problema. Sirve para medir el cambio generado por el proyecto.""",
        como_responder="""Busca estadísticas recientes en fuentes oficiales. Ejemplo: 'Cobertura de agua potable: 45% (DANE, 2023)'. Ese porcentaje es tu línea de base. El proyecto debe aumentarlo.""",
        alerta_cat56="""Si no hay dato oficial disponible, puedes usar registros administrativos del municipio, encuestas de diagnóstico o informes de la entidad prestadora. Documenta bien la fuente para que sea verificable por los evaluadores del SGR.""",
    ),
    PreguntaMGA(
        numero=5, modulo=1, seccion="""2.2 PROBLEMÁTICA – Identificación y descripción del problema""",
        pregunta="""¿Cuáles son los 3 principales efectos negativos que genera este problema en la comunidad?""",
        que_busca="""Los efectos (copa del árbol) justifican la urgencia de intervenir. Los efectos indirectos sirven de 'fin' en la matriz de marco lógico.""",
        como_responder="""Pregúntate: ¿Qué consecuencias tiene el problema si no se resuelve? Lista efectos directos (inmediatos) e indirectos (de segundo nivel). Ej.: Directo: enfermedades gastrointestinales. Indirecto: aumento del gasto en salud.""",
        alerta_cat56="""Conecta los efectos con indicadores sectoriales del municipio. Esto fortalece el argumento ante la banca de proyectos del SGR.""",
    ),
    PreguntaMGA(
        numero=6, modulo=1, seccion="""2.2 PROBLEMÁTICA – Identificación y descripción del problema""",
        pregunta="""¿Cuáles son las 2 o 3 causas principales que generan el problema?""",
        que_busca="""Las causas (raíces del árbol) se convertirán en objetivos específicos y luego en productos del proyecto. Su identificación correcta define toda la cadena de valor.""",
        como_responder="""Pregúntate: ¿Por qué existe este problema? Separa causas directas (primer nivel) e indirectas (segundo nivel). Verifica que si eliminas la causa, el problema mejora.""",
        alerta_cat56="""No inflés las causas: cada causa directa genera un objetivo específico y un conjunto de productos con costo. En municipios cat. 5 y 6 con presupuesto limitado, menos causas = proyectos más manejables.""",
    ),
    PreguntaMGA(
        numero=7, modulo=1, seccion="""2.3 PARTICIPANTES – ¿Quiénes están involucrados?""",
        pregunta="""¿Quiénes se benefician directamente del proyecto?""",
        que_busca="""Los beneficiarios son quienes recibirán los productos o servicios del proyecto.""",
        como_responder="""Lista los grupos de personas que mejorarán su situación: comunidades, organizaciones, empresas. Describe sus intereses frente al proyecto.""",
        alerta_cat56="""En municipios pequeños, identifica asociaciones comunitarias, juntas de acción comunal o gremios locales. Su apoyo puede ser un factor de viabilidad social para el SGR.""",
    ),
    PreguntaMGA(
        numero=8, modulo=1, seccion="""2.3 PARTICIPANTES – ¿Quiénes están involucrados?""",
        pregunta="""¿Hay personas o grupos que pueden oponerse o verse perjudicados por el proyecto?""",
        que_busca="""Identificar oponentes y perjudicados permite anticipar conflictos y diseñar estrategias de manejo que después se reflejan en costos.""",
        como_responder="""Pregúntate: ¿Quién pierde algo si se ejecuta este proyecto? ¿Hay intereses económicos o sociales en contra? Define estrategias concretas para gestionar esa oposición.""",
        alerta_cat56="""En comunidades rurales o pequeñas es común que proyectos de infraestructura afecten predios privados o usos del suelo. Documenta acuerdos previos o procesos de socialización realizados.""",
    ),
    PreguntaMGA(
        numero=9, modulo=1, seccion="""2.3 PARTICIPANTES – ¿Quiénes están involucrados?""",
        pregunta="""¿Qué entidades o actores pueden aportar recursos o colaborar con el proyecto?""",
        que_busca="""Los cooperantes son aliados que aportarán recursos (dinero, especie o conocimiento) y deben registrarse en el esquema financiero del Módulo 4.""",
        como_responder="""Identifica: otras entidades públicas (departamento, nación), empresas privadas, cooperación internacional u organizaciones de la sociedad civil. Documenta qué compromiso ya existe.""",
        alerta_cat56="""En proyectos SGR de municipios pequeños, los cofinanciadotes fortalecen la viabilidad. Consulta si hay compromisos de contrapartida del departamento o de la nación.""",
    ),
    PreguntaMGA(
        numero=10, modulo=1, seccion="""2.4 POBLACIÓN – ¿A cuántas personas afecta y quiénes son?""",
        pregunta="""¿Cuántas personas padecen el problema en el área de estudio?""",
        que_busca="""La población afectada establece la demanda potencial del proyecto y debe calcularse con fuentes estadísticas confiables.""",
        como_responder="""Usa el censo del DANE más reciente o las proyecciones de población. Especifica si es urbana, rural o total, y el año del dato.""",
        alerta_cat56="""DNP Terridata tiene datos desagregados por municipio. Para municipios pequeños, también sirven los registros del SISBEN o de la entidad prestadora del servicio.""",
    ),
    PreguntaMGA(
        numero=11, modulo=1, seccion="""2.4 POBLACIÓN – ¿A cuántas personas afecta y quiénes son?""",
        pregunta="""De ese total, ¿a cuántas personas va a atender el proyecto directamente? ¿Por qué ese subgrupo?""",
        que_busca="""La población objetivo es el grupo focalizado. Debe ser consistente con la capacidad del proyecto y el déficit calculado en el estudio de mercado (Módulo 2).""",
        como_responder="""Define criterios de focalización claros: zona geográfica, condición socioeconómica, grupo etario. El tamaño debe ser realista para la capacidad de ejecución del municipio.""",
        alerta_cat56="""Los municipios cat. 5 y 6 tienen capacidad institucional limitada. Es mejor un proyecto pequeño bien ejecutado que uno grande mal ejecutado. El SGR prefiere proyectos con población objetivo bien definida y alcanzable.""",
    ),
    PreguntaMGA(
        numero=12, modulo=1, seccion="""2.4 POBLACIÓN – ¿A cuántas personas afecta y quiénes son?""",
        pregunta="""¿Cómo se distribuye la población objetivo por sexo, edad y grupos étnicos?""",
        que_busca="""La caracterización demográfica permite incorporar enfoques diferenciales y de género, exigidos en la política pública actual.""",
        como_responder="""Consulta el DANE o el SISBEN para datos de distribución por sexo y grupos etarios. Identifica si hay comunidades étnicas (indígenas, afro) en el área.""",
        alerta_cat56="""Si el municipio tiene resguardos o territorios colectivos, el proyecto puede requerir consulta previa. Consulta con la secretaría de asuntos étnicos o el Ministerio del Interior.""",
    ),
    PreguntaMGA(
        numero=13, modulo=1, seccion="""2.5 OBJETIVOS – ¿Qué quiere lograr el proyecto?""",
        pregunta="""¿Cuál es el objetivo general del proyecto? (expresa el problema en positivo con verbo en infinitivo)""",
        que_busca="""El objetivo general es la transformación positiva del problema central. Es el 'propósito' del marco lógico.""",
        como_responder="""Transforma el problema en logro: si el problema es 'baja cobertura de agua potable', el objetivo es 'Aumentar la cobertura del servicio de agua potable en la zona urbana del municipio XXX'. Inicia con verbo en infinitivo.""",
        alerta_cat56="""Evita incluir en el objetivo la solución ('mediante construcción de...'), las metas numéricas o los fines. El SGR evalúa que el objetivo sea claro, medible y coherente con el problema descrito.""",
    ),
    PreguntaMGA(
        numero=14, modulo=1, seccion="""2.5 OBJETIVOS – ¿Qué quiere lograr el proyecto?""",
        pregunta="""¿Con qué indicador vas a medir si lograste el objetivo? ¿Cuál es la meta?""",
        que_busca="""El indicador de resultado debe ser el mismo indicador de la línea de base. La meta es el valor esperado al final del proyecto.""",
        como_responder="""Usa el indicador que mediste en la línea de base. Define una meta realista. Ej: si la línea de base es 45% de cobertura, la meta podría ser 75%. Especifica la unidad (porcentaje, número de personas, toneladas).""",
        alerta_cat56="""Elige indicadores del Banco de Indicadores Sectoriales (BIS) del DNP. Los evaluadores del SGR revisan que el indicador sea verificable y la meta sea alcanzable con el presupuesto disponible.""",
    ),
    PreguntaMGA(
        numero=15, modulo=1, seccion="""2.5 OBJETIVOS – ¿Qué quiere lograr el proyecto?""",
        pregunta="""¿Cuáles son los 2 o 3 objetivos específicos del proyecto? (uno por cada causa directa identificada)""",
        que_busca="""Cada causa directa del árbol de problemas se convierte en un objetivo específico (medio) que el proyecto debe cumplir.""",
        como_responder="""Transforma cada causa directa en positivo: 'Deficientes prácticas de separación' → 'Mejorar las prácticas de separación de residuos'. Lista solo las causas directas, no las indirectas.""",
        alerta_cat56="""El número de objetivos específicos define el número de productos y el tamaño del presupuesto. En municipios pequeños, 2-3 objetivos específicos son manejables. Más de 4 puede hacer el proyecto muy complejo para la capacidad local.""",
    ),
    PreguntaMGA(
        numero=16, modulo=1, seccion="""2.6 ALTERNATIVAS DE SOLUCIÓN – ¿Cuál es el mejor camino?""",
        pregunta="""¿Cuáles son las 2 o 3 formas diferentes de alcanzar el objetivo?""",
        que_busca="""Las alternativas son los distintos caminos para resolver el problema. La MGA exige evaluarlas y seleccionar la más conveniente.""",
        como_responder="""Piensa en opciones tecnológicas, operativas o de localización. Ejemplo: Alternativa 1: construir acueducto nuevo. Alternativa 2: rehabilitar red existente y ampliar cobertura. Alternativa 3: solución individual (filtros, pozos).""",
        alerta_cat56="""Para proyectos en fase de perfil (la más común en municipios pequeños), basta con dos alternativas. Descarta solo las que sean claramente inviables por ley, presupuesto o capacidad técnica. El SGR requiere que se justifique la alternativa seleccionada.""",
    ),
    PreguntaMGA(
        numero=17, modulo=1, seccion="""2.6 ALTERNATIVAS DE SOLUCIÓN – ¿Cuál es el mejor camino?""",
        pregunta="""¿Por qué la alternativa elegida es mejor que las otras?""",
        que_busca="""La selección de la alternativa debe justificarse con criterios técnicos, económicos y de viabilidad.""",
        como_responder="""Compara las alternativas usando costos estimados, beneficios esperados, facilidad de implementación y aceptación de la comunidad. La MGA permite usar evaluación multicriterio para formalizar esta comparación.""",
        alerta_cat56="""Si solo tienes una alternativa viable (por restricciones territoriales o normativas), documenta las razones por las que se descartan las demás. El SGR acepta alternativa única si la justificación es sólida.""",
    ),
    PreguntaMGA(
        numero=18, modulo=2, seccion="""3.1 NECESIDADES – Estudio de oferta, demanda y déficit""",
        pregunta="""¿Qué bien o servicio produce el proyecto para resolver cada objetivo específico?""",
        que_busca="""Define los productos concretos que entregará el proyecto: campañas, infraestructuras, servicios, formaciones, etc.""",
        como_responder="""Por cada objetivo específico, pregúntate: ¿Qué entrego concreto al final? Ej: 'Kilómetros de red construidos', 'Número de familias capacitadas', 'Unidades de equipo instaladas'. Define la unidad de medida.""",
        alerta_cat56="""Elige productos que puedas medir, ejecutar y verificar con la capacidad técnica del municipio. Productos demasiado complejos pueden ser frenados en viabilización.""",
    ),
    PreguntaMGA(
        numero=19, modulo=2, seccion="""3.1 NECESIDADES – Estudio de oferta, demanda y déficit""",
        pregunta="""¿Cuánto del bien o servicio existe actualmente en el municipio? (oferta)""",
        que_busca="""La oferta actual SIN proyecto determina cuánto déficit existe. No se debe incluir lo que el proyecto generará.""",
        como_responder="""Recoge datos de cuánto del servicio ya se presta: infraestructura existente, capacidad instalada, cobertura actual. Fuentes: secretarías municipales, entidades prestadoras, DANE, Terridata.""",
        alerta_cat56="""Si no hay datos disponibles, usa registros administrativos del municipio o estimaciones basadas en visitas de campo debidamente documentadas. Los evaluadores del SGR verifican este dato.""",
    ),
    PreguntaMGA(
        numero=20, modulo=2, seccion="""3.1 NECESIDADES – Estudio de oferta, demanda y déficit""",
        pregunta="""¿Cuánto del bien o servicio necesita la comunidad? (demanda)""",
        que_busca="""La demanda proyectada permite calcular el déficit que el proyecto debe cerrar y justifica el tamaño de la inversión.""",
        como_responder="""Estima la demanda con tasas de crecimiento poblacional (DANE) y la necesidad per cápita del servicio. Proyecta el horizonte de evaluación del proyecto (vida útil del activo principal). Ejemplo: 'Si hay 5.000 habitantes y el servicio debe cubrir el 100%, la demanda es 5.000 usuarios.'""",
        alerta_cat56="""En municipios pequeños la demanda crece poco. Una sobrestimación de la demanda puede invalidar el proyecto por falta de consistencia. Sé conservador y justifica con fuentes verificables.""",
    ),
    PreguntaMGA(
        numero=21, modulo=2, seccion="""3.1 NECESIDADES – Estudio de oferta, demanda y déficit""",
        pregunta="""¿Cuál es el déficit entre lo que hay y lo que se necesita?""",
        que_busca="""El déficit justifica la inversión y la MGA lo calcula automáticamente (demanda − oferta). Debe ser positivo para que el proyecto tenga razón de ser.""",
        como_responder="""La herramienta lo calcula cuando ingresas oferta y demanda. Verifica que el déficit sea coherente con el tamaño del proyecto: si el déficit es de 1.000 personas, no formules un proyecto para 10.000.""",
        alerta_cat56="""Si el déficit es muy pequeño, el proyecto puede no ser priorizado por el SGR. Si es muy grande, puede superar la capacidad de ejecución municipal. Ajusta la población objetivo hasta equilibrar.""",
    ),
    PreguntaMGA(
        numero=22, modulo=2, seccion="""3.2 ANÁLISIS TÉCNICO – ¿Cómo se ejecutará el proyecto?""",
        pregunta="""¿Cuáles son las especificaciones técnicas mínimas de cada producto que vas a entregar?""",
        que_busca="""La descripción técnica sustenta la viabilidad y es base para los futuros pliegos de contratación.""",
        como_responder="""Describe las características técnicas esenciales de cada producto: materiales, capacidad, dimensiones, estándares o normas aplicables. Si no eres técnico, apóyate en el profesional de la secretaría sectorial.""",
        alerta_cat56="""En municipios cat. 5 y 6 puede no haber profesionales especializados en planta. Busca apoyo técnico en la Gobernación, en el DNP o en entidades sectoriales (MVCT, MinSalud, MinEducación) que tienen equipos de asistencia técnica territorial.""",
    ),
    PreguntaMGA(
        numero=23, modulo=2, seccion="""3.2 ANÁLISIS TÉCNICO – ¿Cómo se ejecutará el proyecto?""",
        pregunta="""¿Cuáles normas técnicas o requisitos legales debe cumplir cada producto?""",
        que_busca="""El proyecto debe cumplir normativa sectorial vigente. El incumplimiento puede impedir la viabilización.""",
        como_responder="""Consulta las normas del sector: RAS para agua y saneamiento, NSR para construcciones, normas del MEN para educación, etc. Cita la norma en el campo técnico de la MGA.""",
        alerta_cat56="""Las guías sectoriales del SGR detallan requisitos normativos por tipo de proyecto. Descárgalas del portal del DNP antes de formular.""",
    ),
    PreguntaMGA(
        numero=24, modulo=2, seccion="""3.3 LOCALIZACIÓN – ¿Dónde se ejecutará el proyecto?""",
        pregunta="""¿Por qué ese lugar es el más adecuado para ejecutar el proyecto?""",
        que_busca="""La localización debe estar justificada con criterios técnicos, de acceso, usos del suelo y normativa de ordenamiento territorial.""",
        como_responder="""Argumenta con criterios como: cercanía a la población objetivo, disponibilidad de servicios públicos, compatibilidad con el POT/PBOT/EOT del municipio, accesibilidad vial. Usa el método de ponderación de factores si tienes varias opciones.""",
        alerta_cat56="""Verifica que el uso del suelo del lugar elegido sea compatible con el proyecto según el EOT o PBOT municipal. Un predio en zona de protección o sin uso compatible puede bloquear la ejecución.""",
    ),
    PreguntaMGA(
        numero=25, modulo=2, seccion="""3.3 LOCALIZACIÓN – ¿Dónde se ejecutará el proyecto?""",
        pregunta="""¿El municipio tiene los permisos, predios o derechos de uso necesarios para ejecutar ahí?""",
        que_busca="""La disponibilidad del predio y los permisos son requisitos de viabilidad.""",
        como_responder="""Confirma si el predio es del municipio, si tiene escritura pública, si se requiere servidumbre o licencia ambiental. Esto debe quedar documentado en los soportes del proyecto.""",
        alerta_cat56="""Los municipios cat. 5 y 6 frecuentemente no tienen legalizada la propiedad de predios. Si el terreno no está disponible, el proyecto no puede iniciar. Incluye el costo de adquisición si aplica.""",
    ),
    PreguntaMGA(
        numero=26, modulo=2, seccion="""3.4 CADENA DE VALOR Y COSTOS – ¿Cuánto cuesta y qué hay que hacer?""",
        pregunta="""¿Cuáles son todas las actividades necesarias para entregar cada producto?""",
        que_busca="""La cadena de valor descompone cada objetivo en productos y cada producto en actividades con sus insumos y costos.""",
        como_responder="""Por cada producto, lista todas las actividades necesarias (mínimo 2). Ejemplo: Producto 'Acueducto construido' → Actividades: estudios y diseños, adquisición de materiales, construcción de redes, instalación de equipos, interventoría.""",
        alerta_cat56="""La interventoría es OBLIGATORIA en proyectos de obra pública financiados con SGR. Debe aparecer como actividad costeada. No olvidarla es un error frecuente de formuladores principiantes.""",
    ),
    PreguntaMGA(
        numero=27, modulo=2, seccion="""3.4 CADENA DE VALOR Y COSTOS – ¿Cuánto cuesta y qué hay que hacer?""",
        pregunta="""¿Cuánto cuesta cada actividad y en qué categoría de insumo entra?""",
        que_busca="""Los costos deben registrarse por categorías predefinidas de la MGA (11 categorías: mano de obra, materiales, transporte, servicios, terrenos, maquinaria, etc.)""",
        como_responder="""Consulta precios de mercado locales o del año de formulación. Usa cotizaciones, tarifas del SMLMV o registros históricos de proyectos similares del municipio. Distribuye los costos por año de ejecución.""",
        alerta_cat56="""No incluyas IVA ni utilidades si ya están reflejados en el precio de mercado. Incluye los costos de operación y mantenimiento posterior: el SGR revisa la sostenibilidad del proyecto.""",
    ),
    PreguntaMGA(
        numero=28, modulo=2, seccion="""3.4 CADENA DE VALOR Y COSTOS – ¿Cuánto cuesta y qué hay que hacer?""",
        pregunta="""¿Cuál es la ruta crítica del proyecto? (las actividades sin las cuales todo se retrasa)""",
        que_busca="""Identificar la ruta crítica permite gestionar el cronograma y es requisito de la MGA.""",
        como_responder="""Marca al menos una actividad por producto como ruta crítica: son las que determinan el tiempo mínimo de ejecución y no pueden retrasarse. Normalmente son estudios y diseños, adquisición de predios, o construcción principal.""",
        alerta_cat56="""En municipios pequeños, las demoras en licencias y permisos son la causa #1 de retrasos. Marca esas gestiones previas como ruta crítica.""",
    ),
    PreguntaMGA(
        numero=29, modulo=2, seccion="""3.5 RIESGOS – ¿Qué puede salir mal?""",
        pregunta="""¿Cuáles son los 3 principales riesgos que amenazan la ejecución del proyecto?""",
        que_busca="""El análisis de riesgos permite anticipar problemas y diseñar medidas de manejo. Es obligatorio registrar al menos un riesgo del objetivo, un producto y una actividad de ruta crítica.""",
        como_responder="""Clasifica los riesgos por probabilidad (alta/media/baja) e impacto (alto/medio/bajo). Para cada riesgo define la medida: aceptar, evitar, mitigar (reducir) o transferir (ej: póliza). Los riesgos con costo deben reflejarse en el presupuesto.""",
        alerta_cat56="""Los riesgos más comunes en municipios cat. 5 y 6: baja capacidad técnica local, demoras en licencias y permisos, inestabilidad de personal, cambios de administración. Documentarlos muestra madurez del proyecto ante el SGR.""",
    ),
    PreguntaMGA(
        numero=30, modulo=2, seccion="""3.5 RIESGOS – ¿Qué puede salir mal?""",
        pregunta="""¿Qué pasa si los riesgos se materializan? ¿Tienes un plan B?""",
        que_busca="""Los planes de contingencia muestran que el formulador pensó en escenarios adversos y tiene respuesta.""",
        como_responder="""Por cada riesgo crítico, describe qué harías si ocurre. Ejemplo: si el contratista incumple, la contingencia es tener la póliza de cumplimiento ejecutable. Si hay cambio de precios, la contingencia es reserva de contingencia presupuestal.""",
        alerta_cat56="""Los proyectos SGR deben contemplar riesgos de mercado (precios, demanda) y riesgos de gestión (contratación, permisos). Transferir riesgos a pólizas es una buena práctica y fortalece la viabilización.""",
    ),
    PreguntaMGA(
        numero=31, modulo=2, seccion="""3.6 BENEFICIOS E INGRESOS – ¿Qué gana la comunidad y el proyecto?""",
        pregunta="""¿Qué beneficios sociales genera el proyecto que se puedan valorar en pesos?""",
        que_busca="""Los beneficios sociales (ahorros, ingresos, tiempos evitados) alimentan la evaluación económica y demuestran que el proyecto genera más valor del que cuesta.""",
        como_responder="""Identifica: costos que la comunidad ya no tendrá que pagar, tiempo que se ahorrará, ingresos adicionales generados. Cuantifícalos en unidades y valóralos con precios de mercado o costos evitados. Ej: si el proyecto evita que 200 personas viajen 2 horas para acceder al servicio, ese tiempo tiene valor.""",
        alerta_cat56="""Para proyectos sociales donde no hay ingresos comerciales, el beneficio principal es el ahorro en costos o la mejora en calidad de vida. El SGR acepta metodologías de valoración como 'costo evitado' o 'disponibilidad a pagar' bien documentadas.""",
    ),
    PreguntaMGA(
        numero=32, modulo=2, seccion="""3.6 BENEFICIOS E INGRESOS – ¿Qué gana la comunidad y el proyecto?""",
        pregunta="""¿El proyecto va a generar ingresos propios (tarifas, ventas, arriendos)?""",
        que_busca="""Los ingresos alimentan el flujo de caja financiero y determinan la sostenibilidad del proyecto.""",
        como_responder="""Si hay tarifas (agua, aseo, transporte), documenta el esquema tarifario. Si hay ventas de productos (residuos reciclados, cosechas), estima los ingresos con precios de mercado históricos.""",
        alerta_cat56="""La mayoría de proyectos en municipios pequeños NO generan ingresos propios (son bienes públicos). En ese caso, usa la evaluación costo-eficiencia en lugar de la costo-beneficio. El SGR contempla ambas metodologías.""",
    ),
    PreguntaMGA(
        numero=33, modulo=3, seccion="""4.1 FLUJO DE CAJA – El resumen financiero del proyecto""",
        pregunta="""¿Cuánto entra y cuánto sale de dinero en cada año del proyecto?""",
        que_busca="""El flujo de caja organiza todos los costos, ingresos y beneficios año a año para calcular si el proyecto genera valor.""",
        como_responder="""La herramienta construye el flujo automáticamente con los datos de costos, ingresos y beneficios que ya ingresaste en el Módulo 2. Tu tarea es verificar que todos los datos estén completos y que los periodos sean correctos.""",
        alerta_cat56="""Para municipios cat. 5 y 6 cuyo proyecto no genera ingresos, el flujo financiero tendrá solo costos. Eso es normal para proyectos sociales. Lo importante es el flujo económico (que incluye beneficios sociales).""",
    ),
    PreguntaMGA(
        numero=34, modulo=3, seccion="""4.1 FLUJO DE CAJA – El resumen financiero del proyecto""",
        pregunta="""¿Cuál es la tasa de descuento que vas a usar para evaluar el proyecto?""",
        que_busca="""La tasa de descuento refleja el costo de oportunidad del dinero: cuánto rinde la mejor alternativa de inversión disponible.""",
        como_responder="""Para la evaluación financiera usa la tasa de interés de referencia del mercado (DTF o TIB). Para la evaluación económica, el DNP define la Tasa Social de Descuento (TSD), que actualmente es del 12% anual. La herramienta la pide explícitamente.""",
        alerta_cat56="""Si no tienes experiencia financiera, usa la TSD del DNP (12%) para la evaluación económica y una tasa bancaria referente (ej: DTF + 4%) para la financiera. Si el municipio no tiene crédito, registra solo la evaluación económica.""",
    ),
    PreguntaMGA(
        numero=35, modulo=3, seccion="""4.2 INDICADORES DE DECISIÓN – ¿El proyecto conviene o no?""",
        pregunta="""¿Qué significan el VPN y la TIR y cómo los interpreto?""",
        que_busca="""El VPN (Valor Presente Neto) y la TIR (Tasa Interna de Retorno) son los indicadores principales para decidir si un proyecto es conveniente.""",
        como_responder="""VPN > 0 significa que el proyecto genera más valor del que cuesta → CONVIENE ejecutarlo. TIR > tasa de descuento usada → CONVIENE. La herramienta los calcula automáticamente; tu trabajo es interpretarlos correctamente.""",
        alerta_cat56="""Si el VPNE (económico) es positivo aunque el VPN financiero sea negativo, el proyecto sigue siendo conveniente para el sector público: crea valor social aunque no sea rentable comercialmente. Esto es normal y esperado en proyectos sociales de municipios pequeños.""",
    ),
    PreguntaMGA(
        numero=36, modulo=3, seccion="""4.2 INDICADORES DE DECISIÓN – ¿El proyecto conviene o no?""",
        pregunta="""¿Qué es la evaluación costo-eficiencia y cuándo debo usarla en lugar del costo-beneficio?""",
        que_busca="""Cuando no es posible valorar los beneficios en pesos (ej: proyectos de salud, educación, cultura), se usa la evaluación costo-eficiencia: la alternativa más barata por unidad de beneficio.""",
        como_responder="""La herramienta calcula automáticamente costo por capacidad y costo por beneficiario. Compara las alternativas: elige la de menor costo por unidad de beneficio. Aplica cuando tienes más de una alternativa.""",
        alerta_cat56="""Para municipios cat. 5 y 6 con proyectos sociales (salud, educación, cultura, deporte), la evaluación costo-eficiencia es la más adecuada y la más común. No te compliques buscando valorar beneficios que no tienen precio de mercado.""",
    ),
    PreguntaMGA(
        numero=37, modulo=3, seccion="""4.2 INDICADORES DE DECISIÓN – ¿El proyecto conviene o no?""",
        pregunta="""¿Para qué sirve la evaluación multicriterio y cuándo la uso?""",
        que_busca="""La evaluación multicriterio permite incluir criterios cualitativos (aceptación social, impacto ambiental, desarrollo tecnológico) que los indicadores financieros no capturan.""",
        como_responder="""Selecciona los criterios relevantes de la lista de la herramienta (hasta 9). Asígnales un peso según su importancia y califica cada alternativa. La herramienta genera un ranking. Úsala para complementar la decisión, especialmente cuando los resultados económicos son similares entre alternativas.""",
        alerta_cat56="""El criterio 'Aceptación de la población' es especialmente relevante en municipios pequeños donde la legitimidad social del proyecto es clave para su éxito. Documentar participación comunitaria aquí fortalece el proyecto ante el SGR.""",
    ),
    PreguntaMGA(
        numero=38, modulo=3, seccion="""4.5 DECISIÓN – ¿Qué hago con los resultados?""",
        pregunta="""Con base en la evaluación, ¿cuál alternativa seleccionas y por qué?""",
        que_busca="""La decisión cierra el Módulo 3 y determina qué alternativa pasa al Módulo 4 de programación.""",
        como_responder="""Selecciona la alternativa con mejores indicadores (mayor VPNE o menor costo por beneficiario). Documenta la justificación. Si solo hay una alternativa, confirma que los indicadores son positivos antes de avanzar.""",
        alerta_cat56="""Si ninguna alternativa muestra indicadores favorables, revisa si hay errores en los datos de costos o beneficios antes de descartar el proyecto. A veces el problema está en la formulación, no en la viabilidad real del proyecto.""",
    ),
    PreguntaMGA(
        numero=39, modulo=4, seccion="""5.1 MATRIZ DE MARCO LÓGICO – El mapa del proyecto""",
        pregunta="""¿Cuáles son los 4 niveles de la matriz de marco lógico y qué va en cada uno?""",
        que_busca="""La matriz de marco lógico resume toda la lógica del proyecto en 4 niveles: Fin, Propósito (objetivo general), Productos y Actividades.""",
        como_responder="""La herramienta genera los 4 niveles automáticamente con lo que ya registraste. Verifica que: Fin = meta del PND al que contribuyes. Propósito = tu objetivo general. Productos = los productos de la cadena de valor. Actividades = las actividades costeadas.""",
        alerta_cat56="""El error más común es que no haya consistencia entre los niveles. Revisa de abajo hacia arriba: ¿Las actividades producen los productos? ¿Los productos logran el objetivo? ¿El objetivo contribuye al fin? Si en algún nivel la respuesta es 'no', hay un error que el SGR detectará.""",
    ),
    PreguntaMGA(
        numero=40, modulo=4, seccion="""5.1 MATRIZ DE MARCO LÓGICO – El mapa del proyecto""",
        pregunta="""¿La lógica del proyecto es consistente de principio a fin?""",
        que_busca="""La consistencia vertical y horizontal de la matriz garantiza que el proyecto tenga coherencia interna.""",
        como_responder="""Verifica: (1) Vertical: causas → objetivos → productos → actividades. Cada nivel es necesario y suficiente para el siguiente. (2) Horizontal: cada objetivo, producto y actividad tiene un indicador, una fuente de verificación y un supuesto.""",
        alerta_cat56="""Haz esta verificación antes de presentar el proyecto. Pide a alguien que no conoce el proyecto que lo lea y pregunte '¿y eso por qué?'. Si no puede seguir la lógica, hay inconsistencias.""",
    ),
    PreguntaMGA(
        numero=41, modulo=4, seccion="""5.2 INDICADORES Y FUENTES DE VERIFICACIÓN – ¿Cómo mido si se logró?""",
        pregunta="""¿Con qué indicador mido el cumplimiento de cada producto?""",
        que_busca="""Los indicadores de producto miden si se entregaron los bienes y servicios comprometidos. Deben tener unidad de medida, meta y fuente de verificación.""",
        como_responder="""La herramienta arma el nombre del indicador con la fórmula: 'producto + condición deseada'. Tu trabajo es completar la unidad (número, metros, kilogramos, porcentaje), la meta por año y el documento que lo verifica.""",
        alerta_cat56="""Elige indicadores que el municipio pueda realmente medir y reportar. Si no tienes sistema de información, una acta de entrega, informe de interventoría o registro fotográfico puede ser la fuente de verificación.""",
    ),
    PreguntaMGA(
        numero=42, modulo=4, seccion="""5.2 INDICADORES Y FUENTES DE VERIFICACIÓN – ¿Cómo mido si se logró?""",
        pregunta="""¿De dónde se toma la información para verificar el cumplimiento de cada indicador?""",
        que_busca="""Las fuentes de verificación son los documentos que demuestran que se alcanzaron las metas.""",
        como_responder="""Para cada indicador define una fuente: estadísticas sectoriales, informes de supervisión, auditorías, encuestas de satisfacción, registros contables. Deben ser documentos reales que existirán durante la ejecución.""",
        alerta_cat56="""En municipios pequeños las fuentes más comunes son: actas de entrega, informes de interventoría, registros de beneficiarios firmados, facturas y contratos. Deben quedar archivados y disponibles para las visitas de seguimiento del SGR.""",
    ),
    PreguntaMGA(
        numero=43, modulo=4, seccion="""5.2 INDICADORES Y FUENTES DE VERIFICACIÓN – ¿Cómo mido si se logró?""",
        pregunta="""¿Qué son los supuestos y cómo los formulo?""",
        que_busca="""Los supuestos son condiciones externas que deben cumplirse para que el proyecto logre sus objetivos, pero que están fuera del control del equipo ejecutor.""",
        como_responder="""Toma los riesgos externos que identificaste en el Módulo 2 y exprésalos en positivo. Ejemplo: riesgo 'inestabilidad de precios' → supuesto 'Los precios de los insumos se mantienen estables durante la ejecución'. Registra un supuesto por nivel de la matriz.""",
        alerta_cat56="""Los supuestos deben ser realistas, no deseables. Si el supuesto no es razonablemente probable, puede ser una amenaza fatal para el proyecto que hay que abordar antes de formularlo.""",
    ),
    PreguntaMGA(
        numero=44, modulo=4, seccion="""5.5 FUENTES DE FINANCIACIÓN – ¿Con qué dinero se ejecuta?""",
        pregunta="""¿Qué parte del proyecto financia el SGR y qué parte pone el municipio u otras entidades?""",
        que_busca="""El esquema financiero cierra la brecha entre los costos del proyecto y las fuentes de recursos. Es donde formalmente se solicitan los recursos del SGR.""",
        como_responder="""Distribuye los costos por etapa (preinversión, inversión, operación), entidad financiadora, tipo de recurso y periodo. El total de aportes debe cuadrar exactamente con el total de costos del proyecto.""",
        alerta_cat56="""El SGR no financia el 100% de todos los proyectos. Consulta los acuerdos de la Comisión Rectora vigentes para saber qué porcentaje puede financiar el SGR y si se requiere contrapartida del municipio o el departamento. Municipios cat. 5 y 6 tienen condiciones especiales de cofinanciación.""",
    ),
    PreguntaMGA(
        numero=45, modulo=4, seccion="""5.5 FUENTES DE FINANCIACIÓN – ¿Con qué dinero se ejecuta?""",
        pregunta="""¿Cuál es la clasificación presupuestal del gasto que corresponde al proyecto?""",
        que_busca="""Cada gasto debe clasificarse según el manual presupuestal del DNP para que sea elegible con recursos de regalías.""",
        como_responder="""Consulta el Manual de Clasificación Presupuestal del Gasto de Inversión del DNP. Selecciona el sector, programa y subprograma que corresponde al proyecto. Si no sabes cómo clasificarlo, consulta con la secretaría de hacienda o planeación del municipio.""",
        alerta_cat56="""Un error en la clasificación presupuestal puede hacer que el proyecto sea devuelto para ajuste. Es uno de los errores técnicos más frecuentes en municipios pequeños. Apóyate en la Gobernación o en el OCAD regional.""",
    ),
    PreguntaMGA(
        numero=46, modulo=4, seccion="""5.5 FUENTES DE FINANCIACIÓN – ¿Con qué dinero se ejecuta?""",
        pregunta="""¿Cómo aseguro que el municipio puede operar y mantener lo que se construya una vez el SGR deje de financiar?""",
        que_busca="""La sostenibilidad operativa demuestra que el proyecto no morirá una vez terminada la inversión. Los evaluadores del SGR la verifican.""",
        como_responder="""Describe quién será el responsable de operar el bien o servicio después del proyecto: una empresa de servicios públicos, la secretaría sectorial, una organización comunitaria. Incluye estimación de costos de operación y mantenimiento en el esquema financiero.""",
        alerta_cat56="""Este es el talón de Aquiles de muchos proyectos en municipios pequeños: se construye pero no hay presupuesto ni capacidad para operar. Si el municipio no puede sostener el proyecto con recursos propios, busca articular con el esquema de subsidios sectorial antes de formular.""",
    ),
    PreguntaMGA(
        numero=47, modulo=5, seccion="""6. DOCUMENTOS DE SOPORTE – ¿Qué adjunto?""",
        pregunta="""¿En qué fase de preinversión está mi proyecto (perfil, prefactibilidad o factibilidad)?""",
        que_busca="""La fase determina el nivel de detalle de los estudios y los documentos que debes adjuntar. El SGR exige más documentación a mayor madurez del proyecto.""",
        como_responder="""Define la fase antes de empezar: Perfil = análisis básico con identificación del problema y alternativas preliminares. Prefactibilidad = estudios más detallados de 2+ alternativas. Factibilidad = estudios completos de la alternativa seleccionada.""",
        alerta_cat56="""La mayoría de municipios cat. 5 y 6 presentan proyectos en fase de PERFIL. Es el nivel mínimo aceptado por el SGR para proyectos de inversión. Si el proyecto requiere infraestructura compleja, considera avanzar a prefactibilidad para fortalecer la viabilización.""",
    ),
    PreguntaMGA(
        numero=48, modulo=5, seccion="""6. DOCUMENTOS DE SOPORTE – ¿Qué adjunto?""",
        pregunta="""¿Cuáles son los documentos de soporte que debo adjuntar según el sector y la fase?""",
        que_busca="""Los documentos de soporte prueban la viabilidad técnica, legal, ambiental y social del proyecto y son revisados por el banco de proyectos y el OCAD.""",
        como_responder="""Consulta las guías sectoriales del SGR (disponibles en el portal del DNP). Los documentos típicos por área son: Mercado/necesidades: diagnóstico con datos estadísticos. Técnico: diseños y especificaciones. Legal: permisos, escrituras, licencias. Social: actas de socialización, consultas previas si aplica. Ambiental: licencia o concepto ambiental.""",
        alerta_cat56="""Para municipios cat. 5 y 6 sin capacidad técnica para estudios complejos, los Acuerdos 15 y 17 de la Comisión Rectora del SGR tienen requisitos diferenciados por fase. Revisa el acuerdo vigente. La Gobernación puede apoyar con asistencia técnica en estudios sectoriales.""",
    ),
    PreguntaMGA(
        numero=49, modulo=5, seccion="""6. DOCUMENTOS DE SOPORTE – ¿Qué adjunto?""",
        pregunta="""¿Hice la verificación final de consistencia antes de transferir?""",
        que_busca="""La herramienta advierte algunas inconsistencias pero no garantiza la confiabilidad de todos los datos. La revisión humana es indispensable.""",
        como_responder="""Antes de transferir: (1) Usa la lista de verificación de la guía. (2) Revisa que problema, objetivos, productos, indicadores y costos estén alineados. (3) Confirma que el esquema financiero cuadra. (4) Verifica que los documentos exigidos por fase y sector estén adjuntos.""",
        alerta_cat56="""El error de transferir un proyecto incompleto o inconsistente genera devoluciones que retrasan meses el acceso a recursos. Haz siempre una revisión final con un par o con el equipo de planeación municipal antes de dar clic en 'transferir'.""",
    ),
    PreguntaMGA(
        numero=50, modulo=5, seccion="""6. DOCUMENTOS DE SOPORTE – ¿Qué adjunto?""",
        pregunta="""¿A dónde va el proyecto una vez lo transfiero y cuáles son los pasos siguientes?""",
        que_busca="""Al transferir, el proyecto ingresa al banco de proyectos y luego al proceso de viabilización y aprobación del OCAD correspondiente.""",
        como_responder="""Una vez transferido: el banco de proyectos valida la información. Luego pasa a viabilización sectorial. Si es viable, llega al OCAD (municipales, departamentales o nacionales según el monto). El OCAD aprueba, prioriza y programa los recursos.""",
        alerta_cat56="""Para municipios cat. 5 y 6, los proyectos van generalmente al OCAD Municipal (hasta cierto monto) o al OCAD Departamental. Averigua los montos y competencias del OCAD en el acuerdo de la Comisión Rectora vigente. La secretaría de planeación departamental puede orientarte.""",
    ),
]


def preguntas_por_modulo(modulo: int) -> list[PreguntaMGA]:
    """Preguntas del módulo indicado (1=Identificación .. 4=Programación, 5=Presentación)."""
    return [p for p in PREGUNTAS_MGA if p.modulo == modulo]


MODULO_NOMBRE: dict[int, str] = {
    1: """Identificación""",
    2: """Preparación""",
    3: """Evaluación""",
    4: """Programación""",
    5: """Presentación""",
}


@dataclass(frozen=True)
class ItemVerificacion:
    modulo: str  # "M1".."M4" | "PR"
    item: str
    como_verificarlo: str
    alerta_sgr: str


LISTA_VERIFICACION: list[ItemVerificacion] = [
    ItemVerificacion(
        modulo="""M1""",
        item="""Articulación con PND, plan sectorial y plan de desarrollo territorial registrada con nombres exactos.""",
        como_verificarlo="""Compara lo registrado con los documentos oficiales.""",
        alerta_sgr="""Los evaluadores verifican nombre y código exacto del programa.""",
    ),
    ItemVerificacion(
        modulo="""M1""",
        item="""Árbol de problemas completo: problema central, efectos directos e indirectos, causas directas e indirectas.""",
        como_verificarlo="""Lee el árbol de abajo hacia arriba con la lógica 'si X entonces Y'.""",
        alerta_sgr="""Sin árbol coherente, el proyecto puede ser devuelto.""",
    ),
    ItemVerificacion(
        modulo="""M1""",
        item="""Línea de base con valor numérico, unidad de medida y fuente citada.""",
        como_verificarlo="""Verifica que la fuente sea verificable (DANE, Terridata, registros oficiales).""",
        alerta_sgr="""El SGR rechaza líneas de base sin soporte estadístico confiable.""",
    ),
    ItemVerificacion(
        modulo="""M1""",
        item="""Participantes registrados con posición, intereses y estrategias de gestión.""",
        como_verificarlo="""Revisa que oponentes y perjudicados tienen estrategia y costo asociado si aplica.""",
        alerta_sgr="""Proyectos con conflictos sociales no gestionados se bloquean en OCAD.""",
    ),
    ItemVerificacion(
        modulo="""M1""",
        item="""Población afectada, objetivo y características demográficas consistentes con el déficit.""",
        como_verificarlo="""Compara cifra de población objetivo con el déficit del estudio de mercado.""",
        alerta_sgr="""Inconsistencia numérica = devolución automática.""",
    ),
    ItemVerificacion(
        modulo="""M1""",
        item="""Objetivo general con verbo infinitivo, sin alternativa, fin ni meta incluida.""",
        como_verificarlo="""Verifica que no empiece con 'Mediante...' ni incluya cifras de meta.""",
        alerta_sgr="""Error muy frecuente en formuladores principiantes.""",
    ),
    ItemVerificacion(
        modulo="""M1""",
        item="""Al menos una alternativa nombrada y método de evaluación seleccionado.""",
        como_verificarlo="""Confirma que la herramienta dejó avanzar al Módulo 2.""",
        alerta_sgr="""Con una sola alternativa se aplica costo-beneficio por defecto.""",
    ),
    ItemVerificacion(
        modulo="""M2""",
        item="""Estudio de necesidades con serie histórica, proyección y déficit por producto.""",
        como_verificarlo="""Verifica que la serie tenga mínimo 2 años y la proyección cubra la vida útil.""",
        alerta_sgr="""Serie con menos de 2 años es insuficiente para evaluadores SGR.""",
    ),
    ItemVerificacion(
        modulo="""M2""",
        item="""Análisis técnico con normas aplicables y relaciones entre productos; soportes adjuntos.""",
        como_verificarlo="""Confirma que las normas citadas son las vigentes al año de formulación.""",
        alerta_sgr="""Normas desactualizadas invalidan la viabilidad técnica.""",
    ),
    ItemVerificacion(
        modulo="""M2""",
        item="""Localización definida (macro y micro) con criterios y compatibilidad con ordenamiento territorial.""",
        como_verificarlo="""Verifica el POT/PBOT/EOT: el uso del suelo debe ser compatible.""",
        alerta_sgr="""Predio incompatible con uso del suelo = proyecto no viable.""",
    ),
    ItemVerificacion(
        modulo="""M2""",
        item="""Cadena de valor completa con ruta crítica e interventoría costeadas.""",
        como_verificarlo="""Revisa que interventoría aparezca como actividad con costo.""",
        alerta_sgr="""Olvidar interventoría es el error #1 en municipios pequeños.""",
    ),
    ItemVerificacion(
        modulo="""M2""",
        item="""Al menos 3 riesgos registrados (objetivo, producto, actividad de ruta crítica) con medidas.""",
        como_verificarlo="""Verifica que medidas con costo estén en el presupuesto.""",
        alerta_sgr="""El SGR verifica coherencia entre riesgos y presupuesto.""",
    ),
    ItemVerificacion(
        modulo="""M2""",
        item="""Ingresos o beneficios identificados, cuantificados y valorados.""",
        como_verificarlo="""Si no hay ingresos comerciales, confirma que hay beneficios sociales valorados.""",
        alerta_sgr="""Sin beneficios, la evaluación económica no puede calcularse.""",
    ),
    ItemVerificacion(
        modulo="""M3""",
        item="""Flujo de caja financiero y económico consolidados con todos los periodos.""",
        como_verificarlo="""Verifica que los flujos incluyan todos los años del horizonte de evaluación.""",
        alerta_sgr="""Un horizonte más corto que la vida útil subestima los beneficios.""",
    ),
    ItemVerificacion(
        modulo="""M3""",
        item="""Indicadores de decisión positivos: VPN/VPNE > 0 o costo-eficiencia menor entre alternativas.""",
        como_verificarlo="""Si el VPNE es negativo, revisa costos y beneficios antes de continuar.""",
        alerta_sgr="""VPNE negativo requiere justificación técnica muy sólida para SGR.""",
    ),
    ItemVerificacion(
        modulo="""M3""",
        item="""Alternativa seleccionada y decisión de avanzar registrada.""",
        como_verificarlo="""Confirma que la herramienta habilita el Módulo 4.""",
        alerta_sgr="""Sin decisión registrada no se puede programar.""",
    ),
    ItemVerificacion(
        modulo="""M4""",
        item="""Matriz de marco lógico consistente: lógica vertical y horizontal verificada.""",
        como_verificarlo="""Lee de abajo arriba: actividades → productos → objetivo → fin.""",
        alerta_sgr="""Inconsistencia lógica = devolución por banco de proyectos.""",
    ),
    ItemVerificacion(
        modulo="""M4""",
        item="""Indicadores con unidad, meta por periodo y fuente de verificación; hoja de vida elaborada.""",
        como_verificarlo="""Verifica que cada indicador tenga fuente real y alcanzable.""",
        alerta_sgr="""Indicadores sin fuente verificable son un riesgo de seguimiento.""",
    ),
    ItemVerificacion(
        modulo="""M4""",
        item="""Supuestos formulados en positivo, uno por nivel de la matriz.""",
        como_verificarlo="""Transforma riesgos externos en hipótesis positivas.""",
        alerta_sgr="""Falta de supuestos es señal de formulación incompleta.""",
    ),
    ItemVerificacion(
        modulo="""M4""",
        item="""Esquema financiero cuadrado: total aportes = total costos, con clasificador presupuestal correcto.""",
        como_verificarlo="""Suma todos los aportes y compara con el total de costos del proyecto.""",
        alerta_sgr="""Descuadre de un peso = devolución. Revisa categorías presupuestales.""",
    ),
    ItemVerificacion(
        modulo="""PR""",
        item="""Documentos de soporte adjuntos según fase (perfil/prefactibilidad/factibilidad) y sector.""",
        como_verificarlo="""Consulta guías sectoriales SGR y Acuerdos 15 y 17 de la Comisión Rectora.""",
        alerta_sgr="""Falta de soportes es la causa más frecuente de devolución en OCAD.""",
    ),
    ItemVerificacion(
        modulo="""PR""",
        item="""Revisión final de consistencia realizada con un par o el equipo de planeación.""",
        como_verificarlo="""Pide a otra persona que lea el proyecto completo antes de transferir.""",
        alerta_sgr="""Dos pares de ojos detectan errores que el formulador no ve.""",
    ),
]
