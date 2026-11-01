"""Задания тренажёра архитектуры (BRIEF §5.4) на реальных открытых проектах.

Материалы — настоящие файлы, закреплённые на коммите, с лицензией (лежат в materials/ без изменений).
Порядок — по нарастающей: выбрать из вариантов → собрать схему → описать своими словами (оценивает Claude).
Правильные ответы сверены с самими файлами; для схем Sock Shop связи взяты из описания архитектуры проекта,
потому что в его compose они не объявлены — и это часть урока.
"""

import re
from pathlib import Path

MATERIALS = Path(__file__).with_name("materials")

FA = {"project": "fastapi/full-stack-fastapi-template", "license": "MIT",
      "base": "https://github.com/fastapi/full-stack-fastapi-template/blob/f4bcfaba7c85be3c6332cc74a20819f586dcdbc6/"}
GC = {"project": "GoogleCloudPlatform/microservices-demo (Online Boutique)", "license": "Apache-2.0",
      "base": "https://github.com/GoogleCloudPlatform/microservices-demo/blob/c7cb6d5bfd6ea3aed768634ebbcb98cb7a523712/"}
SS = {"project": "microservices-demo/microservices-demo (Sock Shop)", "license": "Apache-2.0",
      "base": "https://github.com/microservices-demo/microservices-demo/blob/9dff06fae4981921caec6a62393a6ebfce4b3e3f/"}
RZ = {"project": "Развилка (эта платформа)", "license": "проект владельца", "base": ""}


def _strip_comments(text: str) -> str:
    """Комментарии своего проекта («модульный монолит + воркеры (ADR-001)») прямо называют ответ — убираем их.
    Чужие файлы не трогаем: они под лицензией и показываются как есть."""
    lines = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        lines.append(re.sub(r"\s+#\s.*$", "", line))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def material(file: str, origin: dict, path: str, lang: str, strip_comments: bool = False) -> dict:
    text = (MATERIALS / file).read_text(encoding="utf-8")
    return {
        "file": file, "lang": lang, "path": path, "project": origin["project"], "license": origin["license"],
        "url": origin["base"] + path if origin["base"] else "",
        "text": _strip_comments(text) if strip_comments else text,
        "note": "Комментарии автора убраны: они подсказывали ответ." if strip_comments else "",
    }


