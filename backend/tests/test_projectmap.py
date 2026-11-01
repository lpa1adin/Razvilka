"""Граф проекта: без Claude находит структуру и связи, не трогает библиотеки и секреты."""

from app.modules.projectmap.graph import build, outline, render


def make_project(root):
    (root / "styles" / "vendor").mkdir(parents=True)
    (root / "js").mkdir()
    (root / "index.html").write_text(
        '<!doctype html><html><head><title>Фишт</title><link rel="stylesheet" href="styles/style.css">'
        '<link rel="stylesheet" href="styles/vendor/bootstrap.min.css"></head><body>'
        '<header id="top" class="site-header"><nav><a href="#about">О нас</a><a href="#nope">?</a></nav></header>'
        '<main><section id="about" class="section"><h1>Поход</h1><h2>Маршрут</h2>'
        '<article class="day-card">День 1</article></section></main><script src="js/main.js"></script></body></html>'
    )
    (root / "styles" / "style.css").write_text(
        ".site-header{display:flex}.day-card{display:grid;gap:clamp(8px,2vw,16px)}.ghost{color:red}"
        "@media (min-width:768px){.section{padding:40px}}"
    )
    (root / "styles" / "vendor" / "bootstrap.min.css").write_text(".btn{}" * 100)
    (root / "js" / "main.js").write_text(
        "import { fmt } from './util.js'\nconst ROUTES = []\nfunction renderRoutes(list) {\n"
        "  document.querySelector('.day-card').addEventListener('click', () => {})\n}\n"
    )
    (root / "js" / "util.js").write_text("export const fmt = (n) => n.toFixed(1)\n")
    (root / "app.py").write_text("import os\nclass Route:\n    name: str\n    def __init__(self):\n        self.km = 0\ndef load(path) -> list:\n    return []\n")
    (root / ".env").write_text("SECRET=1")


def test_graph_finds_structure_and_links(tmp_path):
    make_project(tmp_path)
    g = build(tmp_path)
    assert set(g["nodes"]) == {"index.html", "styles/style.css", "js/main.js", "js/util.js", "app.py"}  # без .env и vendor
    assert "styles/vendor/bootstrap.min.css" in g["vendor"]
    assert ("index.html", "styles/style.css", "стили") in g["edges"]
    assert ("index.html", "js/main.js", "скрипт") in g["edges"]
    assert ("js/main.js", "js/util.js", "импорт") in g["edges"]
    html = g["nodes"]["index.html"]
    assert html["landmarks"][:2] == ["header#top.site-header", "nav"]
    assert (1, "Поход") in html["headings"]
    assert g["cross"]["broken_anchors"] == ["nope"]
    assert "ghost" in g["cross"]["styled_not_used"]
    css = g["nodes"]["styles/style.css"]
    assert css["media"] == ["(min-width:768px)"] and "clamp(" in css["features"]
    js = g["nodes"]["js/main.js"]
    assert "renderRoutes(list)" in js["functions"] and js["constants"] == ["ROUTES"] and ".day-card" in js["dom"]
    py = g["nodes"]["app.py"]
    assert py["classes"][0]["fields"] == ["name: str", "km"]
    assert py["functions"][0].startswith("load(path) -> list")


def test_render_is_compact_and_outline_detailed(tmp_path):
    make_project(tmp_path)
    text = render(build(tmp_path), budget=3000)
    assert len(text) <= 3200 and "## Связи" in text and "SECRET" not in text
    assert "renderRoutes(list)" in outline(tmp_path, "js/main.js")
    assert outline(tmp_path, ".env") == "Такого файла в проекте нет."
    assert outline(tmp_path, "../etc/passwd") == "Такого файла в проекте нет."
