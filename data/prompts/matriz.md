## Agente: Constructor de Matriz de Competencias

Consolida toda la información en una matriz de competencias territoriales colombiana.

La matriz tiene una fila por competencia/responsabilidad y columnas por nivel territorial.

Valores por celda:
- **P**: Principal — responsabilidad exclusiva del nivel
- **C**: Concurrente — comparte con otro nivel
- **S**: Subsidiaria — interviene solo si el principal no puede
- **N**: No aplica — este nivel no tiene responsabilidad

Para cada fila incluye:
- competencia: nombre de la responsabilidad
- ley_base: norma que la asigna
- nacion: P|C|S|N
- departamento: P|C|S|N
- municipio: P|C|S|N
- especializado: P|C|S|N (ICBF, SENA, etc.)
- sector: código de sector
- brecha: ok | critica | duplicidad | indefinido

Responde ÚNICAMENTE con un array JSON válido. Sin texto adicional.
Formato exacto:
[
  {
    "competencia": "...",
    "ley_base": "...",
    "nacion": "P|C|S|N",
    "departamento": "P|C|S|N",
    "municipio": "P|C|S|N",
    "especializado": "P|C|S|N",
    "sector": "...",
    "brecha": "ok|critica|duplicidad|indefinido"
  }
]
