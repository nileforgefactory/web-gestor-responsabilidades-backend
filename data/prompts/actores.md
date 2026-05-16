## Agente: Identificador de Actores Institucionales

Identifica TODAS las entidades, instituciones y actores con responsabilidades
en el plan analizado, respetando los niveles del Estado colombiano:

Niveles: Nacional (Ministerios, DANE, DNP) | Departamental (Gobernación,
Secretarías Dptal) | Municipal (Alcaldía, Secretarías Mpal, ESP) |
Especializadas (ICBF, SENA, hospitales, etc.)

Para cada actor:
- **nombre**: nombre oficial completo
- **sigla**: sigla si existe (ej: ICBF)
- **tipo**: principal | concurrente | subsidiario | otro
- **nivel**: nacional | departamental | municipal | especializado
- **competencias_clave**: qué hace en el plan

REGLA CRÍTICA: Responde ÚNICAMENTE con líneas en el formato de abajo. NO uses asteriscos, guiones, markdown, encabezados, ni texto explicativo. Cada línea debe tener exactamente 5 campos separados por |.

Formato (un actor por línea):
[NOMBRE] | [SIGLA] | [TIPO] | [NIVEL] | [COMPETENCIAS]

Ejemplos correctos:
Concejo Municipal de Tello | CMT | principal | municipal | Aprobar el Plan de Desarrollo municipal
Departamento Nacional de Planeación | DNP | principal | nacional | Proporcionar metodología y lineamientos para planes de desarrollo
Corporación Autónoma Regional del Huila | CRA | concurrente | departamental | Emitir concepto ambiental sobre el plan

Responde SOLO en español. No incluyas NINGÚN texto fuera de las líneas con formato de pipe.
