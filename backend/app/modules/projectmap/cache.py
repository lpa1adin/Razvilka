"""Граф строится за доли секунды, но в одной генерации его спрашивают много раз — кэшируем по «отпечатку»
папки (пути, размеры и время правки файлов). Изменился проект — граф пересоберётся сам."""

import os
from functools import lru_cache
from pathlib import Path

from app.modules.projectmap.graph import build, list_files, render


def _signature(root: str) -> tuple:
    files, _ = list_files(Path(root))
    return tuple((str(p), (st := os.stat(p)).st_size, st.st_mtime_ns) for p in files)


@lru_cache(maxsize=16)
def _cached(root: str, focus: str, signature: tuple, budget: int) -> str:
    return render(build(root, focus), budget)


def render_map(root: str, focus: str = "", budget: int = 9000) -> str:
    return _cached(root, focus, _signature(os.path.join(root, focus) if focus else root), budget)
