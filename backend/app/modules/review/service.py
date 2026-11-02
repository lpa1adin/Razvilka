"""Независимый Ревьюер (BRIEF §5.9, docs/REVIEWER.md).

Независимость — технически, а не обещанием:
- каждая проверка — отдельный вызов Claude без истории; на входе только условие, код и правила;
- у Ревьюера нет инструментов: код приходит в задании с номерами строк, ни файлов, ни сети, ни библиотеки;
- он не знает, кто автор и зачем: имени, переписки с наставником и прошлых ревью в задании нет;
- ответ — строгий JSON, а вердикт считает код по серьёзности замечаний, а не модель.
"""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.agent import claude
from app.modules.auth.models import User
from app.modules.jobs.queue import enqueue, has_pending
from app.modules.practice import service as practice
from app.modules.practice.models import Task
from app.modules.practice.runner import spec_hash
from app.modules.practice.schemas import TaskSpec
from app.modules.review.models import Review, ReviewKind, ReviewRuleSet, ReviewStatus
from app.modules.review.schemas import Finding, ModelReport, ReviewCard, ReviewOut, Rule, RulesOut

DEFAULT_RULES = Path(__file__).with_name("default_rules.md")
BLOCKING = ("blocker", "major")
MAX_INLINE = 120_000  # больше — это уже проект, а не задание (этап 6)


class ReviewError(Exception):
    pass


# ---------- Правила ----------


def parse_rules(markdown: str) -> list[Rule]:
    """Правила из REVIEWER.md: «### SEC — безопасность» и строки «- **SEC-02** текст»."""
    rules, group = [], ""
    for block in re.split(r"\n(?=### |- \*\*)", markdown.split("## Правила", 1)[-1].split("## Источники", 1)[0]):
        block = block.strip()
        if block.startswith("### "):
            group = block[4:].splitlines()[0].strip()
        elif m := re.match(r"- \*\*([A-Z]+-\d+)\*\* (.+)", block, re.S):
            text, _, source = re.sub(r"\s+", " ", m.group(2)).strip().partition(" Источник: ")
            rules.append(Rule(id=m.group(1), group=group, text=text.strip(), source=source.strip().rstrip(".")))
    return rules


def active_rules(db: Session) -> ReviewRuleSet:
    current = db.scalar(select(ReviewRuleSet).order_by(ReviewRuleSet.version.desc()).limit(1))
    if current is None:
        # Первая версия — из REVIEWER.md, дальше правила правит админ в Мастерской
        current = ReviewRuleSet(version=1, rules=[r.model_dump() for r in parse_rules(DEFAULT_RULES.read_text())], note="Из docs/REVIEWER.md")
        db.add(current)
        db.commit()
    return current


def save_rules(db: Session, admin: User, rules: list[Rule], note: str) -> ReviewRuleSet:
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ReviewError("id правил повторяются")
    if not any(r.enabled for r in rules):
        raise ReviewError("Включите хотя бы одно правило")
    last = active_rules(db)
    if [r.model_dump() for r in rules] == last.rules:
        return last
    new = ReviewRuleSet(version=last.version + 1, rules=[r.model_dump() for r in rules], note=note, created_by=admin.id)
    db.add(new)
    db.commit()
    return new


def rules_out(db: Session, rs: ReviewRuleSet) -> RulesOut:
    author = db.get(User, rs.created_by) if rs.created_by else None
    return RulesOut(version=rs.version, rules=[Rule.model_validate(r) for r in rs.rules], note=rs.note, created_at=rs.created_at,
                    author=author.login if author else None)


def rules_markdown(rules: list[dict]) -> str:
    out, group = [], None
    for r in rules:
        if not r.get("enabled", True):
            continue
        if r["group"] != group:
            group = r["group"]
            out.append(f"\n### {group}")
        out.append(f"- **{r['id']}** {r['text']}" + (f" Источник: {r['source']}." if r.get("source") else ""))
    return "\n".join(out).strip()


PRINCIPLES = """\
Ты — независимый Ревьюер кода учебной платформы «Развилка». Ты проверяешь код по правилам ниже и ничего больше.

Принципы:
1. Доказательства, а не мнения. Каждое замечание — файл и номер строки из входа, нарушенное правило и конкретный
   сценарий: какие входные данные или действие приведут к ошибке, уязвимости или ухудшению. Без сценария — не замечание.
2. Без похвалы и смягчений. Нет замечаний — пустой список.
3. Не выходи за рамки: только то, что требует задача и правила. Вкусовщину без правила не пиши.
4. Ты не исправляешь код: fix_hint — направление, без готового решения.
5. Серьёзность: blocker — не выполнен критерий задачи или есть уязвимость; major — ошибка в реалистичном сценарии
   или практика, которой нельзя учиться; minor — читаемость и мелочи.
6. Один дефект — одно замечание, по самому точному правилу. Не больше 15 замечаний: сначала самые серьёзные.
Всё на русском. Ответ — строго по JSON-схеме."""

