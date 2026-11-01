"""Сдача на проверку (BRIEF §5.11): автотесты → Ревьюер → Оценщик.

Шаги идут по очередям: автотесты — в runner (без сети), Ревьюер и Оценщик — в потоке review agent-worker.
Каждый шаг пишет в сдачу свой отчёт и статус: пользователь видит прогресс и всё, что видели проверяющие.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.modules.agent import claude
from app.modules.assess import autotests, evaluator, seed
from app.modules.assess.models import Assignment, ReferenceProject, RubricSet, Submission, SubmissionStatus
from app.modules.assess.schemas import (
    AssignmentAdminOut,
    AssignmentCard,
    AssignmentForLearner,
    AssignmentIn,
    Criterion,
    EvaluatorReport,
    ForkAnswer,
    ReferenceOut,
    RubricOut,
    SubmissionCard,
    SubmissionOut,
)
from app.modules.assess.sources import code_for_review, list_projects
from app.modules.auth.models import User
from app.modules.courses.service import slugify
from app.modules.jobs.queue import enqueue
from app.modules.library.render import render_markdown
from app.modules.review import service as review_service
from app.modules.review.models import Review

CODE_BUDGET = 110_000  # символов кода для Ревьюера и Оценщика: больше — сдавайте часть проекта
STEPS = [("tests", "Автотесты"), ("review", "Ревьюер"), ("evaluate", "Оценщик")]


class AssessError(Exception):
    pass


# ---------- Рубрика, эталоны, практикумы ----------


def active_rubric(db: Session) -> RubricSet:
    current = db.scalar(select(RubricSet).order_by(RubricSet.version.desc()).limit(1))
    if current is None:
        current = RubricSet(version=1, criteria=seed.RUBRIC, mismatch_penalty=0.75, note="Из BRIEF §5.6")
        db.add(current)
        db.commit()
    return current


def save_rubric(db: Session, admin: User, criteria: list[Criterion], penalty: float, note: str) -> RubricSet:
    ids = [c.id for c in criteria]
    if len(ids) != len(set(ids)):
        raise AssessError("id критериев повторяются")
    if {c.block for c in criteria} != {"reasoning", "implementation"}:
        raise AssessError("Нужны критерии обоих блоков: обоснование и реализация")
    last = active_rubric(db)
    data = [c.model_dump() for c in criteria]
    if data == last.criteria and penalty == last.mismatch_penalty:
        return last
    new = RubricSet(version=last.version + 1, criteria=data, mismatch_penalty=penalty, note=note, created_by=admin.id)
    db.add(new)
    db.commit()
    return new


def rubric_out(rs: RubricSet) -> RubricOut:
    return RubricOut(version=rs.version, criteria=[Criterion.model_validate(c) for c in rs.criteria],
                     mismatch_penalty=rs.mismatch_penalty, note=rs.note, created_at=rs.created_at)


def seed_all(db: Session) -> dict:
    """Рубрика, эталоны и практикумы — один раз; повторный запуск ничего не дублирует."""
    active_rubric(db)
    refs = {r.name: r for r in db.scalars(select(ReferenceProject))}
    for r in seed.REFERENCES:
        if r["name"] not in refs:
            refs[r["name"]] = ReferenceProject(**r)
            db.add(refs[r["name"]])
    db.flush()
    created = 0
    for a in seed.ASSIGNMENTS:
        if db.scalar(select(Assignment.id).where(Assignment.slug == a["slug"])):
            continue
        db.add(Assignment(
            slug=a["slug"], title=a["title"], statement=a["statement"], kind=a["kind"], forks=a["forks"], tests=a["tests"],
            reference_ids=[refs[n].id for n in a["references"]], threshold=a["threshold"], published=True,
        ))
        created += 1
    db.commit()
    return {"references": len(refs), "assignments_created": created}


def unique_slug(db: Session, title: str) -> str:
    slug = base = slugify(title)[:70] or "praktikum"
    n = 2
    while db.scalar(select(Assignment.id).where(Assignment.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    return slug


def assignment_admin_out(db: Session, a: Assignment) -> AssignmentAdminOut:
    count = db.scalar(select(func.count()).where(Submission.assignment_id == a.id)) or 0
    return AssignmentAdminOut(id=a.id, slug=a.slug, submissions=count, title=a.title, statement=a.statement, kind=a.kind,
                              forks=a.forks, tests=a.tests, reference_ids=a.reference_ids, threshold=a.threshold, published=a.published)


def apply_assignment(a: Assignment, payload: AssignmentIn) -> None:
    ids = [f.id for f in payload.forks]
    if len(ids) != len(set(ids)):
        raise AssessError("id развилок повторяются")
    for name, value in payload.model_dump().items():
        setattr(a, name, value)


# ---------- Сдача ----------


def _references(db: Session, a: Assignment) -> list[ReferenceProject]:
    return list(db.scalars(select(ReferenceProject).where(ReferenceProject.id.in_(a.reference_ids))))


def submit(db: Session, user: User, a: Assignment, answers: dict[str, ForkAnswer], summary: str,
           files: dict[str, str], vendor: list[str], warnings: list[str], source: str, source_name: str) -> Submission:
    if not claude.configured():
        raise AssessError("Оценщик недоступен: Claude не подключён. Сдачу можно отправить, когда администратор добавит токен.")
    if a.path_id is not None:
        from app.modules.paths.service import check_order  # путь знает о сдачах, а не наоборот

        try:
            check_order(db, user, a)
        except Exception as exc:
            raise AssessError(str(exc)) from exc
    missing = [f["question"] for f in a.forks if f["id"] not in answers]
    if missing:
        raise AssessError(f"Ответьте на все развилки: {'; '.join(missing)}")
    busy = db.scalar(select(Submission.id).where(
        Submission.user_id == user.id, Submission.assignment_id == a.id,
        Submission.status.in_([SubmissionStatus.testing, SubmissionStatus.reviewing, SubmissionStatus.evaluating]),
    ))
    if busy:
        raise AssessError("Прошлая сдача этого практикума ещё проверяется — дождитесь отчёта")
    attempt = (db.scalar(select(func.max(Submission.attempt)).where(Submission.user_id == user.id, Submission.assignment_id == a.id)) or 0) + 1
    has_tests = a.kind != "any" and a.tests.strip()
    submission = Submission(
        user_id=user.id, assignment_id=a.id, attempt=attempt, source=source, source_name=source_name, files=files,
        vendor=vendor, warnings=warnings, answers={k: v.model_dump() for k, v in answers.items() if k in {f["id"] for f in a.forks}},
        summary=summary, rubric_version=active_rubric(db).version, tokens={},
        status=SubmissionStatus.testing if has_tests else SubmissionStatus.reviewing,
        steps=[{"key": k, "label": label, "state": "pending", "detail": ""} for k, label in STEPS],
    )
    db.add(submission)
    db.commit()
    if has_tests:
        _step(db, submission, "tests", "running", "runner запускает тесты практикума")
        enqueue(db, "runner", {"type": "test_submission", "submission_id": str(submission.id)})
    else:
        _step(db, submission, "tests", "skipped", "в практикуме нет автотестов — оценка по коду и ответам")
        enqueue(db, "review", {"type": "assess_submission", "submission_id": str(submission.id)})
    return submission


def _step(db: Session, s: Submission, key: str, state: str, detail: str = "") -> None:
    s.steps = [{**st, "state": state, "detail": detail[:300]} if st["key"] == key else st for st in s.steps]
    flag_modified(s, "steps")
    db.commit()


def _fail(db: Session, s: Submission, key: str, message: str) -> dict:
    s.status = SubmissionStatus.failed
    s.error = message
    s.finished_at = datetime.now(UTC)
    _step(db, s, key, "failed", message)
    return {"error": message}


def run_tests(db: Session, submission_id: int) -> dict:
    """Шаг 1 (runner): автотесты практикума на файлах сдачи."""
    s = db.get(Submission, submission_id)
    a = db.get(Assignment, s.assignment_id)
    try:
        outcome = autotests.run(a.kind, s.files, a.tests)
    except Exception as exc:  # Chromium или процесс упали — это не вина ученика, но отчёт нужен
        outcome = {"results": [], "error": f"Тесты не запустились: {type(exc).__name__}: {exc}", "passed": False}
    s.tests = outcome
    passed = sum(r["passed"] for r in outcome.get("results", []))
    total = len(outcome.get("results", []))
    _step(db, s, "tests", "done" if outcome["passed"] else "failed", outcome.get("error") or f"пройдено {passed} из {total}")
    s.status = SubmissionStatus.reviewing
    db.commit()
    enqueue(db, "review", {"type": "assess_submission", "submission_id": str(s.id)})
    return {"passed": outcome["passed"]}


def run_assessment(db: Session, submission_id: int) -> dict:
    """Шаги 2–3 (agent-worker, поток review): Ревьюер, затем Оценщик — каждый в своей чистой сессии."""
    s = db.get(Submission, submission_id)
    a = db.get(Assignment, s.assignment_id)
    user = db.get(User, s.user_id)
    code, left_out = code_for_review(s.files, s.vendor, CODE_BUDGET)
    if left_out:
        s.warnings = [*s.warnings, f"Не вошли в проверку по объёму: {', '.join(left_out[:8])}{'…' if len(left_out) > 8 else ''}"]

    _step(db, s, "review", "running", "Ревьюер читает код")
    try:
        review = review_service.project_review(db, user, a.title, a.statement, code)
    except review_service.ReviewError as exc:
        return _fail(db, s, "review", str(exc))
    s.review_id = review.id
    if review.status.value == "failed":
        return _fail(db, s, "review", review.error or "Ревьюер не ответил")
    c = review_service.counts(review)
    _step(db, s, "review", "done", "замечаний нет" if not review.findings else f"blocker {c['blocker']}, major {c['major']}, minor {c['minor']}")

    s.status = SubmissionStatus.evaluating
    _step(db, s, "evaluate", "running", "Оценщик сверяет ответы с кодом")
    rubric = db.scalar(select(RubricSet).where(RubricSet.version == s.rubric_version))
    history = [
        {"attempt": h.attempt, "score": h.score, "choices": {k: v.get("choice", "") for k, v in h.answers.items()}}
        for h in db.scalars(select(Submission).where(
            Submission.user_id == s.user_id, Submission.assignment_id == a.id, Submission.id < s.id, Submission.status == SubmissionStatus.done,
        ).order_by(Submission.id))
    ]
    system, prompt = evaluator.build_prompt(
        a, s, rubric, _references(db, a), s.tests, review_service.to_out(db, review).model_dump(mode="json"), code, left_out, history,
    )
    usage: dict[str, int] = {}
    try:
        report = claude.run_structured("evaluate", prompt, system, EvaluatorReport, effort="high", max_turns=4, library=False, on_usage=usage.update)
    except claude.AgentUnavailable as exc:
        return _fail(db, s, "evaluate", str(exc))
    result = evaluator.finalize(report, rubric, s, code, a.threshold, s.tests)
    s.evaluation = result
    s.score = result["score"]
    s.passed = result["passed"]
    s.tokens = {"review": review.tokens, "evaluate": usage}
    s.status = SubmissionStatus.done
    s.finished_at = datetime.now(UTC)
    mism = len([m for m in result["mismatches"] if m["claim_verified"]])
    _step(db, s, "evaluate", "done", f"итог {result['score']} из 5" + (f", «сказал ≠ сделал»: {mism}" if mism else ""))
    return {"score": s.score, "passed": s.passed, "mismatches": mism}


# ---------- Ответы API ----------


def _mismatch_count(s: Submission) -> int:
    return len([m for m in (s.evaluation or {}).get("mismatches", []) if m.get("claim_verified")])


def submission_card(db: Session, s: Submission) -> SubmissionCard:
    a = db.get(Assignment, s.assignment_id)
    return SubmissionCard(id=s.id, assignment_slug=a.slug, assignment_title=a.title, attempt=s.attempt, status=s.status,
                          score=s.score, passed=s.passed, mismatches=_mismatch_count(s), created_at=s.created_at)


def submission_out(db: Session, s: Submission) -> SubmissionOut:
    a = db.get(Assignment, s.assignment_id)
    review = db.get(Review, s.review_id) if s.review_id else None
    done = s.status is SubmissionStatus.done
    forks = [
        {"id": f["id"], "question": f["question"], "context": f.get("context", ""), "answer": s.answers.get(f["id"]),
         "reference": f.get("reference", "") if done else ""}  # ответ эталона — только после оценки
        for f in a.forks
    ]
    files = {p: t for p, t in s.files.items() if p not in s.vendor}
    return SubmissionOut(
        id=s.id, assignment_slug=a.slug, assignment_title=a.title, attempt=s.attempt, source=s.source, source_name=s.source_name,
        status=s.status, steps=s.steps, warnings=s.warnings, files=files, forks=forks, summary=s.summary, tests=s.tests,
        review=review_service.to_out(db, review).model_dump(mode="json") if review else None,
        evaluation=s.evaluation, score=s.score, passed=s.passed, threshold=a.threshold, rubric_version=s.rubric_version,
        error=s.error, created_at=s.created_at, finished_at=s.finished_at,
    )


def assignment_cards(db: Session, user: User) -> list[AssignmentCard]:
    out = []
    # Этапы путей «напиши заново сам» живут на странице пути, а не в общем списке практикумов
    for a in db.scalars(select(Assignment).where(Assignment.published.is_(True), Assignment.path_id.is_(None)).order_by(Assignment.id)):
        mine = list(db.scalars(select(Submission).where(Submission.user_id == user.id, Submission.assignment_id == a.id)))
        scores = [s.score for s in mine if s.score is not None]
        out.append(AssignmentCard(slug=a.slug, title=a.title, kind=a.kind, forks=len(a.forks), attempts=len(mine),
                                  best_score=max(scores) if scores else None, passed=any(s.passed for s in mine)))
    return out


def assignment_for_learner(db: Session, user: User, a: Assignment) -> AssignmentForLearner:
    mine = db.scalars(select(Submission).where(Submission.user_id == user.id, Submission.assignment_id == a.id).order_by(Submission.id.desc()))
    path_info = None
    if a.path_id is not None:
        from app.modules.paths.models import ProjectPath
        from app.modules.paths.service import stages, workspace_info

        path = db.get(ProjectPath, a.path_id)
        path_info = {"slug": path.slug, "title": path.title, "position": a.position, "total": len(stages(db, path)),
                     "workspace": workspace_info(user, path), "goal": a.goal, "files": a.files_hint}
    return AssignmentForLearner(
        slug=a.slug, title=a.title, statement_html=render_markdown(a.statement), kind=a.kind, path=path_info,
        forks=[{"id": f["id"], "question": f["question"], "context": f.get("context", "")} for f in a.forks],
        has_tests=a.kind != "any" and bool(a.tests.strip()), threshold=a.threshold,
        references=[ReferenceOut(id=r.id, name=r.name, url=r.url, about=r.about) for r in _references(db, a)],
        projects=list_projects(), submissions=[submission_card(db, s) for s in mine],
    )


# ---------- Журнал развилок ----------


def fork_journal(db: Session, user: User) -> list[dict]:
    """Все решения пользователя: последняя оценённая сдача каждого практикума, по развилкам."""
    entries = []
    latest: dict[int, Submission] = {}
    for s in db.scalars(select(Submission).where(Submission.user_id == user.id, Submission.status == SubmissionStatus.done).order_by(Submission.id)):
        latest[s.assignment_id] = s
    for s in latest.values():
        a = db.get(Assignment, s.assignment_id)
        ev = s.evaluation or {}
        views = {r["fork_id"]: r["reference"] for r in ev.get("reference_view", [])}
        for f in a.forks:
            answer = s.answers.get(f["id"])
            if not answer:
                continue
            entries.append({
                "assignment": a.title, "assignment_slug": a.slug, "submission_id": s.id, "attempt": s.attempt,
                "fork_id": f["id"], "question": f["question"], "answer": answer, "date": s.created_at.isoformat(),
                "score": s.score, "passed": s.passed, "reference": f.get("reference", ""), "evaluator_reference": views.get(f["id"], ""),
                "mismatches": [m for m in ev.get("mismatches", []) if m["fork_id"] == f["id"] and m.get("claim_verified")],
            })
    return entries


def journal_markdown(entries: list[dict]) -> str:
    """Выгрузка в формате docs/DECISIONS.md — чтобы положить в свой проект."""
    lines = ["# Журнал решений", "", "Выгружено из «Развилки». Формат — ADR: выбор, альтернативы, причины, риски, когда пересмотреть.", ""]
    for n, e in enumerate(entries, 1):
        a = e["answer"]
        lines += [
            f"## ADR-{n:03d}. {e['question']} — `{a['choice']}`",
            f"*{e['assignment']}, попытка {e['attempt']}, {e['date'][:10]}; оценка {e['score']} из 5.*", "",
            f"**Решение.** {a['choice']}",
            *([f"**Варианты.** {a['alternatives']}"] if a.get("alternatives") else []),
            f"**Почему.** {a['reasons']}",
            *([f"**Цена и риски.** {a['risks']}"] if a.get("risks") else []),
            *([f"**Пересмотреть, когда** {a['revisit']}"] if a.get("revisit") else []),
            *([f"**Расхождение с кодом.** «{m['claim']}» — {m['file']}:{m['line']}: {m['code_says']}" for m in e["mismatches"]]),
            "",
        ]
    return "\n".join(lines)
