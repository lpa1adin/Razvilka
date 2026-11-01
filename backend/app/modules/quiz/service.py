import random
import re
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.modules.auth.models import User
from app.modules.library.models import Fragment
from app.modules.library.render import render_markdown
from app.modules.quiz.models import (
    AttemptStatus,
    Question,
    QuestionStatus,
    QuestionType,
    QuizAttempt,
    QuizAttemptItem,
    QuizTopic,
)
from app.modules.quiz.schemas import AttemptItemOut, AttemptOut, QuestionIn, SimilarQuestion, TopicCard


# Тест — 5–10 случайных вопросов из банка темы; банк — 20–50, чтобы попытки не повторялись (банк ≈ 4× теста)
TEST_MIN, TEST_MAX = 5, 10
BANK_MIN, BANK_MAX = 20, 50


def test_size(bank: int) -> int:
    return max(TEST_MIN, min(TEST_MAX, round(bank / 4)))


class QuizError(Exception):
    """Ошибка, понятная пользователю."""


# ---------- дубли ----------

_WORD = re.compile(r"[а-яёa-z0-9]+")


def _tokens(text: str) -> set[str]:
    # Короткие слова («в», «и», «на») не помогают отличить вопросы
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2}


def similar_questions(db: Session, topic_id: int, prompt: str, code: str = "", exclude: int | None = None) -> list[SimilarQuestion]:
    """Похожие формулировки в той же теме (коэффициент Жаккара по словам ≥ 0.6)."""
    mine = _tokens(prompt + " " + code)
    result = []
    query = select(Question).where(Question.topic_id == topic_id, Question.status != QuestionStatus.archived)
    for q in db.scalars(query):
        if q.id == exclude:
            continue
        other = _tokens(q.prompt + " " + q.code)
        if mine and other:
            score = len(mine & other) / len(mine | other)
            if score >= 0.6:
                result.append(SimilarQuestion(id=q.id, prompt=q.prompt, similarity=round(score, 2)))
    return sorted(result, key=lambda s: -s.similarity)


def apply(question: Question, data: QuestionIn) -> None:
    for name, value in data.model_dump().items():
        setattr(question, name, value)


# ---------- подбор вопросов (BRIEF §5.2) ----------


def _history(db: Session, user: User, topic: QuizTopic) -> dict[int, tuple[datetime, bool | None]]:
    """По каждому вопросу темы: когда пользователь видел его в последний раз и верно ли ответил тогда."""
    rows = db.execute(
        select(QuizAttemptItem.question_id, QuizAttempt.created_at, QuizAttemptItem.correct)
        .join(QuizAttempt, QuizAttempt.id == QuizAttemptItem.attempt_id)
        .where(QuizAttempt.user_id == user.id, QuizAttempt.topic_id == topic.id, QuizAttemptItem.question_id.is_not(None))
        .order_by(QuizAttempt.created_at)
    ).all()
    return {qid: (seen, correct) for qid, seen, correct in rows}  # последняя запись перезаписывает прошлые


def _spread(questions: list[Question], n: int, rng: random.Random) -> list[Question]:
    """Берёт n вопросов равномерно по подтемам; внутри подтемы — разной сложности."""
    groups: dict[str, list[Question]] = defaultdict(list)
    for q in questions:
        groups[q.subtopic].append(q)
    for items in groups.values():
        rng.shuffle(items)
        # чередуем сложность: 1, 2, 3, 1, 2, 3… — чтобы тест не был целиком из лёгких
        by_level = defaultdict(list)
        for q in items:
            by_level[q.difficulty].append(q)
        items[:] = [q for row in _zip_longest(*[by_level[k] for k in sorted(by_level)]) for q in row if q]
    order = list(groups)
    rng.shuffle(order)
    picked: list[Question] = []
    while len(picked) < n and any(groups.values()):
        for key in order:
            if groups[key] and len(picked) < n:
                picked.append(groups[key].pop(0))
    return picked


def _zip_longest(*lists):
    longest = max((len(x) for x in lists), default=0)
    return [[x[i] if i < len(x) else None for x in lists] for i in range(longest)]


