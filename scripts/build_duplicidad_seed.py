"""Wrapper CLI para correr manualmente la carga de la matriz de proyectos SGR
(GESPROY/DNP) sin pasar por la UI de admin.

La lógica real vive en `app/slices/sgr/duplicidad_seed_service.py` (mismo
código que usa el endpoint `POST /sgr/duplicidad-seed/iniciar`) — este script
solo la invoca directamente, útil para correr dentro del contenedor sin subir
el archivo por HTTP.

Uso:
    python scripts/build_duplicidad_seed.py <ruta_al_xlsx>
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.slices.rag.service import RagService  # noqa: E402
from app.slices.sgr.duplicidad_seed_service import (  # noqa: E402
    get_estado,
    run_duplicidad_seed,
)


async def main(xlsx_path: Path) -> None:
    settings = get_settings()
    rag = RagService.from_settings(settings)
    try:
        await run_duplicidad_seed(xlsx_path=xlsx_path, rag=rag)
    finally:
        await rag.close()

    estado = get_estado()
    print(
        f"estado={estado.estado} filas_leidas={estado.filas_leidas} "
        f"filas_filtradas={estado.filas_filtradas} "
        f"indexados={estado.proyectos_indexados} fallidos={estado.proyectos_fallidos}",
        file=sys.stderr,
    )
    if estado.error:
        print(f"ERROR: {estado.error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Uso: python {sys.argv[0]} <ruta_al_xlsx>", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main(Path(sys.argv[1])))
