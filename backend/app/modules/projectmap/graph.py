"""Граф проекта без Claude: структура, связи между файлами и «оглавление» каждого файла.

Зачем: агенту не нужно читать весь проект, чтобы понять, как он устроен. Карта в несколько килобайт
заменяет десятки килобайт исходников; конкретный файл агент читает, только когда нужны точные строки
(ADR-008, BRIEF §5.5 «карта проекта»).

Только стандартная библиотека — модуль запускается и в платформе, и как скрипт из скилла Claude Code:
    python3 graph.py <папка> [--focus часть] [--file путь] [--json]
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "dist", "build", ".next", "__pycache__", ".cache", "graphify-out",
    ".pytest_cache", ".mypy_cache", "coverage", ".idea", ".vscode", "pyodide",
}
VENDOR_HINT = re.compile(r"(^|/)(vendor|vendors|lib|libs|third[_-]?party)(/|$)", re.I)
TEXT_EXT = {".html", ".htm", ".css", ".scss", ".js", ".mjs", ".jsx", ".ts", ".tsx", ".py", ".sql", ".md", ".json", ".toml", ".yml", ".yaml", ".vue", ".svelte"}
LANG = {
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "SCSS", ".js": "JavaScript", ".mjs": "JavaScript",
    ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".py": "Python", ".sql": "SQL", ".md": "Markdown",
    ".json": "JSON", ".toml": "TOML", ".yml": "YAML", ".yaml": "YAML", ".vue": "Vue", ".svelte": "Svelte",
}
MAX_FILE = 400_000  # больше — почти наверняка сборка или данные
MAX_FILES = 3000
SECRET = re.compile(r"^(\.env.*|.*\.(pem|key|p12|pfx)|id_rsa.*|id_ed25519.*|credentials.*|secrets?\..*)$", re.I)


# ---------- Файлы ----------


def _is_minified(path: Path, text: str) -> bool:
    if ".min." in path.name:
        return True
    lines = text.count("\n") + 1
    return len(text) > 20_000 and len(text) / lines > 400


def list_files(root: Path) -> tuple[list[Path], list[str]]:
    """Свои файлы проекта и отдельно — подключённые библиотеки (их не разбираем, только называем)."""
    files, vendor = [], []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        for name in sorted(names):
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if SECRET.match(name) or path.suffix.lower() not in TEXT_EXT:
                continue
            if VENDOR_HINT.search(rel_dir) or ".min." in name:
                vendor.append(rel)
                continue
            files.append(path)
            if len(files) >= MAX_FILES:
                return files, vendor
    return files, vendor


def _read(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_FILE:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ---------- Разбор по языкам ----------


class _Html(HTMLParser):
    LANDMARKS = {"header", "nav", "main", "section", "article", "aside", "footer", "form", "dialog"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.classes: Counter = Counter()
        self.headings: list[tuple[int, str]] = []
        self.landmarks: list[str] = []
        self.styles: list[str] = []
        self.scripts: list[str] = []
        self.anchors: set[str] = set()
        self.title = ""
        self._heading: int | None = None
        self._text: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.append(a["id"])
        for cls in (a.get("class") or "").split():
            self.classes[cls] += 1
        if tag in self.LANDMARKS:
            label = tag + (f"#{a['id']}" if a.get("id") else "") + (f".{a['class'].split()[0]}" if a.get("class") else "")
            self.landmarks.append(label)
        if tag == "link" and "stylesheet" in (a.get("rel") or "") and a.get("href"):
            self.styles.append(a["href"])
        if tag == "script" and a.get("src"):
            self.scripts.append(a["src"])
        if tag == "a" and (a.get("href") or "").startswith("#") and len(a["href"]) > 1:
            self.anchors.add(a["href"][1:])
        if re.fullmatch(r"h[1-6]", tag):
            self._heading, self._text = int(tag[1]), []
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if self._heading and tag == f"h{self._heading}":
            text = re.sub(r"\s+", " ", "".join(self._text)).strip()
            self.headings.append((self._heading, text[:80]))
            self._heading = None
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._heading:
            self._text.append(data)
        if self._in_title:
            self.title += data.strip()


def parse_html(text: str) -> dict:
    p = _Html()
    try:
        p.feed(text)
    except Exception:  # битая разметка не должна ронять карту
        pass
    return {
        "title": p.title,
        "landmarks": p.landmarks,
        "headings": p.headings,
        "ids": p.ids,
        "classes": dict(p.classes),
        "styles": p.styles,
        "scripts": p.scripts,
        "anchors": sorted(p.anchors),
    }


_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def parse_css(text: str) -> dict:
    text = _CSS_COMMENT.sub("", text)
    media = [re.sub(r"\s+", " ", m.strip()) for m in re.findall(r"@media([^{]+)\{", text)]
    selectors = []
    for block in re.findall(r"([^{}@;]+)\{", text):
        for sel in block.split(","):
            sel = re.sub(r"\s+", " ", sel.strip())
            if sel and not sel.startswith(("from", "to")) and not re.fullmatch(r"[\d.]+%", sel):
                selectors.append(sel)
    classes = Counter(re.findall(r"\.([a-zA-Z_][\w-]*)", " ".join(selectors)))
    layout = Counter(re.findall(r"display\s*:\s*(flex|grid|inline-flex|inline-grid)", text))
    return {
        "rules": len(selectors),
        "classes": dict(classes),
        "media": list(dict.fromkeys(media)),
        "variables": sorted(set(re.findall(r"(--[\w-]+)\s*:", text)))[:40],
        "imports": re.findall(r"@import\s+(?:url\()?['\"]?([^'\")\s;]+)", text),
        "keyframes": re.findall(r"@keyframes\s+([\w-]+)", text),
        "layout": dict(layout),
        "features": [f for f in ("clamp(", "grid-template", "position: sticky", "aspect-ratio", "container-type", ":has(", "transition", "@supports") if f in text],
    }


_JS_IMPORT = re.compile(r"""(?:import\s[^'"]*?from\s*|import\s*\(\s*|require\(\s*|import\s+)['"]([^'"]+)['"]""")
_JS_FUNC = re.compile(r"(?:^|\n)\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(([^)]*)\)")
_JS_ARROW = re.compile(r"(?:^|\n)\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\(([^)]*)\)|([A-Za-z_$][\w$]*))\s*=>")
_JS_CLASS = re.compile(r"(?:^|\n)\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)(?:\s+extends\s+([\w$.]+))?")
_JS_CONST = re.compile(r"(?:^|\n)(?:export\s+)?const\s+([A-Z][A-Z0-9_]{2,})\s*=")
_JS_DOM = re.compile(r"""(?:querySelector(?:All)?|getElementById|getElementsByClassName|closest)\(\s*['"`]([^'"`]+)['"`]""")
_JS_EVENT = re.compile(r"""addEventListener\(\s*['"]([\w:-]+)['"]""")


def parse_js(text: str) -> dict:
    functions = [f"{m.group(1)}({m.group(2).strip()[:40]})" for m in _JS_FUNC.finditer(text)]
    functions += [f"{m.group(1)}({(m.group(2) or m.group(3) or '').strip()[:40]})" for m in _JS_ARROW.finditer(text)]
    return {
        "imports": list(dict.fromkeys(_JS_IMPORT.findall(text))),
        "exports": sorted(set(re.findall(r"export\s+(?:default\s+)?(?:async\s+)?(?:function|const|class|let)\s+([\w$]+)", text))),
        "functions": list(dict.fromkeys(functions))[:60],
        "classes": [m.group(1) + (f" extends {m.group(2)}" if m.group(2) else "") for m in _JS_CLASS.finditer(text)],
        "constants": list(dict.fromkeys(_JS_CONST.findall(text)))[:20],
        "dom": list(dict.fromkeys(_JS_DOM.findall(text)))[:40],
        "events": sorted(set(_JS_EVENT.findall(text))),
        "react": bool(re.search(r"from ['\"]react['\"]", text)),
    }


def _ann(node) -> str:
    try:
        return ast.unparse(node) if node is not None else ""
    except Exception:
        return ""


def parse_py(text: str) -> dict:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return {"error": f"синтаксическая ошибка, строка {exc.lineno}"}
    imports, functions, classes = [], [], []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports.append(("." * node.level) + (node.module or ""))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            args = ", ".join(a.arg for a in node.args.args)
            functions.append(f"{node.name}({args})" + (f" -> {_ann(node.returns)}" if node.returns else "") + f" :{node.lineno}")
        elif isinstance(node, ast.ClassDef):
            fields, methods = [], []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    fields.append(f"{item.target.id}: {_ann(item.annotation)[:40]}")
                elif isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    methods.append(item.name)
                    if item.name == "__init__":
                        fields += [t.attr for s in ast.walk(item) if isinstance(s, ast.Assign) for t in s.targets
                                   if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self"]
            bases = ", ".join(_ann(b) for b in node.bases)
            classes.append({"name": node.name + (f"({bases})" if bases else ""), "line": node.lineno,
                            "fields": list(dict.fromkeys(fields))[:20], "methods": methods[:30]})
    return {"imports": list(dict.fromkeys(imports)), "functions": functions[:60], "classes": classes[:40]}


def parse_md(text: str) -> dict:
    heads = []
    in_code = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        elif not in_code and (m := re.match(r"(#{1,3})\s+(.+)", line)):
            heads.append((len(m.group(1)), m.group(2).strip()[:80]))
    return {"headings": heads[:40]}


def parse_json(path: Path, text: str) -> dict:
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    if path.name == "package.json":
        return {
            "scripts": list((data.get("scripts") or {}).keys()),
            "dependencies": list((data.get("dependencies") or {}).keys()),
            "devDependencies": list((data.get("devDependencies") or {}).keys()),
        }
    return {"keys": list(data.keys())[:20]} if isinstance(data, dict) else {"items": len(data) if isinstance(data, list) else 0}


def parse_sql(text: str) -> dict:
    return {
        "tables": re.findall(r"create\s+table\s+(?:if\s+not\s+exists\s+)?[\"`]?([\w.]+)", text, re.I),
        "statements": dict(Counter(m.upper() for m in re.findall(r"^\s*(select|insert|update|delete|create|alter|drop)\b", text, re.I | re.M))),
    }


def parse_file(path: Path, text: str) -> dict:
    ext = path.suffix.lower()
    if ext in (".html", ".htm", ".vue", ".svelte"):
        info = parse_html(text)
        if ext in (".vue", ".svelte"):
            info |= {"script": parse_js(text)}
        return info
    if ext in (".css", ".scss"):
        return parse_css(text)
    if ext in (".js", ".mjs", ".jsx", ".ts", ".tsx"):
        return parse_js(text)
    if ext == ".py":
        return parse_py(text)
    if ext == ".md":
        return parse_md(text)
    if ext == ".json":
        return parse_json(path, text)
    if ext == ".sql":
        return parse_sql(text)
    return {}


# ---------- Граф ----------


def _resolve(base: Path, target: str, root: Path, known: set[str]) -> str | None:
    """Относительная ссылка или импорт → путь файла проекта (с угадыванием расширения, как сборщики)."""
    if re.match(r"^(https?:)?//|^data:|^#", target):
        return None
    target = target.split("?")[0].split("#")[0]
    start = root if target.startswith("/") else base.parent
    candidate = (start / target.lstrip("/")).resolve()
    try:
        rel = candidate.relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    for option in (rel, f"{rel}.js", f"{rel}.ts", f"{rel}.tsx", f"{rel}.jsx", f"{rel}/index.js", f"{rel}/index.ts", f"{rel}/index.tsx"):
        if option in known:
            return option
    return rel if target.startswith(".") or "/" in target else None


def build(root: str | Path, focus: str = "") -> dict:
    root = Path(root).resolve()
    scope = (root / focus).resolve() if focus else root
    files, vendor = list_files(scope)
    rel = lambda p: p.relative_to(root).as_posix()  # noqa: E731
    known = {rel(p) for p in files}
    nodes, edges = {}, []
    py_modules = {rel(p)[:-3].replace("/", "."): rel(p) for p in files if p.suffix == ".py"}

    for path in files:
        text = _read(path)
        key = rel(path)
        info = {"lang": LANG.get(path.suffix.lower(), path.suffix), "lines": text.count("\n") + 1 if text else 0, "bytes": len(text.encode())}
        if not text:
            info["skipped"] = "слишком большой или не читается"
        elif _is_minified(path, text):
            info["skipped"] = "минифицирован"
            vendor.append(key)
            continue
        else:
            info |= parse_file(path, text)
        nodes[key] = info

        for href in info.get("styles", []):
            if t := _resolve(path, href, root, known):
                edges.append((key, t, "стили"))
        for src in info.get("scripts", []):
            if t := _resolve(path, src, root, known):
                edges.append((key, t, "скрипт"))
        for imp in info.get("imports", []):
            if path.suffix == ".py":
                base = imp.lstrip(".")
                hit = py_modules.get(base) or next((v for k, v in py_modules.items() if k.endswith("." + base) or k.startswith(base + ".")), None)
                if hit and hit != key:
                    edges.append((key, hit, "импорт"))
            elif t := _resolve(path, imp, root, known):
                if t in known:
                    edges.append((key, t, "импорт"))

    # Связи HTML ↔ CSS ↔ JS по классам: что стилизовано, но не используется, и наоборот
    html_classes = Counter()
    for k, n in nodes.items():
        html_classes.update(n.get("classes", {}) if n["lang"] == "HTML" else {})
    css_classes = Counter()
    for k, n in nodes.items():
        if n["lang"] in ("CSS", "SCSS"):
            css_classes.update(n.get("classes", {}))
    js_dom = {s for n in nodes.values() for s in n.get("dom", [])}
    js_classes = {c for s in js_dom for c in re.findall(r"\.([\w-]+)", s)} | {
        c for n in nodes.values() for c in re.findall(r"classList\.\w+\(\s*['\"]([\w-]+)", "")}
    ids = {i for n in nodes.values() for i in n.get("ids", [])}
    anchors = {a for n in nodes.values() for a in n.get("anchors", [])}

    return {
        "root": root.name,
        "focus": focus,
        "files": len(nodes),
        "languages": dict(Counter(n["lang"] for n in nodes.values()).most_common()),
        "vendor": sorted(set(vendor)),
        "nodes": nodes,
        "edges": sorted(set(edges)),
        "cross": {
            "styled_not_used": sorted(set(css_classes) - set(html_classes) - js_classes)[:40] if html_classes else [],
            "used_not_styled": sorted(set(html_classes) - set(css_classes))[:40] if css_classes else [],
            "broken_anchors": sorted(anchors - ids),
            "js_hooks": sorted(js_dom)[:40],
        },
    }


# ---------- Текст для агента ----------


def _short(items, limit: int, sep: str = ", ") -> str:
    items = list(items)
    more = f"{sep}…ещё {len(items) - limit}" if len(items) > limit else ""
    return sep.join(str(i) for i in items[:limit]) + more


def file_summary(path: str, n: dict, detail: bool = False) -> list[str]:
    head = f"{path} — {n['lang']}, {n['lines']} строк"
    if n.get("skipped"):
        return [f"{head} ({n['skipped']})"]
    out = [head]
    lim = 40 if detail else 12
    if n["lang"] == "HTML":
        if n.get("title"):
            out.append(f"  title: {n['title']}")
        if n.get("landmarks"):
            out.append(f"  каркас: {_short(n['landmarks'], lim, ' › ')}")
        if n.get("headings"):
            out.append("  заголовки: " + _short((f"h{l} {t}" for l, t in n["headings"]), lim, " | "))
        if n.get("ids"):
            out.append(f"  id: {_short(n['ids'], lim)}")
        if n.get("classes"):
            top = sorted(n["classes"].items(), key=lambda kv: -kv[1])
            out.append("  классы: " + _short((f"{c}×{k}" if k > 1 else c for c, k in top), lim * 2))
    elif n["lang"] in ("CSS", "SCSS"):
        out.append(f"  правил: {n.get('rules', 0)}; раскладка: {n.get('layout') or '—'}; приёмы: {', '.join(n.get('features', [])) or '—'}")
        if n.get("media"):
            out.append(f"  @media: {_short(n['media'], lim, ' | ')}")
        if n.get("variables"):
            out.append(f"  переменные: {_short(n['variables'], lim)}")
        if n.get("classes"):
            out.append(f"  классы: {_short(sorted(n['classes']), lim * 3)}")
        if n.get("keyframes"):
            out.append(f"  анимации: {', '.join(n['keyframes'])}")
    elif n["lang"] in ("JavaScript", "TypeScript"):
        for label, key in (("импорт", "imports"), ("экспорт", "exports"), ("функции", "functions"), ("классы", "classes"),
                           ("константы", "constants"), ("DOM", "dom"), ("события", "events")):
            if n.get(key):
                out.append(f"  {label}: {_short(n[key], lim)}")
    elif n["lang"] == "Python":
        if n.get("error"):
            out.append(f"  {n['error']}")
        if n.get("imports"):
            out.append(f"  импорт: {_short(n['imports'], lim)}")
        for c in n.get("classes", [])[: lim]:
            out.append(f"  class {c['name']} :{c['line']}" + (f" поля: {_short(c['fields'], 10)}" if c["fields"] else "")
                       + (f"; методы: {_short(c['methods'], 10)}" if c["methods"] and detail else ""))
        if n.get("functions"):
            out.append(f"  функции: {_short(n['functions'], lim)}")
    elif n["lang"] == "Markdown" and n.get("headings"):
        out.append("  разделы: " + _short((t for l, t in n["headings"] if l <= 2), lim, " | "))
    elif n["lang"] == "JSON" and (n.get("dependencies") or n.get("scripts")):
        out.append(f"  scripts: {_short(n.get('scripts', []), lim)}; зависимости: {_short(n.get('dependencies', []), lim)}")
    elif n["lang"] == "SQL" and n.get("tables"):
        out.append(f"  таблицы: {_short(n['tables'], lim)}")
    return out


def render(graph: dict, budget: int = 9000) -> str:
    """Карта проекта для промпта: дерево, связи, оглавления файлов. Обрезается по бюджету символов,
    сначала теряя подробности самых мелких файлов."""
    nodes = graph["nodes"]
    lines = [
        f"# Карта проекта «{graph['root']}»" + (f", часть {graph['focus']}" if graph["focus"] else ""),
        f"Своих файлов: {graph['files']} ({', '.join(f'{k} {v}' for k, v in graph['languages'].items())}).",
    ]
    if graph["vendor"]:
        lines.append(f"Библиотеки (не разбираются): {_short(graph['vendor'], 8)}.")
    if graph["edges"]:
        lines.append("\n## Связи")
        lines += [f"- {a} → {b} ({kind})" for a, b, kind in graph["edges"][:60]]
    cross = graph["cross"]
    notes = []
    if cross["broken_anchors"]:
        notes.append(f"ссылки #якорь на несуществующие id: {_short(cross['broken_anchors'], 10)}")
    if cross["used_not_styled"]:
        notes.append(f"классы в HTML без стилей (часто — Bootstrap или JS): {_short(cross['used_not_styled'], 15)}")
    if cross["styled_not_used"]:
        notes.append(f"стили для классов, которых нет в HTML (рендерит JS?): {_short(cross['styled_not_used'], 15)}")
    if cross["js_hooks"]:
        notes.append(f"JS ищет на странице: {_short(cross['js_hooks'], 15)}")
    if notes:
        lines.append("\n## Перекрёстные связи")
        lines += [f"- {n}" for n in notes]
    lines.append("\n## Файлы")
    # Крупные файлы — подробнее: в них обычно главное
    # Данные и документация — после кода: про устройство проекта они говорят меньше
    order = sorted(nodes, key=lambda k: (nodes[k]["lang"] in ("JSON", "Markdown", "YAML", "TOML"), -nodes[k]["bytes"], k))
    body = []
    for key in order:
        body.append("\n".join(file_summary(key, nodes[key])))
    text = "\n".join(lines)
    for part in body:
        if len(text) + len(part) > budget:
            rest = len(body) - body.index(part)
            text += f"\n…и ещё {rest} файлов: их оглавление — инструментом project_file."
            break
        text += "\n" + part
    return text


def outline(root: str | Path, path: str) -> str:
    """Подробное оглавление одного файла — дешевле, чем читать его целиком."""
    root = Path(root).resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file() or SECRET.match(target.name):
        return "Такого файла в проекте нет."
    text = _read(target)
    info = {"lang": LANG.get(target.suffix.lower(), target.suffix), "lines": text.count("\n") + 1, "bytes": len(text.encode())}
    if _is_minified(target, text):
        info["skipped"] = "минифицирован — это библиотека"
    else:
        info |= parse_file(target, text)
    return "\n".join(file_summary(path, info, detail=True))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit("Использование: graph.py <папка> [--focus часть] [--file путь] [--json] [--budget N]")
    opts = {args[i]: args[i + 1] for i in range(1, len(args) - 1) if args[i].startswith("--") and not args[i + 1].startswith("--")}
    if "--file" in opts:
        print(outline(args[0], opts["--file"]))
    else:
        g = build(args[0], opts.get("--focus", ""))
        print(json.dumps(g, ensure_ascii=False, indent=1) if "--json" in args else render(g, int(opts.get("--budget", 9000))))