def pick_questions(db: Session, user: User, topic: QuizTopic, n: int, rng: random.Random | None = None) -> list[Question]:
    rng = rng or random.Random()
    pool = list(db.scalars(select(Question).where(Question.topic_id == topic.id, Question.status == QuestionStatus.published)))
    history = _history(db, user, topic)
    unseen = [q for q in pool if q.id not in history]
    picked = _spread(unseen, n, rng)
    if len(picked) < n:
        # Невиданные кончились: добираем то, что было давно, и в первую очередь — где ошибся.
        seen = [q for q in pool if q.id in history]
        rng.shuffle(seen)  # случайный порядок при равных условиях
        seen.sort(key=lambda q: (history[q.id][1] is not False, history[q.id][0]))
        picked += seen[: n - len(picked)]
    rng.shuffle(picked)
    return picked


# ---------- попытки ----------


def _snapshot(question: Question, fragment: Fragment | None, rng: random.Random) -> dict:
    """Вопрос в том виде, как его увидит пользователь: варианты перемешаны, ответ — отдельно."""
    options = dict(question.options)
    if question.type is QuestionType.match:
        right = list(options["right"])
        rng.shuffle(right)
        options = {"left": options["left"], "right": right}
    else:
        items = list(options["items"])
        rng.shuffle(items)
        options = {"items": items}
    return {
        "type": question.type.value,
        "prompt_html": render_markdown(question.prompt),
        "code": question.code,
        "code_lang": question.code_lang,
        "options": options,
        "answer": question.answer,
        "explanation_html": render_markdown(question.explanation) if question.explanation else "",
        "source": {"fragment_id": fragment.id, "title": fragment.title, "source": fragment.source.title} if fragment else None,
    }


def active_attempt(db: Session, user: User, topic: QuizTopic) -> QuizAttempt | None:
    return db.scalar(
        select(QuizAttempt).where(
            QuizAttempt.user_id == user.id, QuizAttempt.topic_id == topic.id, QuizAttempt.status == AttemptStatus.in_progress
        )
    )


def _last_finished(db: Session, user: User, topic: QuizTopic) -> QuizAttempt | None:
    return db.scalar(
        select(QuizAttempt)
        .where(QuizAttempt.user_id == user.id, QuizAttempt.topic_id == topic.id, QuizAttempt.status == AttemptStatus.finished)
        .order_by(QuizAttempt.finished_at.desc())
        .limit(1)
    )


def start(db: Session, user: User, topic: QuizTopic, mistakes_only: bool, rng: random.Random | None = None) -> QuizAttempt:
    rng = rng or random.Random()
    current = active_attempt(db, user, topic)
    if current is not None:
        return current  # прерванный тест продолжается, а не начинается заново

    if mistakes_only:
        last = _last_finished(db, user, topic)
        wrong_ids = [i.question_id for i in last_items(db, last) if i.correct is False and i.question_id] if last else []
        questions = list(db.scalars(select(Question).where(Question.id.in_(wrong_ids), Question.status == QuestionStatus.published)))
        if not questions:
            raise QuizError("В прошлом тесте ошибок нет — повторять нечего")
        rng.shuffle(questions)
    else:
        questions = pick_questions(db, user, topic, topic.size, rng)
        if not questions:
            raise QuizError("В теме пока нет опубликованных вопросов")

    fragments = {f.id: f for f in db.scalars(
        select(Fragment).options(joinedload(Fragment.source)).where(Fragment.id.in_([q.fragment_id for q in questions if q.fragment_id]))
    )}
    attempt = QuizAttempt(user_id=user.id, topic_id=topic.id, mistakes_only=mistakes_only, total=len(questions))
    db.add(attempt)
    db.flush()
    for position, question in enumerate(questions, 1):
        snapshot = _snapshot(question, fragments.get(question.fragment_id), rng)
        db.add(QuizAttemptItem(attempt_id=attempt.id, position=position, question_id=question.id, snapshot=snapshot))
    db.commit()
    return attempt


def last_items(db: Session, attempt: QuizAttempt) -> list[QuizAttemptItem]:
    return list(db.scalars(select(QuizAttemptItem).where(QuizAttemptItem.attempt_id == attempt.id).order_by(QuizAttemptItem.position)))


