#!/usr/bin/env python3
# ============================================================
# DXT CONTA - Limpieza de entrega obsoleta de Planillas
# ============================================================

from __future__ import annotations

import shutil
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    target = project_root / 'modules' / 'planilla_prestamos_glosa_pdf_compacto'

    if target.exists():
        if not target.is_dir():
            raise RuntimeError(f'Ruta inesperada, no es directorio: {target}')
        shutil.rmtree(target)
        print('Carpeta obsoleta eliminada: modules/planilla_prestamos_glosa_pdf_compacto')
    else:
        print('No existe carpeta obsoleta por eliminar.')


if __name__ == '__main__':
    main()
