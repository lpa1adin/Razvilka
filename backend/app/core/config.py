from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Все настройки приходят из окружения (.env → docker-compose). В коде секретов нет."""

    model_config = SettingsConfigDict(env_prefix="RZ_", extra="ignore")

    database_url: str = "postgresql+psycopg://razvilka:razvilka@postgres:5432/razvilka"
    session_cookie: str = "rz_session"
    session_days: int = 14
    # В локальном запуске по http cookie не может быть Secure; при публикации включить.
    cookie_secure: bool = False

    # Неглубокие копии репозиториев источников (том collector-а)
    sources_cache: str = "/var/cache/razvilka/sources"
    # Как часто сборщик сам обновляет источники
    import_every_days: int = 7

    # Claude (ADR-007): модель наставника и папка с проектами владельца (смонтирована только на чтение).
    # Токен подписки читается самим Agent SDK из CLAUDE_CODE_OAUTH_TOKEN — в настройках его нет.
    # Код и суждения о коде (исправление эталона, Ревьюер, Оценщик) — самая сильная модель
    agent_model: str = "claude-opus-5-5"
    # Текст (план, уроки, вопросы, чат наставника, разбор ответов тренажёра) — модель дешевле
    text_model: str = "claude-sonnet-5-5"
    text_purposes: str = "plan,draft,chat,arch"
    # Второй взгляд на эталоны: другая модель — другие слепые пятна (ADR-025)
    reviewer_second_model: str = "claude-sonnet-5-5"
    # Предел одного вызова Claude: зависший запрос не должен держать очередь часами (самые долгие уроки — ~10 мин)
    agent_timeout_seconds: int = 1200
    projects_root: str = "/projects"
    # Рабочие папки путей «напиши заново сам»: <login>/<путь>. Ученик пишет в них в своём редакторе
    workspace_root: str = "/workspace"
    workspace_host: str = "razvilka/workspace"  # как эта папка называется на компьютере владельца — для подсказки

    # Первые учётки создаются при старте, если их ещё нет (публичной регистрации нет — ADR-011).
    admin_login: str | None = None
    admin_password: str | None = None
    user_login: str | None = None
    user_password: str | None = None


settings = Settings()
