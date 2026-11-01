"""Файлы сдачи: zip-архив или папка проекта из ProjectsWithClaude (BRIEF §5.11).

Берём только текст: бинарные файлы, сборки, node_modules и секреты отбрасываем — и честно говорим об этом
пользователю (крайний случай из ТЗ). Библиотеки (vendor, *.min.*) оставляем для автотестов страницы, но
помечаем: в Ревьюера и Оценщика они не идут.
"""

import io
import os
import re
import zipfile
from pathlib import Path, PurePosixPath

from app.core.config import settings
from app.modules.projectmap.graph import SECRET, SKIP_DIRS, TEXT_EXT, VENDOR_HINT

MAX_ZIP = 20 * 1024 * 1024
MAX_FILE = 300_000
MAX_TOTAL = 4 * 1024 * 1024
MAX_FILES = 600
EXTRA_TEXT = {".txt", ".cfg", ".ini", ".env.example", ".sh", ".dockerfile", ".gitignore"}


class SourceError(Exception):
    pass


def _is_text_path(path: str) -> bool:
    name = PurePosixPath(path).name
    return Path(name).suffix.lower() in TEXT_EXT | EXTRA_TEXT or name in ("Dockerfile", "Makefile", "requirements.txt")


def _collect(items, warnings: list[str]) -> tuple[dict[str, str], list[str]]:
    """items: (путь, функция чтения байтов, размер). Общая фильтрация для zip и папки."""
    files: dict[str, str] = {}
    vendor: list[str] = []
    skipped = {"secrets": [], "deps": 0, "binary": 0, "large": []}
    total = 0
    for path, read, size in items:
        parts = PurePosixPath(path).parts
        if any(p in SKIP_DIRS or (p.startswith(".") and p not in (".env.example",)) for p in parts[:-1]):
            skipped["deps"] += 1
            continue
        name = parts[-1]
        if SECRET.match(name) and not name.endswith(".example"):
            skipped["secrets"].append(path)
            continue
        if not _is_text_path(path):
            skipped["binary"] += 1
            continue
        if size > MAX_FILE:
            skipped["large"].append(path)
            continue
        if len(files) >= MAX_FILES or total + size > MAX_TOTAL:
            raise SourceError(f"Слишком большой проект: больше {MAX_FILES} файлов или {MAX_TOTAL // 1024 // 1024} МБ кода. Сдайте нужную часть.")
        try:
            text = read().decode("utf-8")
        except UnicodeDecodeError:
            skipped["binary"] += 1
            continue
        files[path] = text
        total += size
        if VENDOR_HINT.search(str(PurePosixPath(path).parent)) or ".min." in name:
            vendor.append(path)
    if skipped["secrets"]:
        warnings.append(f"Отброшены файлы с секретами: {', '.join(skipped['secrets'][:5])} — их не нужно сдавать.")
    if skipped["deps"]:
        warnings.append(f"Пропущено служебных файлов (node_modules, .git, сборки, кэши): {skipped['deps']}.")
    if skipped["binary"]:
        warnings.append(f"Пропущено бинарных файлов (картинки, шрифты, архивы): {skipped['binary']}.")
    if skipped["large"]:
        warnings.append(f"Пропущены слишком большие файлы: {', '.join(skipped['large'][:5])}.")
    if not any(p not in vendor for p in files):
        raise SourceError("В сдаче не нашлось ни одного файла с кодом.")
    return files, vendor


def from_zip(data: bytes) -> tuple[dict[str, str], list[str], list[str]]:
    if len(data) > MAX_ZIP:
        raise SourceError("Архив больше 20 МБ — уберите сборки и зависимости.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        infos = [i for i in archive.infolist() if not i.is_dir()]
    except zipfile.BadZipFile as exc:
        raise SourceError("Архив повреждён или это не zip.") from exc
    names = [i.filename for i in infos if not i.filename.startswith("__MACOSX/")]
    # Архив с одной корневой папкой — убираем её из путей: project/index.html → index.html
    roots = {n.split("/", 1)[0] for n in names}
    strip = len(roots) == 1 and all("/" in n for n in names)
    items = []
    for info in infos:
        name = info.filename
        if name.startswith("__MACOSX/") or ".." in PurePosixPath(name).parts or name.startswith("/"):
            continue
        rel = name.split("/", 1)[1] if strip else name
        items.append((rel, (lambda i=info: archive.read(i)), info.file_size))
    warnings: list[str] = []
    files, vendor = _collect(items, warnings)
    return files, vendor, warnings


def list_projects() -> list[str]:
    root = Path(settings.projects_root)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".") and p.name not in SKIP_DIRS)


def from_folder(project: str, focus: str = "") -> tuple[dict[str, str], list[str], list[str]]:
    root = os.path.realpath(settings.projects_root)
    base = os.path.realpath(os.path.join(root, project, focus or ""))
    if "/" in project or not base.startswith(root + os.sep) or not os.path.isdir(base):
        raise SourceError("Такой папки среди проектов нет")
    items = []
    for dirpath, dirs, names in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(names):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, base).replace(os.sep, "/")
            items.append((rel, (lambda f=full: Path(f).read_bytes()), os.path.getsize(full)))
    warnings: list[str] = []
    files, vendor = _collect(items, warnings)
    return files, vendor, warnings


def from_workspace(folder: Path) -> tuple[dict[str, str], list[str], list[str]]:
    """Рабочая папка пути «напиши заново сам» — тот же фильтр, что и для папки проекта."""
    if not folder.is_dir():
        raise SourceError("Рабочей папки ещё нет — создайте её на странице пути")
    items = []
    for dirpath, dirs, names in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(names):
            full = os.path.join(dirpath, name)
            items.append((os.path.relpath(full, folder).replace(os.sep, "/"), (lambda f=full: Path(f).read_bytes()), os.path.getsize(full)))
    warnings: list[str] = []
    files, vendor = _collect(items, warnings)
    return files, vendor, warnings


def code_for_review(files: dict[str, str], vendor: list[str], budget: int) -> tuple[dict[str, str], list[str]]:
    """Что отдать Ревьюеру и Оценщику: свой код без библиотек; не влезло — сначала код, потом данные и тексты."""
    own = {p: t for p, t in files.items() if p not in vendor and not re.search(r"(^|/)(package-lock\.json|uv\.lock|poetry\.lock|yarn\.lock)$", p)}
    data_like = (".json", ".md", ".txt", ".yml", ".yaml", ".toml", ".csv")
    order = sorted(own, key=lambda p: (p.endswith(data_like), -len(own[p]) if p.endswith(data_like) else 0, p))
    chosen, left_out, size = {}, [], 0
    for p in order:
        if size + len(own[p]) > budget:
            left_out.append(p)
            continue
        chosen[p] = own[p]
        size += len(own[p])
    return chosen, left_out
