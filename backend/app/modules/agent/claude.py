"""Обращения к Claude через Agent SDK (ADR-007). Работает только в agent-worker.

Две формы:
- run_structured — задача с ответом строго по схеме (план, черновик урока). Проект агент видит через граф
  (скилл project-graph и инструменты project_map/project_file) и читает точечно (Read в папке проекта);
  библиотеку — через свои инструменты; писать и запускать команды не может;
- stream_reply — ответ наставника в чате, текст отдаётся кусками по мере генерации.

Токены тратятся только внутри этих двух вызовов: CLI Claude запускается на одно обращение и завершается.
Расход каждого обращения пишется в метрики (razvilka_agent_tokens_total).

Тесты подменяют обе функции, поэтому сервисы вызывают их через модуль: `claude.run_structured(...)`.
"""

import asyncio
import logging
import os
import re
import time
from collections.abc import Callable
from typing import TypeVar

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    HookMatcher,
    ResultMessage,
    StreamEvent,
    ToolUseBlock,
    query,
)
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from pathlib import Path

from app.core.metrics import AGENT_RUNS, AGENT_SECONDS, AGENT_TOKENS
from app.modules.agent.tools import LIBRARY_TOOLS, PROJECT_TOOLS, library_server, project_server

log = logging.getLogger("agent")
M = TypeVar("M", bound=BaseModel)

# Файлы, которые агенту читать нельзя даже внутри проекта: там бывают пароли и ключи
SECRET_NAME = re.compile(r"^(\.env.*|.*\.(pem|key|p12|pfx)|id_rsa.*|id_ed25519.*|credentials.*|secrets?\..*)$", re.I)
# Библиотеки не читаем: это чужой код и тысячи строк впустую
VENDOR = re.compile(r"(^|/)(vendor|node_modules|dist|build)(/|$)|\.min\.", re.I)
PLUGIN_DIR = str(Path(__file__).resolve().parent / "plugin")
# CLI не должен ходить в сеть ни за чем, кроме ответа модели: без телеметрии, автообновлений и подсказок
QUIET_ENV = {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1"}


class AgentUnavailable(Exception):
    """Claude не ответил. Текст — для человека: его видит админ в Мастерской или пользователь в чате."""


def configured() -> bool:
    return bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY"))


def _human_error(result: ResultMessage) -> str:
    status = result.api_error_status
    if status == 429:
        return "Исчерпан лимит подписки Claude. Попробуйте позже."
    if status in (401, 403):
        return "Claude отклонил токен. Обновите CLAUDE_CODE_OAUTH_TOKEN в .env (claude setup-token)."
    if status and status >= 500:
        return "Сервис Claude временно недоступен. Попробуйте ещё раз через пару минут."
    if result.subtype == "error_max_turns":
        return "Claude не уложился в отведённое число шагов. Сузьте задачу или попробуйте ещё раз."
    detail = "; ".join(result.errors or []) or result.result or result.subtype
    return f"Claude завершил работу с ошибкой: {detail[:300]}"


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}


def _path_guard(root: str):
    """Чтение — только внутри папки проекта и не секретов. Проверяется до выполнения инструмента."""
    root = os.path.realpath(root)

    async def guard(input_data, _tool_use_id, _context):
        args = input_data.get("tool_input") or {}
        target = args.get("file_path") or args.get("path") or root
        real = os.path.realpath(os.path.join(root, target))
        pattern = str(args.get("pattern", ""))
        inside = real == root or real.startswith(root + os.sep)
        if not inside or ".." in pattern or pattern.startswith("/") or SECRET_NAME.match(os.path.basename(real)):
            return _deny("Доступ только на чтение файлов этого проекта, без секретов.")
        if VENDOR.search(os.path.relpath(real, root)):
            return _deny("Это библиотека, её читать не нужно: опирайтесь на граф проекта.")
        return {}

    return guard


def _options(system: str, *, cwd: str | None, effort: str, max_turns: int, library: bool = True, **extra) -> ClaudeAgentOptions:
    # Проект агент видит через граф; Read — только за точными строками. Glob не нужен: файлы есть в графе
    builtin = ["Read"] if cwd else []
    hooks = {"PreToolUse": [HookMatcher(matcher="Read", hooks=[_path_guard(cwd)])]} if cwd else None
    servers = {"library": library_server()} if library else {}
    if cwd:
        servers["project"] = project_server(cwd)
    return ClaudeAgentOptions(
        model=settings.agent_model,
        system_prompt=system,
        tools=builtin,  # встроенные инструменты: только чтение; Bash, Write, Edit, WebFetch агенту не даны
        allowed_tools=builtin + (LIBRARY_TOOLS if library else []) + (PROJECT_TOOLS if cwd else []),
        permission_mode="dontAsk",  # всё, что не разрешено явно, отклоняется без вопросов
        mcp_servers=servers,
        setting_sources=[],  # не подхватывать чужие настройки и CLAUDE.md
        # Скилл работы с проектом через граф — только там, где есть проект; в чате список скиллов пуст,
        # чтобы не тратить токены на их описание в каждом сообщении
        plugins=[{"type": "local", "path": PLUGIN_DIR}] if cwd else [],
        skills=["razvilka:project-graph"] if cwd else [],
        env=QUIET_ENV,
        cwd=cwd,
        hooks=hooks,
        effort=effort,
        max_turns=max_turns,
        **extra,
    )


