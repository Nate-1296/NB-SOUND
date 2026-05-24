"""PyInstaller runtime hook — Windows GUI app stdio redirect.

Executed by the PyInstaller bootloader before any Python imports.

Problem: PyInstaller builds with console=False set sys.stdout and sys.stderr
to None. Any module-level code that calls sys.stdout.isatty() or
print(..., file=sys.stderr) crashes immediately with:
  AttributeError: 'NoneType' object has no attribute 'isatty'

This is particularly acute for infra/progress.py which evaluates isatty()
at import time (module-level constants), causing the error to surface
the first time any worker thread imports that module — which happens
when the user clicks "Iniciar importación".

Fix: redirect both streams to os.devnull before any Python code runs.
Console output is discarded in windowed mode anyway; file logging still
works because infra/logger.py opens a real file handler for disk logs.
"""

import os as _os
import sys as _sys

if _sys.platform.startswith("win"):
    try:
        _nul = open(_os.devnull, "w", encoding="utf-8", errors="replace")
        if _sys.stdout is None:
            _sys.stdout = _nul
        if _sys.stderr is None:
            _sys.stderr = _nul
    except Exception:
        pass
