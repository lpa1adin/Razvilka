"""Начальные данные этапа 6: рубрика из BRIEF §5.6, эталоны из §3.2 и два практикума.

Формулировки эталонных ответов — короткие выжимки из решений самой платформы (docs/DECISIONS.md) и
общеизвестных свойств технологий; теорией они не являются — ученик видит их только после оценки.
"""

RUBRIC = [
    {"id": "R1", "block": "reasoning", "title": "Названы реальные альтернативы", "description": "Не «а можно было бы иначе», а конкретные варианты, уместные в этом контексте."},
    {"id": "R2", "block": "reasoning", "title": "Компромиссы описаны верно", "description": "Что выигрываем и чем платим у выбранного варианта и у альтернатив; без фактических ошибок."},
    {"id": "R3", "block": "reasoning", "title": "Выбор подходит к контексту проекта", "description": "Масштаб, нагрузка, команда, сроки из условия; выбор не взят «на вырост» без причины."},
    {"id": "R4", "block": "reasoning", "title": "Опора на источники и эталоны; указано, когда пересмотреть", "description": "Ссылка на документацию или эталонный проект и конкретное условие пересмотра."},
    {"id": "R5", "block": "implementation", "title": "Код соответствует заявленному решению", "description": "Сказал «PostgreSQL + миграции» — в коде Postgres и миграции, а не SQLite и ручной SQL."},
    {"id": "R6", "block": "implementation", "title": "Решение реализовано правильно", "description": "Тесты проходят, у Ревьюера нет blocker по этому месту."},
    {"id": "R7", "block": "implementation", "title": "Заявленные свойства видны в коде", "description": "Сказал «модули разделены» — нет импортов через слои; сказал «транзакции» — они есть."},
]

REFERENCES = [
    {"name": "Развилка (эта платформа)", "url": "docs/DECISIONS.md",
     "about": "Модульный монолит + воркеры на очереди в PostgreSQL (SKIP LOCKED), миграции Alembic, Docker Compose. "
              "Сборщик источников: белый список, расписание раз в неделю, git-копии репозиториев, лицензия проверяется кодом."},
    {"name": "fastapi/full-stack-fastapi-template", "url": "https://github.com/fastapi/full-stack-fastapi-template",
     "about": "Full-stack монолит: FastAPI, SQLModel, PostgreSQL, миграции Alembic, Docker Compose, тесты и CI."},
    {"name": "gothinkster/realworld", "url": "https://github.com/gothinkster/realworld",
     "about": "Одно и то же приложение во множестве реализаций: видно, как разные стеки решают одинаковые задачи."},
    {"name": "GoogleCloudPlatform/microservices-demo", "url": "https://github.com/GoogleCloudPlatform/microservices-demo",
     "about": "Online Boutique: 11 микросервисов на gRPC, у каждого свои данные, наблюдаемость, Kubernetes."},
    {"name": "donnemartin/system-design-primer", "url": "https://github.com/donnemartin/system-design-primer",
     "about": "Разборы системного дизайна: SQL vs NoSQL, кэши, очереди, масштабирование, компромиссы CAP."},
]

STORAGE_TESTS = '''import importlib


def test_add_and_list():
    """add_hike возвращает новый id, list_hikes отдаёт добавленные записи"""
    import storage
    a = storage.add_hike("Фишт", 54.5)
    b = storage.add_hike("Оштен", 32)
    assert a != b, "add_hike вернул одинаковые id для разных записей"
    names = [h["name"] for h in storage.list_hikes()]
    assert "Фишт" in names and "Оштен" in names, f"В журнале нет добавленных походов: {names}"


def test_total_km():
    """total_km складывает километры всех походов"""
    import storage
    before = storage.total_km()
    storage.add_hike("Контрольный", 10)
    assert abs(storage.total_km() - before - 10) < 1e-6, "total_km не учёл новый поход"


def test_survives_restart():
    """Записи переживают перезапуск программы"""
    import storage
    storage.add_hike("После перезапуска", 1)
    importlib.reload(storage)
    assert any(h["name"] == "После перезапуска" for h in storage.list_hikes()), "После перезапуска запись пропала — данные не сохраняются"
'''