def _ex():
    return [
        # ---------- 1–5: выбрать из вариантов ----------
        {
            "slug": "razvilka-compose-type", "level": "high", "kind": "choice", "project": RZ["project"],
            "title": "Какая архитектура у самой Развилки",
            "question": "Посмотрите на docker-compose.yml платформы. Какой это тип архитектуры?",
            "materials": [material("razvilka-compose.yml", RZ, "docker-compose.yml", "yaml", strip_comments=True)],
            "multiple": False,
            "options": [
                {"id": "a", "text": "Микросервисы: у каждого сервиса своя база и свой код"},
                {"id": "b", "text": "Модульный монолит и фоновые воркеры: один код бэкенда, разные команды запуска, общая база"},
                {"id": "c", "text": "Serverless: функции запускаются по событию"},
                {"id": "d", "text": "Классический монолит: всё в одном процессе"},
            ],
            "correct": ["b"],
            "explanation": "api, agent-worker, collector и runner собираются из одного `./backend` через якорь `x-backend` и "
                           "отличаются только `command`. Postgres один на всех. Это модульный монолит с воркерами (ADR-001). "
                           "Сети `public` и `internal` разделяют доступ в интернет, но не код.",
            "diagram": {"material": 0, "parser": "compose"},
        },
        {
            "slug": "fastapi-compose-services", "level": "high", "kind": "choice", "project": FA["project"],
            "title": "Смежные сервисы full-stack шаблона FastAPI",
            "question": "Какие смежные сервисы есть в этом compose.yml? Отметьте все, что действительно объявлены.",
            "materials": [material("fastapi-compose.yml", FA, "compose.yml", "yaml")],
            "multiple": True,
            "options": [
                {"id": "a", "text": "Обратный прокси Traefik: маршрутизирует запросы по Host из labels"},
                {"id": "b", "text": "Adminer: веб-интерфейс к базе"},
                {"id": "c", "text": "Redis как кэш"},
                {"id": "d", "text": "PostgreSQL как основная база"},
                {"id": "e", "text": "RabbitMQ как брокер сообщений"},
                {"id": "f", "text": "Prometheus для метрик"},
            ],
            "correct": ["a", "b", "d"],
            "explanation": "Объявлены proxy (`traefik:v3.7`, читает labels через docker.sock), db (`postgres:18` с healthcheck), "
                           "adminer и backend. backend ждёт `db` по `condition: service_healthy` и ходит в неё по `DATABASE_URL …@db:5432`. "
                           "Кэша, брокера и мониторинга в этом файле нет: фронтенд и окружение для разработки добавляет `compose.override.yml`.",
            "diagram": {"material": 0, "parser": "compose"},
        },
        {
            "slug": "boutique-k8s-discovery", "level": "high", "kind": "choice", "project": GC["project"],
            "title": "Как frontend Online Boutique находит другие сервисы",
            "question": "Это манифест Kubernetes для frontend. Как он находит остальные сервисы и что это говорит об архитектуре?",
            "materials": [material("boutique-frontend.yaml", GC, "kubernetes-manifests/frontend.yaml", "yaml")],
            "multiple": False,
            "options": [
                {"id": "a", "text": "Ходит в общую базу, где лежат данные всех частей. Это монолит"},
                {"id": "b", "text": "Получает адреса сервисов из переменных окружения (`cartservice:7070`…). Это DNS-имена Service в Kubernetes: микросервисы, каждый за своим Service"},
                {"id": "c", "text": "Публикует запросы в брокер, сервисы их забирают"},
                {"id": "d", "text": "Импортирует код других сервисов как библиотеки"},
            ],
            "correct": ["b"],
            "explanation": "В `env` перечислены `PRODUCT_CATALOG_SERVICE_ADDR=productcatalogservice:3550`, `CART_SERVICE_ADDR=cartservice:7070` и "
                           "ещё шесть адресов. Kubernetes разрешает имя Service в его IP. Наружу frontend выставлен отдельным Service "
                           "типа LoadBalancer (`frontend-external`). Протокол между сервисами — gRPC: общий контракт лежит в `protos/demo.proto`.",
            "diagram": {"material": 0, "parser": "k8s"},
        },
        {
            "slug": "fastapi-models-relations", "level": "low", "kind": "choice", "project": FA["project"],
            "title": "Классы моделей: как связаны UserBase, UserCreate и User",
            "question": "Как связаны классы `UserBase`, `UserCreate` и `User`?",
            "materials": [material("fastapi-models.py", FA, "backend/app/models.py", "python")],
            "multiple": False,
            "options": [
                {"id": "a", "text": "Наследование: общие поля в UserBase, UserCreate добавляет password, User — таблица (`table=True`) с id и hashed_password"},
                {"id": "b", "text": "Композиция: User содержит поле типа UserCreate"},
                {"id": "c", "text": "Никак: поля просто продублированы"},
                {"id": "d", "text": "Миксины: User собран из нескольких независимых классов-примесей"},
            ],
            "correct": ["a"],
            "explanation": "`class UserCreate(UserBase)` и `class User(UserBase, table=True)` наследуют общие поля (email, is_active…). "
                           "Таблицей БД становится только User. `UserUpdate` намеренно НЕ наследует UserBase: при обновлении все поля "
                           "необязательные. Композиция в файле тоже есть, но в другом месте: `User.items: list[Item]` через Relationship.",
            "diagram": {"material": 0, "parser": "python"},
        },
        {
            "slug": "boutique-email-pattern", "level": "low", "kind": "choice", "project": GC["project"],
            "title": "Какой приём реализуют классы почтового сервиса",
            "question": "Что делают вместе `BaseEmailService`, `EmailService`, `DummyEmailService` и функция `start(dummy_mode)`?",
            "materials": [material("boutique-email_server.py", GC, "src/emailservice/email_server.py", "python")],
            "multiple": False,
            "options": [
                {"id": "a", "text": "Одиночка (Singleton): единственный экземпляр сервиса на процесс"},
                {"id": "b", "text": "Наследование и подмена реализации: базовый класс даёт health-check, две реализации одного gRPC-интерфейса, start выбирает реализацию по флагу (стратегия)"},
                {"id": "c", "text": "Наблюдатель (Observer): сервисы подписываются на события заказа"},
                {"id": "d", "text": "Декоратор: DummyEmailService оборачивает EmailService"},
            ],
            "correct": ["b"],
            "explanation": "`BaseEmailService(demo_pb2_grpc.EmailServiceServicer)` реализует Check/Watch. От него наследуют две реализации "
                           "`SendOrderConfirmation`: настоящая (`EmailService`, пока бросает «not implemented») и заглушка (`DummyEmailService`). "
                           "`start(dummy_mode)` выбирает, какую зарегистрировать на gRPC-сервере. Это замена реализации через общий интерфейс.",
            "diagram": {"material": 0, "parser": "python"},
        },
        # ---------- 6–8: собрать схему ----------
        {
            "slug": "sockshop-diagram", "level": "high", "kind": "diagram", "project": SS["project"],
            "title": "Схема связей Sock Shop",
            "question": "Соедините сервисы Sock Shop стрелками «кто к кому обращается»: от входа до баз и брокера. "
                        "Подсказка: в compose связи почти не объявлены — опирайтесь на имена и роли.",
            "materials": [material("sockshop-compose.yml", SS, "deploy/docker-compose/docker-compose.yml", "yaml")],
            "nodes": ["edge-router", "front-end", "catalogue", "catalogue-db", "carts", "carts-db", "orders", "orders-db",
                      "user", "user-db", "payment", "shipping", "rabbitmq", "queue-master"],
            "expected": [
                ["edge-router", "front-end"], ["front-end", "catalogue"], ["front-end", "carts"], ["front-end", "orders"], ["front-end", "user"],
                ["catalogue", "catalogue-db"], ["carts", "carts-db"], ["orders", "orders-db"], ["user", "user-db"],
                ["orders", "payment"], ["orders", "shipping"], ["orders", "carts"], ["orders", "user"],
                ["shipping", "rabbitmq"], ["queue-master", "rabbitmq"],
            ],
            "explanation": "Вход — edge-router, дальше front-end, который вызывает catalogue, carts, orders и user. orders собирает заказ: "
                           "берёт корзину и данные пользователя, списывает оплату (payment) и передаёт доставку (shipping). shipping публикует "
                           "задачу в rabbitmq, queue-master её забирает. У каждого сервиса данных своя база — признак микросервисов. "
                           "Авто-схема по compose найдёт только `user → user-db` (из MONGO_HOST): связи здесь живут в коде и конфигурации образов, а не в compose.",
            "diagram": {"material": 0, "parser": "compose"},
        },
        {
            "slug": "razvilka-dataflow", "level": "high", "kind": "diagram", "project": RZ["project"],
            "title": "Поток данных Развилки: depends_on ≠ связи",
            "question": "Соедините сервисы Развилки стрелками «кто к кому обращается за данными», а не «кто кого ждёт при старте».",
            "materials": [material("razvilka-compose.yml", RZ, "docker-compose.yml", "yaml", strip_comments=True)],
            "nodes": ["web", "api", "agent-worker", "collector", "runner", "postgres", "prometheus", "grafana"],
            "expected": [
                ["web", "api"], ["api", "postgres"], ["agent-worker", "postgres"], ["collector", "postgres"], ["runner", "postgres"],
                ["prometheus", "api"], ["prometheus", "agent-worker"], ["prometheus", "collector"], ["prometheus", "runner"],
                ["grafana", "prometheus"],
            ],
            "explanation": "Воркеры объявляют `depends_on: api`, но это только порядок запуска: api накатывает миграции. За задачами они "
                           "ходят напрямую в Postgres (очередь в таблице jobs, ADR-004). Prometheus сам опрашивает /metrics сервисов, "
                           "его цели описаны в ops/prometheus/prometheus.yml, а не в compose. Grafana читает Prometheus. "
                           "Сравните со схемой, которую построил генератор: она показывает только depends_on.",
            "diagram": {"material": 0, "parser": "compose"},
        },
        {
            "slug": "fastapi-crud-calls", "level": "low", "kind": "diagram", "project": FA["project"],
            "title": "Граф вызовов crud.py",
            "question": "Нарисуйте граф вызовов: какая функция crud.py какие функции вызывает. Учитывайте только узлы на схеме.",
            "materials": [material("fastapi-crud.py", FA, "backend/app/crud.py", "python")],
            "nodes": ["create_user", "update_user", "get_user_by_email", "authenticate", "create_item", "get_password_hash", "verify_password", "select"],
            "expected": [
                ["create_user", "get_password_hash"], ["update_user", "get_password_hash"], ["get_user_by_email", "select"],
                ["authenticate", "get_user_by_email"], ["authenticate", "verify_password"],
            ],
            "explanation": "authenticate сначала ищет пользователя (get_user_by_email → select), потом проверяет пароль. Если пользователя нет, "
                           "verify_password всё равно вызывается с DUMMY_HASH, чтобы время ответа не выдавало, существует ли email "
                           "(защита от timing attack). create_item ничего из списка не вызывает: только Item.model_validate и сессию.",
            "diagram": {"material": 0, "parser": "python-calls"},
        },
        # ---------- 9–10: описать своими словами (оценивает Claude) ----------
        {
            "slug": "boutique-describe", "level": "high", "kind": "describe", "project": GC["project"],
            "title": "Опишите архитектуру Online Boutique",
            "question": "По дереву репозитория и манифесту frontend опишите своими словами: тип архитектуры, как общаются сервисы, "
                        "на каких языках они написаны и почему это возможно, где выполняется каждая часть, что выигрывают и чем платят.",
            "materials": [
                material("boutique-tree.txt", GC, "src", "text"),
                material("boutique-frontend.yaml", GC, "kubernetes-manifests/frontend.yaml", "yaml"),
            ],
            "keypoints": [
                {"id": "k1", "text": "Микросервисы: отдельный сервис на каждую папку src и отдельный манифест"},
                {"id": "k2", "text": "Общение по gRPC через общий контракт protos/demo.proto"},
                {"id": "k3", "text": "Адреса сервисов передаются переменными окружения и разрешаются как DNS-имена Service в Kubernetes"},
                {"id": "k4", "text": "Разные языки (Go, C#, Java, Node.js, Python) — возможны благодаря контракту gRPC"},
                {"id": "k5", "text": "Развёртывание в Kubernetes: Deployment и Service на сервис, вход снаружи через LoadBalancer"},
                {"id": "k6", "text": "Цена и выигрыш: независимое развёртывание и масштабирование против сложности эксплуатации, сети и наблюдаемости"},
            ],
            "explanation": "Online Boutique — учебный эталон микросервисов Google: 11 с лишним сервисов на пяти языках, gRPC, Kubernetes, трассировка.",
            "diagram": {"material": 1, "parser": "k8s"},
        },
        {
            "slug": "fastapi-describe-lowlevel", "level": "low", "kind": "describe", "project": FA["project"],
            "title": "Опишите нижний уровень: модели и CRUD",
            "question": "По models.py и crud.py опишите: парадигму, классы и связи между ними, как устроены функции CRUD и их граф "
                        "вызовов, к какому слою относится crud.py и зачем он отдельно.",
            "materials": [
                material("fastapi-models.py", FA, "backend/app/models.py", "python"),
                material("fastapi-crud.py", FA, "backend/app/crud.py", "python"),
            ],
            "keypoints": [
                {"id": "k1", "text": "Модели — декларативные классы SQLModel с наследованием: UserBase → UserCreate и User(table=True)"},
                {"id": "k2", "text": "Связь один-ко-многим между User и Item через Relationship (User.items ↔ Item.owner)"},
                {"id": "k3", "text": "crud.py — процедурный модуль функций без состояния; сессия передаётся явно, аргументы только по имени (*)"},
                {"id": "k4", "text": "crud — слой доступа к данным между API и моделями (репозиторий / DAO)"},
                {"id": "k5", "text": "Граф вызовов: authenticate → get_user_by_email и verify_password; create_user и update_user → get_password_hash"},
                {"id": "k6", "text": "Защита от timing attack: verify_password с DUMMY_HASH, когда пользователь не найден"},
            ],
            "explanation": "Такая раскладка — модели отдельно, доступ к данным отдельно, маршруты отдельно — и есть «слои» нижнего уровня.",
            "diagram": {"material": 1, "parser": "python-calls"},
        },
    ]


EXERCISES = _ex()
BY_SLUG = {e["slug"]: e for e in EXERCISES}
