# Развилка — памятка для Claude

Локальная учебная платформа владельца: FastAPI + Postgres + React, Docker Compose. Подробности — в `README.md`
и `docs/`, но целиком их не читать: сначала эта памятка и команды ниже.

## Главное правило: лимит подписки

Claude Code и `agent-worker` платформы тратят один 5-часовой лимит. Платное — всё, что идёт через очереди
`agent`, `review`, `chat`: генерация, ревью и исправление эталонов, дописывание вопросов, наставник.
Без явного согласия владельца в его сообщении платное не запускать; `agent-worker` держать остановленным
и останавливать сразу после разрешённой задачи (`docker compose stop agent-worker`).
Автопроверка заданий (`runner`) бесплатна.

## С чего начинать (все команды из этой папки)

```bash
docker compose exec -T api python -m app.cli status          # очередь, заявки, задания с замечаниями, банки вопросов
docker compose exec -T api python -m app.cli map             # список курсов
docker compose exec -T api python -m app.cli map 5           # карта курса с адресами ячеек
docker compose exec -T api python -m app.cli show 5/2.3/4    # одна ячейка
docker compose exec -T api python -m app.cli set task:28/tests < файл   # запись в черновик + бесплатная автопроверка
```

Содержимое курсов лежит в базе, а не в файлах. «Измени блок 4 урока 2.3 курса 5» = `map` → `show` → `set`;
не выгружать курс целиком и не писать разовых скриптов. Адреса:

| Адрес | Что это |
|---|---|
| `5` | курс; `5/2.3` — урок 3 модуля 2 (`/title`, `/goal`); `5/2.3/4` — блок 4 (`/why` у теории) |
| `task:28` | задание: `/title` `/statement` `/tests` `/sql_setup` `/hints/N` `/starter/<файл>` `/solution/<файл>` |
| `quiz:5` | банк вопросов; `quiz:5/12` — вопрос целиком в JSON |
| `fragment:123` | статья библиотеки, только чтение; `/text` — целиком |

Адрес блока практики или теста продолжается полями того, на что он ссылается: `5/2.3/4/tests` = `task:28/tests`.
`set` пишет только в черновик (опубликованная версия не меняется, ADR-013); публикует владелец в Мастерской.

## Где что в коде

Код искать через скилл `project-graph` (`python3 backend/app/modules/projectmap/graph.py . --focus …`,
оглавление файла — `--file …`), читать нужные строки, а не файлы целиком.

`backend/app/modules/<модуль>/` — обычно `models.py`, `schemas.py`, `service.py`, `router.py`:

| Модуль | За что отвечает |
|---|---|
| `courses` | курсы и уроки, версии-снимки в JSONB, прогресс |
| `practice` | задания, версии, автопроверка (`runner.py`, `harness/`) |
| `quiz` | банки вопросов и тесты |
| `library` | источники теории и статьи (`parsers.py`) |
| `generation` | заявки генерации, конвейер по шагам (`pipeline.py`), пауза |
| `review` | Ревьюер: правила, ревью кода и эталонов, исправление эталона |
| `assess`, `arch`, `paths` | Оценщик сдач, тренажёр архитектуры, путь «напиши заново сам» |
| `mentor`, `agent` | наставник и обёртка над Claude Agent SDK |
| `jobs` | очередь задач в Postgres (`queue.py`), платные виды — `PAID_KINDS` |
| `system` | `status.py` (сводка), `cells.py` (адреса `map`/`show`/`set`) |
| `projectmap` | граф проекта без модели |
| `auth`, `users`, `workshop` | вход и роли, пользователи, Мастерская |

Фронтенд: `frontend/src/pages/<раздел>/` (страницы; Мастерская — `pages/workshop/`), `features/`, `components/`.
Решения по архитектуре: оглавление в начале `docs/DECISIONS.md`, читать только нужный ADR.

## После правок кода

- Код зашит в образ, а не примонтирован: `docker compose up -d --build api runner` (без `agent-worker`).
  Для быстрой пробы одного файла — `docker compose cp backend/app/… api:/srv/app/…`.
- Тесты: `docker compose exec -T api python -m pytest -q` (отдельная тестовая база).
- Коммит и `git push` в `origin`. Секреты — только в `.env`, хук `.githooks/pre-commit` их не пропускает.
- Общение и интерфейс — на русском. Файлы владельца не удалять и не перемещать без подтверждения.