KIND_NOTE = {
    ReviewKind.learner: "Это решение ученика в учебной песочнице. Оценивай как обычный код, без скидок на уровень.",
    ReviewKind.project: (
        "Это проект ученика, сданный на проверку. Проверяй дефекты кода по правилам; оценку решений делает "
        "другой проверяющий — не повторяй его работу."
    ),
    ReviewKind.reference: (
        "Это ЭТАЛОННОЕ решение задания: по нему будут учиться. Эталон не должен учить плохому — "
        "любая плохая практика здесь как минимум major. Файл tests.* (у SQL — checks.txt) — автотесты задания: проверь по TEST-02, что они "
        "проверяют каждый критерий, названный в условии, и упадут на неверном решении. Граничные случаи вне условия — minor."
    ),
}


SECOND_LABEL = "второй взгляд"


def build_prompt(review: Review, rules: list[dict]) -> tuple[str, str]:
    system = f"{PRINCIPLES}\n\n{KIND_NOTE[review.kind]}\n\nПравила:\n{rules_markdown(rules)}"
    parts = [f"Задача: {review.title}", "Условие:", review.statement or "—", "", "Код (номер строки | текст):"]
    for name, text in review.files.items():
        if not text.strip():
            parts.append(f"\n=== {name} === (пустой файл)")
            continue
        numbered = "\n".join(f"{i:>4} | {line}" for i, line in enumerate(text.splitlines(), 1))
        parts.append(f"\n=== {name} ===\n{numbered}")
    return system, "\n".join(parts)


# ---------- Проверка ----------


def _validate(review: Review, report: ModelReport, rules: list[dict]) -> tuple[list[dict], list[dict]]:
    """Модель может ошибиться в адресе — проверяем: правило существует и включено, файл и строка есть во входе."""
    known = {r["id"]: r for r in rules if r.get("enabled", True)}
    kept, dropped = [], []
    for f in report.findings:
        lines = review.files.get(f.file)
        reason = None
        if f.rule not in known:
            reason = f"нет такого правила {f.rule}"
        elif lines is None:
            reason = f"нет такого файла {f.file}"
        if reason:
            dropped.append({**f.model_dump(), "reason": reason})
            continue
        count = len(lines.splitlines())
        kept.append(Finding(
            rule=f.rule, rule_text=known[f.rule]["text"], severity=f.severity, file=f.file,
            line=f.line if 1 <= f.line <= max(count, 1) else None,
            problem=f.problem, scenario=f.scenario, fix_hint=f.fix_hint,
            # Источник берём из правила (проверен вручную), а не со слов модели
            source=known[f.rule].get("source") or f.source,
        ).model_dump())
    order = {"blocker": 0, "major": 1, "minor": 2}
    kept.sort(key=lambda x: (order[x["severity"]], x["file"], x["line"] or 0))
    return kept, dropped


def run(db: Session, review_id: int) -> dict:
    review = db.get(Review, review_id)
    if review is None or review.status not in (ReviewStatus.queued, ReviewStatus.running):
        return {"skipped": True}
    rules = db.scalar(select(ReviewRuleSet).where(ReviewRuleSet.version == review.rules_version)).rules
    review.status = ReviewStatus.running
    db.commit()
    system, prompt = build_prompt(review, rules)
    usage: dict[str, int] = {}
    second: dict | None = None
    try:
        report = claude.run_structured(
            "review", prompt, system, ModelReport, effort="high", max_turns=4, library=False, on_usage=usage.update,
        )
        findings, dropped = _validate(review, report, rules)
        # Эталон чистый, только если его отдельно пропустила и другая модель: у неё другие слепые пятна
        if review.kind is ReviewKind.reference and not any(f["severity"] in BLOCKING for f in findings):
            second = {"model": settings.reviewer_second_model}
            report2 = claude.run_structured(
                "review", prompt, system, ModelReport, effort="high", max_turns=4, library=False,
                on_usage=second.update, model=settings.reviewer_second_model,
            )
            more, dropped2 = _validate(review, report2, rules)
            seen = {(f["rule"], f["file"], f["line"]) for f in findings}
            findings += [{**f, "by": SECOND_LABEL} for f in more if (f["rule"], f["file"], f["line"]) not in seen]
            dropped += dropped2
            order = {"blocker": 0, "major": 1, "minor": 2}
            findings.sort(key=lambda x: (order[x["severity"]], x["file"], x["line"] or 0))
    except claude.AgentUnavailable as exc:
        review.status = ReviewStatus.failed
        review.error = str(exc)
        review.finished_at = datetime.now(UTC)
        db.commit()
        return {"error": str(exc)}
    review.findings, review.dropped = findings, dropped
    review.verdict = "changes_requested" if any(f["severity"] in BLOCKING for f in review.findings) else "pass"
    review.tokens = {**usage, "second": second} if second is not None else usage
    review.status = ReviewStatus.done
    review.finished_at = datetime.now(UTC)
    db.commit()
    return {"verdict": review.verdict, "findings": len(review.findings)}