ASSIGNMENTS = [
    {
        "slug": "hike-journal-storage",
        "title": "Практикум: журнал походов — где хранить данные",
        "kind": "python",
        "statement": (
            "Походному клубу нужен журнал походов. Напишите модуль **`storage.py`**:\n\n"
            "- `add_hike(name: str, km: float) -> int` — добавляет поход и возвращает его id;\n"
            "- `list_hikes() -> list[dict]` — все походы по порядку добавления, ключи `id`, `name`, `km`;\n"
            "- `total_km() -> float` — сумма километров.\n\n"
            "Данные должны **переживать перезапуск** программы. Контекст: около 1000 записей в год, один сервер, "
            "иногда два администратора вносят записи одновременно.\n\n"
            "Перед сдачей ответьте на развилки: Оценщик сверит ответы с кодом. Сдайте папку проекта или zip."
        ),
        "forks": [
            {"id": "storage", "question": "Где хранить журнал и почему?",
             "context": "Около 1000 записей в год, один сервер, иногда два администратора пишут одновременно.",
             "reference": "Для одного сервера и такой нагрузки хватает SQLite: один файл, транзакции, ноль администрирования. "
                          "PostgreSQL оправдан, когда пишут несколько процессов по сети, нужна репликация или Postgres уже есть в "
                          "инфраструктуре (как в Развилке, ADR-003). JSON-файл без блокировок теряет записи при одновременной записи. "
                          "Главное — выбор должен совпадать с кодом."},
            {"id": "schema", "question": "Как менять структуру данных со временем (новое поле, переименование)?",
             "context": "Через полгода клуб захочет хранить дату похода и сложность.",
             "reference": "Миграции: Alembic для SQLAlchemy или нумерованные SQL-скрипты и таблица версии схемы (PRAGMA user_version "
                          "для SQLite). Ручной ALTER на рабочей базе — нет: изменение не повторить и не откатить."},
        ],
        "tests": STORAGE_TESTS,
        "references": ["Развилка (эта платформа)", "fastapi/full-stack-fastapi-template", "donnemartin/system-design-primer"],
        "threshold": 3.0,
    },
    {
        "slug": "own-aggregator",
        "title": "Практикум: свой агрегатор",
        "kind": "any",
        "statement": (
            "Финальный проект курса по архитектуре (BRIEF §5.8). Спроектируйте и напишите сборщик материалов из открытых "
            "источников: он по расписанию забирает статьи с 2–3 сайтов из белого списка, хранит их с источником и "
            "лицензией и отдаёт поиск.\n\n"
            "Сдайте код и ответьте на развилки. Оценщик сравнит решения с устройством сборщика Развилки и эталонами."
        ),
        "forks": [
            {"id": "storage", "question": "Как хранить собранные материалы и искать по ним?",
             "reference": "Развилка: PostgreSQL с полнотекстовым поиском (tsvector, русская морфология) — один сервис вместо отдельного "
                          "поискового движка; Elasticsearch/Meilisearch оправданы при больших объёмах и сложной релевантности."},
            {"id": "schedule", "question": "Как запускать сбор по расписанию и не потерять задачу при сбое?",
             "reference": "Развилка: очередь задач в PostgreSQL (SELECT … FOR UPDATE SKIP LOCKED), воркер-сборщик с пульсом; "
                          "незавершённые задачи возвращаются в очередь при перезапуске. Cron без очереди не переживает сбой посреди импорта."},
            {"id": "boundaries", "question": "Один процесс, модульный монолит или отдельные сервисы?",
             "reference": "Развилка: модульный монолит + воркеры из одного образа (ADR-001). Микросервисы окупаются при нескольких "
                          "командах и разной нагрузке частей; для одного разработчика это цена без выгоды."},
        ],
        "tests": "",
        "references": ["Развилка (эта платформа)", "donnemartin/system-design-primer", "GoogleCloudPlatform/microservices-demo"],
        "threshold": 3.0,
    },
]
