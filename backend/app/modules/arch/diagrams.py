"""Авто-диаграммы тренажёра (BRIEF §5.4): схема строится кодом, без Claude, по тому, что реально написано в файле.

Ученик сначала рисует сам, потом сравнивает со сгенерированной схемой. Генератор честно показывает только
объявленное: depends_on в compose — это порядок запуска, а не поток данных, и схема это видно отличает.
Формат: {"nodes": [{id, label, kind, detail}], "edges": [{from, to, kind}]}.
"""

import ast
import re

import yaml

KINDS = [
    ("db", re.compile(r"postgres|mysql|mariadb|mongo|-db$|_db$|^db$|sqlite|cassandra", re.I)),
    ("cache", re.compile(r"redis|memcached", re.I)),
    ("broker", re.compile(r"rabbitmq|kafka|nats|queue-master", re.I)),
    ("proxy", re.compile(r"traefik|nginx|edge-router|haproxy|envoy|caddy", re.I)),
    ("monitoring", re.compile(r"prometheus|grafana|jaeger|zipkin|loki|alertmanager", re.I)),
]


def kind_of(name: str, image: str = "") -> str:
    for kind, pattern in KINDS:
        if pattern.search(name) or pattern.search(image or ""):
            return kind
    return "app"


def _mentions(text: str, names: set[str], self_name: str) -> set[str]:
    """Какие сервисы упомянуты в строке как хост: «db:5432», «http://catalogue», «-h edge-router»."""
    found = set()
    for name in names:
        if name != self_name and re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text):
            found.add(name)
    return found


def from_compose(text: str) -> dict:
    data = yaml.safe_load(text) or {}
    services = data.get("services") or {}
    names = set(services)
    nodes, edges = [], set()
    for name, svc in services.items():
        svc = svc or {}
        image = str(svc.get("image") or "")
        build = svc.get("build")
        detail = image or (f"сборка: {build.get('context')}" if isinstance(build, dict) else f"сборка: {build}" if build else "")
        command = svc.get("command")
        if isinstance(command, list):
            command = " ".join(map(str, command))
        if command:
            detail += f" · команда: {str(command)[:60]}"
        nodes.append({"id": name, "label": name, "kind": kind_of(name, image), "detail": detail.strip(" ·")})
        depends = svc.get("depends_on") or []
        for target in (depends if isinstance(depends, list) else list(depends)):
            edges.add((name, target, "depends_on"))
        for link in svc.get("links") or []:
            edges.add((name, str(link).split(":")[0], "links"))
        env = svc.get("environment") or {}
        values = env.values() if isinstance(env, dict) else [str(e).split("=", 1)[-1] for e in env]
        for value in values:
            for target in _mentions(str(value), names, name):
                edges.add((name, target, "env"))
        for target in _mentions(str(command or ""), names, name):
            edges.add((name, target, "command"))
    return {"nodes": nodes, "edges": [{"from": a, "to": b, "kind": k} for a, b, k in sorted(edges) if b in names]}


def from_k8s(text: str) -> dict:
    """Deployment/Service → узлы; адреса других сервисов в env («cartservice:7070») → связи."""
    docs = [d for d in yaml.safe_load_all(text) if isinstance(d, dict)]
    deployments = [d for d in docs if d.get("kind") in ("Deployment", "StatefulSet")]
    nodes, edges = [], []
    for dep in deployments:
        name = dep["metadata"]["name"]
        containers = dep.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        ports = [str(p.get("containerPort")) for c in containers for p in c.get("ports", [])]
        nodes.append({"id": name, "label": name, "kind": kind_of(name), "detail": f"{dep['kind']}, порт {', '.join(ports)}"})
        for c in containers:
            for env in c.get("env", []):
                value = str(env.get("value", ""))
                if m := re.fullmatch(r"([a-z][a-z0-9-]*):(\d+)", value):
                    target = m.group(1)
                    if target not in {n["id"] for n in nodes}:
                        nodes.append({"id": target, "label": target, "kind": kind_of(target), "detail": f"по адресу из {env['name']}"})
                    edges.append({"from": name, "to": target, "kind": "env"})
    for svc in (d for d in docs if d.get("kind") == "Service"):
        spec = svc.get("spec", {})
        if spec.get("type") == "LoadBalancer":
            ext = svc["metadata"]["name"]
            nodes.append({"id": ext, "label": ext, "kind": "proxy", "detail": "Service LoadBalancer — вход снаружи"})
            target = spec.get("selector", {}).get("app")
            if target:
                edges.append({"from": ext, "to": target, "kind": "service"})
    return {"nodes": nodes, "edges": edges}


def from_python(text: str, functions_only: bool = False) -> dict:
    """Классы: наследование и поля-ссылки на другие классы модуля. Функции: кто кого вызывает."""
    tree = ast.parse(text)
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    imported = {a.asname or a.name for n in tree.body if isinstance(n, ast.ImportFrom) for a in n.names}
    nodes, edges = [], set()

    if not functions_only:
        for name, cls in classes.items():
            fields = [t.target.id for t in cls.body if isinstance(t, ast.AnnAssign) and isinstance(t.target, ast.Name)]
            methods = [m.name for m in cls.body if isinstance(m, ast.FunctionDef)]
            detail = (f"поля: {', '.join(fields[:6])}" if fields else "") + (f" · методы: {', '.join(methods[:6])}" if methods else "")
            nodes.append({"id": name, "label": name, "kind": "class", "detail": detail.strip(" ·")})
            for base in cls.bases:
                base_name = ast.unparse(base).split(".")[-1]
                if base_name in classes:
                    edges.add((name, base_name, "inherits"))
            for item in cls.body:
                if isinstance(item, ast.AnnAssign):
                    for ref in re.findall(r"\b[A-Z]\w+", ast.unparse(item.annotation)):
                        if ref in classes and ref != name:
                            edges.add((name, ref, "has"))

    def calls(fn) -> set[str]:
        out = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                target = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None
                if target and (target in funcs or target in imported and target[0].islower()):
                    out.add(target)
        return out

    used_external = set()
    for name, fn in funcs.items():
        args = ", ".join(a.arg for a in fn.args.args + fn.args.kwonlyargs)
        nodes.append({"id": name, "label": f"{name}()", "kind": "function", "detail": f"аргументы: {args}" if args else ""})
        for target in calls(fn) - {name}:
            edges.add((name, target, "calls"))
            if target not in funcs:
                used_external.add(target)
    for ext in sorted(used_external):
        nodes.append({"id": ext, "label": f"{ext}()", "kind": "external", "detail": "импортирована из другого модуля"})
    return {"nodes": nodes, "edges": [{"from": a, "to": b, "kind": k} for a, b, k in sorted(edges)]}


PARSERS = {"compose": from_compose, "k8s": from_k8s, "python": from_python, "python-calls": lambda t: from_python(t, functions_only=True)}


def build(parser: str, text: str) -> dict:
    return PARSERS[parser](text)
