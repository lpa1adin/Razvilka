"""Тренажёр архитектуры: проверка ответов. Выбор и схему проверяет код сразу; описание своими словами —
Claude в отдельной чистой сессии без инструментов, а засчитанность каждого пункта ещё раз проверяет код."""

import re

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.agent import claude
from app.modules.arch import diagrams
from app.modules.arch.exercises import BY_SLUG, EXERCISES
from app.modules.arch.models import ArchAttempt
from app.modules.auth.models import User
from app.modules.jobs.queue import enqueue

KIND_LABEL = {"choice": "выбор", "diagram": "схема", "describe": "своими словами"}


class ArchError(Exception):
    pass


# ---------- Для ученика: без ответов, пока он не ответил сам ----------


def public(ex: dict) -> dict:
    out = {k: ex[k] for k in ("slug", "level", "kind", "project", "title", "question")}
    out["materials"] = [{k: m[k] for k in ("file", "lang", "path", "project", "license", "url", "text", "note")} for m in ex["materials"]]
    if ex["kind"] == "choice":
        out |= {"options": ex["options"], "multiple": ex["multiple"]}
    if ex["kind"] == "diagram":
        kinds = {n["id"]: n["kind"] for n in diagrams.build(ex["diagram"]["parser"], ex["materials"][ex["diagram"]["material"]]["text"])["nodes"]}
        out["nodes"] = [{"id": n, "kind": kinds.get(n, diagrams.kind_of(n))} for n in ex["nodes"]]
    if ex["kind"] == "describe":
        out["keypoints_count"] = len(ex["keypoints"])
    return out


def reveal(ex: dict) -> dict:
    """После ответа: правильный вариант, объяснение и схема, построенная генератором по самому файлу."""
    m = ex["materials"][ex["diagram"]["material"]]
    out = {"explanation": ex["explanation"], "auto_diagram": diagrams.build(ex["diagram"]["parser"], m["text"]), "auto_from": m["path"]}
    if ex["kind"] == "choice":
        out["correct"] = ex["correct"]
    if ex["kind"] == "diagram":
        out["expected"] = ex["expected"]
    if ex["kind"] == "describe":
        out["keypoints"] = ex["keypoints"]
    return out


def attempts(db: Session, user: User, slug: str | None = None) -> list[ArchAttempt]:
    q = select(ArchAttempt).where(ArchAttempt.user_id == user.id)
    if slug:
        q = q.where(ArchAttempt.slug == slug)
    return list(db.scalars(q.order_by(ArchAttempt.id.desc())))


def counted_attempt(db: Session, user: User, slug: str) -> ArchAttempt | None:
    return db.scalar(select(ArchAttempt).where(ArchAttempt.user_id == user.id, ArchAttempt.slug == slug, ArchAttempt.counted.is_(True)))


def next_slug(slug: str) -> str | None:
    slugs = [e["slug"] for e in EXERCISES]
    i = slugs.index(slug)
    return slugs[i + 1] if i + 1 < len(slugs) else None


def overview(db: Session, user: User) -> list[dict]:
    mine = attempts(db, user)
    out = []
    for n, ex in enumerate(EXERCISES, 1):
        first = next((a for a in mine if a.slug == ex["slug"] and a.counted), None)
        out.append({
            "n": n, "slug": ex["slug"], "title": ex["title"], "level": ex["level"], "kind": ex["kind"], "project": ex["project"],
            "attempts": sum(a.slug == ex["slug"] for a in mine),
            # Балл задания — первый ответ (засчитанный); пока его оценивают — None
            "score": first.score if first else None, "done": first is not None,
        })
    return out


# ---------- Проверка ----------


def grade_choice(ex: dict, picked: list[str]) -> tuple[float, dict]:
    right, picked_set = set(ex["correct"]), set(picked)
    if not ex["multiple"]:
        ok = picked_set == right
        return (5.0 if ok else 0.0), {"correct": ok, "picked": picked}
    hits, wrong = len(right & picked_set), len(picked_set - right)
    score = max(0.0, (hits - wrong) / len(right)) * 5
    return round(score, 2), {"correct": picked_set == right, "picked": picked, "hits": hits, "wrong": wrong}


def grade_diagram(ex: dict, edges: list[list[str]]) -> tuple[float, dict]:
    nodes = set(ex["nodes"])
    drawn = {(a, b) for a, b in edges if a in nodes and b in nodes and a != b}
    expected = {tuple(e) for e in ex["expected"]}
    matched = drawn & expected
    reversed_ = {(a, b) for a, b in drawn if (b, a) in expected and (a, b) not in expected}
    extra = drawn - expected - reversed_
    missed = expected - matched - {(b, a) for a, b in reversed_}
    # Перепутанное направление — половина балла; лишняя стрелка снимает половину: схема должна быть точной, а не «всё со всем»
    raw = (len(matched) + 0.5 * len(reversed_) - 0.5 * len(extra)) / len(expected)
    score = round(max(0.0, min(1.0, raw)) * 5, 2)
    return score, {
        "matched": sorted(map(list, matched)), "reversed": sorted(map(list, reversed_)),
        "extra": sorted(map(list, extra)), "missed": sorted(map(list, missed)),
    }