def _option_ids(snapshot: dict) -> tuple[set[str], set[str]]:
    options = snapshot["options"]
    if snapshot["type"] == QuestionType.match.value:
        return {o["id"] for o in options["left"]}, {o["id"] for o in options["right"]}
    ids = {o["id"] for o in options["items"]}
    return ids, ids


def grade(snapshot: dict, response: dict) -> bool:
    answer, kind = snapshot["answer"], snapshot["type"]
    if kind in (QuestionType.single.value, QuestionType.multiple.value):
        return set(response.get("selected", [])) == set(answer["correct"])
    if kind == QuestionType.order.value:
        return response.get("order") == answer["order"]
    return response.get("pairs") == answer["pairs"]


def save_answer(db: Session, attempt: QuizAttempt, position: int, response: dict) -> None:
    if attempt.status is not AttemptStatus.in_progress:
        raise QuizError("Тест уже завершён — ответы не меняются")
    item = db.scalar(select(QuizAttemptItem).where(QuizAttemptItem.attempt_id == attempt.id, QuizAttemptItem.position == position))
    if item is None:
        raise QuizError("Нет такого вопроса в тесте")
    left, right = _option_ids(item.snapshot)
    used = set(response.get("selected", [])) | set(response.get("order", [])) | set(response.get("pairs", {})) | set(response.get("pairs", {}).values())
    if not used <= left | right:
        raise QuizError("Ответ ссылается на вариант, которого нет в вопросе")
    item.response = response
    item.correct = grade(item.snapshot, response)  # хранится, но показывается только после завершения
    db.commit()


def finish(db: Session, attempt: QuizAttempt) -> None:
    if attempt.status is AttemptStatus.finished:
        return
    items = last_items(db, attempt)
    for item in items:
        if item.response is None:
            item.correct = False  # без ответа — ошибка, чтобы вопрос попал в «Повторить ошибки»
    attempt.score = sum(1 for i in items if i.correct)
    attempt.total = len(items)
    attempt.status = AttemptStatus.finished
    attempt.finished_at = datetime.now(UTC)
    db.commit()


def attempt_out(db: Session, attempt: QuizAttempt) -> AttemptOut:
    topic = db.get(QuizTopic, attempt.topic_id)
    finished = attempt.status is AttemptStatus.finished
    items = []
    for item in last_items(db, attempt):
        s = item.snapshot
        items.append(AttemptItemOut(
            position=item.position, type=s["type"], prompt_html=s["prompt_html"], code=s["code"], code_lang=s["code_lang"],
            options=s["options"], response=item.response,
            correct=item.correct if finished else None,
            answer=s["answer"] if finished else None,  # правильный ответ — только после завершения
            explanation_html=s["explanation_html"] if finished else None,
            source=s["source"] if finished else None,
        ))
    note = None
    if attempt.mistakes_only:
        note = "Повторяем вопросы, где в прошлый раз была ошибка."
    elif attempt.total < topic.size:
        note = f"В теме пока {attempt.total} вопр. — тест короче обычного ({topic.size})."
    return AttemptOut(
        id=attempt.id, topic_slug=topic.slug, topic_title=topic.title, status=attempt.status,
        mistakes_only=attempt.mistakes_only, score=attempt.score, total=attempt.total,
        created_at=attempt.created_at, finished_at=attempt.finished_at, note=note, items=items,
    )


def topic_card(db: Session, user: User, topic: QuizTopic) -> TopicCard:
    published = list(db.scalars(select(Question.id).where(Question.topic_id == topic.id, Question.status == QuestionStatus.published)))
    seen = set(_history(db, user, topic))
    last = _last_finished(db, user, topic)
    active = active_attempt(db, user, topic)
    attempts = db.scalar(select(func.count()).select_from(QuizAttempt).where(
        QuizAttempt.user_id == user.id, QuizAttempt.topic_id == topic.id, QuizAttempt.status == AttemptStatus.finished
    ))
    return TopicCard(
        slug=topic.slug, title=topic.title, description=topic.description, questions=len(published), size=topic.size,
        unseen=len([q for q in published if q not in seen]), active_attempt_id=active.id if active else None,
        last_score=last.score if last else None, last_total=last.total if last else None, attempts=attempts or 0,
    )