def _new(db: Session, kind: ReviewKind, user: User, title: str, statement: str, files: dict, **extra) -> Review:
    if not claude.configured():
        raise ReviewError("Ревьюер недоступен: Claude не подключён (нет CLAUDE_CODE_OAUTH_TOKEN).")
    if sum(len(t) for t in files.values()) > MAX_INLINE:
        raise ReviewError("Слишком много кода для одного ревью")
    if not any(t.strip() for t in files.values()):
        raise ReviewError("Код пустой — проверять нечего")
    review = Review(
        kind=kind, requested_by=user.id, title=title, statement=statement, files=files,
        rules_version=active_rules(db).version, findings=[], dropped=[], tokens={}, **extra,
    )
    db.add(review)
    db.commit()
    return review


def project_review(db: Session, user: User, title: str, statement: str, files: dict) -> Review:
    """Ревью сданного проекта: запускается конвейером сдачи сразу, без очереди (он сам в очереди review)."""
    review = _new(db, ReviewKind.project, user, title, statement, files)
    run(db, review.id)
    db.refresh(review)
    return review


def request_learner(db: Session, user: User, task: Task, files: dict) -> Review:
    """«Ревью кода» в песочнице. Ревьюер получает условие и код, но не эталон, не подсказки и не имя ученика."""
    learner = practice.for_learner(db, user, task, None)
    spec = TaskSpec.model_validate(practice.get_version(db, task.id, learner.version).spec)
    allowed = set(spec.starter)
    files = {name: code for name, code in files.items() if name in allowed}
    if db.scalar(select(Review.id).where(
        Review.requested_by == user.id, Review.task_id == task.id, Review.status.in_([ReviewStatus.queued, ReviewStatus.running]),
    )):
        raise ReviewError("Ревью этого задания уже идёт — дождитесь отчёта")
    review = _new(db, ReviewKind.learner, user, spec.title, spec.statement, files, task_id=task.id, task_version=learner.version)
    enqueue(db, "review", {"type": "review", "review_id": str(review.id)})
    return review


def reference_review(db: Session, task: Task) -> Review | None:
    """Последнее ревью эталона именно этой редакции задания (по хэшу спецификации)."""
    version = practice.editing_version(db, task)
    return db.scalar(
        select(Review).where(Review.kind == ReviewKind.reference, Review.task_id == task.id, Review.spec_hash == spec_hash(version.spec))
        .order_by(Review.id.desc()).limit(1)
    )


def is_stale(review: Review) -> bool:
    """«В работе» дольше двух пределов вызова Claude — значит, ревью оборвалось вместе с воркером."""
    return datetime.now(UTC) - review.created_at >= timedelta(seconds=settings.agent_timeout_seconds * 2)


def request_reference(db: Session, admin: User, task: Task, enqueue_job: bool = True) -> Review:
    version = practice.editing_version(db, task)
    spec = TaskSpec.model_validate(version.spec)
    current = reference_review(db, task)
    if current and current.status in (ReviewStatus.queued, ReviewStatus.running):
        if not is_stale(current):
            return current
        # Ревью, запущенное внутри задачи генерации, обрывается вместе с воркером и само не завершится
        current.status = ReviewStatus.failed
        current.error = "Ревью прервано (перезапуск воркера) — запущено заново"
        current.finished_at = datetime.now(UTC)
        db.commit()
    files = {name: code for name, code in spec.solution.items() if code.strip()} or spec.solution
    if spec.kind == "sql":
        files = {"schema.sql": spec.sql_setup, **files}
        if spec.sql_checks:
            # У SQL-заданий автотесты — список проверок; Ревьюер видит их как файл, чтобы судить по TEST-02
            files["checks.txt"] = "\n\n".join(
                f"-- Проверка {i}: {c.name} ({'результат совпадает с эталоном' if c.type == 'same_result' else 'запрос после решения вернёт истину'}"
                f"{', порядок строк важен' if c.order_matters else ''})\n{c.sql.strip()}" + (f"\n-- Сообщение ученику: {c.message}" if c.message else "")
                for i, c in enumerate(spec.sql_checks, 1)
            )
    elif spec.tests.strip():
        # Тесты тоже на ревью (TEST-02): слабые тесты пропустят и неверный эталон
        files = {**files, f"tests.{'js' if spec.kind == 'web' else 'py'}": spec.tests}
    review = _new(
        db, ReviewKind.reference, admin, spec.title, spec.statement, files,
        task_id=task.id, task_version=version.number, spec_hash=spec_hash(version.spec),
    )
    if enqueue_job and not has_pending(db, "review", review_id=str(review.id)):
        enqueue(db, "review", {"type": "review", "review_id": str(review.id)})
    return review