def submit(db: Session, user: User, slug: str, answer: dict) -> ArchAttempt:
    ex = BY_SLUG.get(slug)
    if ex is None:
        raise ArchError("Задание не найдено")
    first = counted_attempt(db, user, slug)
    if first is not None and ex["kind"] == "choice":
        # После ответа виден правильный вариант — «перевыбрать» значило бы просто переписать ключ
        raise ArchError("Ответ уже засчитан. Разбор открыт, переходите к следующему заданию.")
    if first is not None and first.status == "evaluating":
        raise ArchError("Первый ответ ещё оценивается — дождитесь результата")
    if ex["kind"] == "choice":
        picked = [p for p in answer.get("picked", []) if p in {o["id"] for o in ex["options"]}]
        if not picked:
            raise ArchError("Выберите вариант")
        score, result = grade_choice(ex, picked)
        attempt = ArchAttempt(user_id=user.id, slug=slug, answer={"picked": picked}, result=result, score=score, status="done")
    elif ex["kind"] == "diagram":
        edges = [e for e in answer.get("edges", []) if isinstance(e, list) and len(e) == 2][:80]
        if not edges:
            raise ArchError("Нарисуйте хотя бы одну связь")
        score, result = grade_diagram(ex, edges)
        attempt = ArchAttempt(user_id=user.id, slug=slug, answer={"edges": edges}, result=result, score=score, status="done")
    else:
        text = str(answer.get("text", "")).strip()
        if len(text) < 80:
            raise ArchError("Опишите подробнее — хотя бы несколько предложений")
        if len(text) > 6000:
            raise ArchError("Слишком длинно: уложитесь в 6000 символов")
        if not claude.configured():
            raise ArchError("Оценка описаний недоступна: Claude не подключён. Задания с выбором и схемами работают без него.")
        attempt = ArchAttempt(user_id=user.id, slug=slug, answer={"text": text}, status="evaluating")
    attempt.counted = first is None
    db.add(attempt)
    db.commit()
    if attempt.status == "evaluating":
        enqueue(db, "review", {"type": "arch_describe", "attempt_id": str(attempt.id)})
    return attempt


# ---------- «Своими словами»: оценивает Claude ----------


class PointCheck(BaseModel):
    id: str
    covered: bool
    quote: str = Field("", description="Дословная цитата из ответа ученика, где раскрыт пункт; пусто, если не раскрыт")
    comment: str = Field("", description="Что верно или чего не хватает, одно предложение")


class DescribeReport(BaseModel):
    points: list[PointCheck]
    errors: list[str] = Field(default_factory=list, description="Фактические ошибки в ответе")
    feedback: str = Field(description="2–3 предложения ученику: что сильнее всего, что добавить")


SYSTEM = """\
Ты — независимый проверяющий тренажёра архитектуры. Ученик описал архитектуру фрагмента реального проекта своими
словами. Проверь, какие ключевые пункты он раскрыл. Пункт раскрыт, только если в ответе есть по сути то же
утверждение (другими словами можно); упоминания термина мимоходом мало. Для раскрытого пункта приведи дословную
цитату из ответа. Отдельно перечисли фактические ошибки. Не хвали. Всё на русском. Ответ — строго по JSON-схеме."""


def _norm(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


def evaluate_describe(db: Session, attempt_id: int) -> dict:
    attempt = db.get(ArchAttempt, attempt_id)
    if attempt is None or attempt.status != "evaluating":
        return {"skipped": True}
    # Если оценка не удалась, первая попытка не «сгорает»: засчитанной станет следующая

    ex = BY_SLUG[attempt.slug]
    materials = "\n\n".join(f"=== {m['path']} ({m['project']}) ===\n{m['text'][:8000]}" for m in ex["materials"])
    points = "\n".join(f"- {k['id']}: {k['text']}" for k in ex["keypoints"])
    prompt = f"Вопрос: {ex['question']}\n\nМатериал:\n{materials}\n\nКлючевые пункты:\n{points}\n\nОтвет ученика:\n{attempt.answer['text']}"
    try:
        report = claude.run_structured("arch", prompt, SYSTEM, DescribeReport, effort="medium", max_turns=3, library=False)
    except claude.AgentUnavailable as exc:
        attempt.status, attempt.error, attempt.counted = "failed", str(exc)[:500], False
        db.commit()
        return {"error": str(exc)}
    text = _norm(attempt.answer["text"])
    known = {k["id"]: k for k in ex["keypoints"]}
    checked = []
    for k in ex["keypoints"]:
        got = next((p for p in report.points if p.id == k["id"]), None)
        quote_ok = bool(got and got.quote and _norm(got.quote) in text)
        # Пункт засчитан, только если цитата действительно из ответа — модель не может «додумать» за ученика
        checked.append({"id": k["id"], "text": k["text"], "covered": bool(got and got.covered and quote_ok),
                        "quote": got.quote if got and quote_ok else "", "comment": got.comment if got else ""})
    covered = sum(p["covered"] for p in checked)
    attempt.result = {"points": checked, "errors": report.errors, "feedback": report.feedback, "covered": covered, "total": len(known)}
    attempt.score = round(covered / len(known) * 5, 2)
    attempt.status = "done"
    db.commit()
    return {"score": attempt.score}


def attempt_out(attempt: ArchAttempt) -> dict:
    ex = BY_SLUG[attempt.slug]
    out = {"id": attempt.id, "slug": attempt.slug, "status": attempt.status, "answer": attempt.answer, "result": attempt.result,
           "score": attempt.score, "counted": attempt.counted, "error": attempt.error, "created_at": attempt.created_at}
    if attempt.status == "done":
        out["reveal"] = reveal(ex)
    return out