def tokens(usage: dict | None) -> dict[str, int]:
    usage = usage or {}
    return {
        "input": int(usage.get("input_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
        "output": int(usage.get("output_tokens") or 0),
    }


async def _consume(purpose: str, prompt: str, options: ClaudeAgentOptions, on_event: Callable) -> ResultMessage:
    result = None
    stream = query(prompt=prompt, options=options)
    try:
        async for message in stream:
            if isinstance(message, ResultMessage):
                result = message
            else:
                on_event(message)
    finally:
        # Прерванный поток (пауза генерации) закрываем сами — вместе с ним завершается процесс Claude
        await stream.aclose()
    if result is None:
        raise AgentUnavailable("Claude не вернул результат")
    for kind, value in tokens(result.usage).items():
        AGENT_TOKENS.labels(purpose, kind).inc(value)
    if result.is_error:
        raise AgentUnavailable(_human_error(result))
    return result


class Stopped(Exception):
    """Вызов прерван по просьбе админа (пауза генерации)."""


def _run(purpose: str, coro):
    if not configured():
        raise AgentUnavailable("Claude не подключён: добавьте CLAUDE_CODE_OAUTH_TOKEN в .env и перезапустите agent-worker.")
    started = time.monotonic()
    try:
        value = asyncio.run(coro)
    except AgentUnavailable:
        AGENT_RUNS.labels(purpose, "error").inc()
        raise
    except Stopped:
        AGENT_RUNS.labels(purpose, "stopped").inc()
        raise
    except (ClaudeSDKError, OSError) as exc:
        AGENT_RUNS.labels(purpose, "error").inc()
        log.exception("Claude недоступен")
        text = str(exc)
        if limit := re.search(r"hit your (.+?) limit(?: · resets ([^(]+?)\s*(\(UTC\))?)?\s*\(exit", text):
            when = f" Сбросится в {limit.group(2).strip()} UTC." if limit.group(2) else ""
            raise AgentUnavailable(
                f"Исчерпан лимит подписки Claude.{when} Повторите шаг потом — готовые уроки не потеряются."
            ) from exc
        if "auth token" in text.lower():
            raise AgentUnavailable(
                "Claude отклонил токен. Проверьте CLAUDE_CODE_OAUTH_TOKEN в .env (claude setup-token) и перезапустите api и agent-worker."
            ) from exc
        raise AgentUnavailable(f"Не удалось связаться с Claude: {exc}") from exc
    finally:
        AGENT_SECONDS.labels(purpose).observe(time.monotonic() - started)
    AGENT_RUNS.labels(purpose, "ok").inc()
    return value


def describe_tool(block: ToolUseBlock) -> str:
    args = block.input or {}
    if block.name == "Read":
        return f"читает {args.get('file_path', '')}"
    if block.name.endswith("project_map"):
        return "смотрит граф проекта"
    if block.name.endswith("project_file"):
        return f"смотрит оглавление {args.get('path', '')}"
    if block.name == "Skill":
        return "открывает скилл работы с проектом"
    if block.name.endswith("library_search"):
        return f"ищет в библиотеке «{args.get('query', '')}»"
    if block.name.endswith("library_fragment"):
        return f"читает статью №{args.get('id', '')}"
    return block.name


def run_structured(
    purpose: str,
    prompt: str,
    system: str,
    schema: type[M],
    *,
    cwd: str | None = None,
    effort: str = "high",
    max_turns: int = 60,
    on_progress: Callable[[str], None] | None = None,
    on_usage: Callable[[dict[str, int]], None] | None = None,
    library: bool = True,
    should_stop: Callable[[], bool] | None = None,
    model: str | None = None,
) -> M:
    """Задача с ответом по схеме. on_progress получает короткие описания шагов: «читает src/app.js».
    should_stop проверяется на каждом сообщении агента: True — вызов прерывается (Stopped), Claude
    останавливается и дальше лимит не тратит."""

    def on_event(message):
        if should_stop and should_stop():
            raise Stopped()
        if on_progress and isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    on_progress(describe_tool(block))

    options = _options(
        system, cwd=cwd, effort=effort, max_turns=max_turns, library=library,
        output_format={"type": "json_schema", "schema": schema.model_json_schema()},
    )
    if model:
        options.model = model
    result = _run(purpose, _consume(purpose, prompt, options, on_event))
    if on_usage:
        on_usage(tokens(result.usage))
    try:
        return schema.model_validate(result.structured_output)
    except ValidationError as exc:
        raise AgentUnavailable(f"Ответ Claude не подошёл под схему: {exc.errors()[:3]}") from exc


def stream_reply(prompt: str, system: str, on_delta: Callable[[str], None]) -> str:
    """Ответ наставника. Кусочки текста уходят в on_delta сразу, как приходят от модели."""
    parts: list[str] = []

    def on_event(message):
        if isinstance(message, StreamEvent):
            event = message.event
            # Текст между вызовами инструментов (поиском в библиотеке) тоже часть ответа — отделяем абзацем
            if event.get("type") == "message_start" and parts and not parts[-1].endswith("\n"):
                parts.append("\n\n")
                on_delta("\n\n")
            if event.get("type") == "content_block_delta" and event.get("delta", {}).get("type") == "text_delta":
                text = event["delta"]["text"]
                parts.append(text)
                on_delta(text)

    options = _options(system, cwd=None, effort="medium", max_turns=8, include_partial_messages=True)
    result = _run("chat", _consume("chat", prompt, options, on_event))
    return "".join(parts) or (result.result or "")