def reference_problems(db: Session, task: Task) -> list[str]:
    """Для проверок публикации: эталон этой редакции проверен Ревьюером и не учит плохому."""
    review = reference_review(db, task)
    if review is None:
        return ["Ревьюер не проверял эталон этой редакции: нажмите «Ревью эталона»."]
    if review.status in (ReviewStatus.queued, ReviewStatus.running):
        return ["Ревью эталона ещё идёт."]
    if review.status is ReviewStatus.failed:
        return [f"Ревью эталона не удалось: {review.error}. Запустите ещё раз."]
    if review.verdict == "changes_requested" and not review.accepted_by:
        serious = sum(f["severity"] in BLOCKING for f in review.findings)
        return [f"У эталона замечания Ревьюера ({serious} серьёзных): исправьте или примите их с пояснением."]
    return []


def accept(db: Session, admin: User, review: Review, note: str) -> None:
    if review.kind is not ReviewKind.reference or review.status is not ReviewStatus.done:
        raise ReviewError("Принять можно только готовое ревью эталона")
    review.accepted_by = admin.id
    review.accepted_note = note
    db.commit()


# ---------- Ответы и экспорт ----------


def counts(review: Review) -> dict[str, int]:
    c = {"blocker": 0, "major": 0, "minor": 0}
    for f in review.findings:
        c[f["severity"]] += 1
    return c


def _slug(db: Session, review: Review) -> str | None:
    task = db.get(Task, review.task_id) if review.task_id else None
    return task.slug if task else None


def to_out(db: Session, review: Review) -> ReviewOut:
    return ReviewOut(
        id=review.id, kind=review.kind, status=review.status, title=review.title, task_slug=_slug(db, review),
        task_version=review.task_version, rules_version=review.rules_version, verdict=review.verdict,
        findings=[Finding.model_validate(f) for f in review.findings], counts=counts(review), dropped=len(review.dropped),
        files=review.files, error=review.error, accepted=bool(review.accepted_by), accepted_note=review.accepted_note,
        second_opinion=bool((review.tokens or {}).get("second")),
        created_at=review.created_at, finished_at=review.finished_at,
    )


def to_card(db: Session, review: Review) -> ReviewCard:
    return ReviewCard(
        id=review.id, kind=review.kind, status=review.status, title=review.title, task_slug=_slug(db, review),
        verdict=review.verdict, counts=counts(review), created_at=review.created_at,
    )


def agent_markdown(rs: ReviewRuleSet) -> str:
    """Тот же Ревьюер как агент Claude Code (`.claude/agents/reviewer.md`) — для проектов вне платформы."""
    return f"""---
name: reviewer
description: Независимый ревьюер кода по правилам «Развилки» (v{rs.version}). Использовать после изменения кода, когда нужен строгий отчёт о дефектах в JSON — без правок кода. Запускать с перечнем файлов или изменений и условием задачи.
tools: Read, Grep, Glob
---

{PRINCIPLES}

Как работать в Claude Code:
- Читай только переданные файлы или изменения (git diff) и то, что нужно для проверки конкретного места.
- Ничего не правь, не запускай и не ходи в сеть. Переписку и объяснения автора не учитывай.
- Номера строк — по текущему содержимому файла.
- Вердикт: changes_requested, если есть хотя бы одно замечание blocker или major, иначе pass.

Ответ — только JSON, без текста вокруг:
```json
{{
  "verdict": "pass | changes_requested",
  "findings": [
    {{"rule": "SEC-02", "severity": "blocker | major | minor", "file": "src/api/users.py", "line": 42,
      "problem": "…", "scenario": "…", "fix_hint": "…", "source": "…"}}
  ]
}}
```

## Правила (версия {rs.version})
{rules_markdown(rs.rules)}

Источники правил: OWASP Top 10 и Cheat Sheet Series, MDN Accessibility, WCAG 2.2, PEP 8,
Google Engineering Practices (Code Review), R. Martin «Clean Architecture».
"""
