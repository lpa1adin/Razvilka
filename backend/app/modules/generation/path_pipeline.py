"""Черновик пути «напиши заново сам» (BRIEF §5.5, §5.10): этап за этапом.

Для каждого этапа Claude пишет условие, развилки с ответом автора и автотесты. Автопроверка без Claude:
тесты обязаны проходить на оригинальном проекте (он и есть эталон) и падать на пустой папке. Не прошло —
Claude один раз чинит тесты по отчёту. Ревьюер эталона здесь не нужен: эталон — проект автора как есть.
"""

import re
import time

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.modules.agent import claude
from app.modules.assess import autotests
from app.modules.assess.models import Assignment
from app.modules.assess.sources import from_folder
from app.modules.auth.models import User
from app.modules.courses.service import slugify
from app.modules.generation import prompts
from app.modules.generation.models import GenRequest, GenStatus
from app.modules.generation.pipeline import checkpoint, stop_now
from app.modules.generation.schemas import Plan, StageDraft, StageFix
from app.modules.jobs.queue import enqueue
from app.modules.library.models import Fragment
from app.modules.paths.models import ProjectPath
from app.modules.projectmap.graph import build, outline

CHECK_WAIT_SECONDS = 300
STAGE_PREFIX = re.compile(r"^\s*этап\s*\d+\s*[.:—-]?\s*", re.I)


def stage_title(n: int, title: str) -> str:
    """Claude иногда сам пишет «Этап 1.» в названии — номер ставим один раз."""
    return f"Этап {n}. {STAGE_PREFIX.sub('', title)}"


def _unique(db: Session, model, base: str) -> str:
    slug, n = base[:70] or "put", 2
    while db.scalar(select(model.id).where(model.slug == slug)):
        slug, n = f"{base[:66]}-{n}", n + 1
    return slug


def ensure_path(db: Session, req: GenRequest, plan: Plan, cwd: str) -> ProjectPath:
    path = db.get(ProjectPath, req.result.get("path_id")) if req.result.get("path_id") else None
    if path is None:
        langs = build(cwd)["languages"]
        kind = "web" if langs.get("HTML") else "python"
        path = ProjectPath(slug=_unique(db, ProjectPath, slugify(plan.title)), title=plan.title, project=req.project, kind=kind, gen_request_id=req.id)
        db.add(path)
        db.flush()
        req.result = {**req.result, "path_id": path.id}
    path.title = plan.title
    path.description = plan.description
    path.roles = [r.model_dump() for r in plan.roles]
    db.commit()
    return path


def write_stage(db: Session, req: GenRequest, path: ProjectPath, plan: Plan, n: int, lesson, cwd: str, instruction: str | None, progress,
                should_stop=None) -> Assignment:
    frags = db.scalars(select(Fragment).where(Fragment.id.in_(lesson.fragment_ids))).all()
    files_outline = "\n".join(outline(cwd, f) for f in (lesson.files or [])[:6])
    system, prompt = prompts.stage_prompt(req, plan.model_dump(), lesson.model_dump(), n, path.kind, files_outline,
                                          [f"#{f.id} «{f.title}»" for f in frags], instruction)
    draft = claude.run_structured("draft", prompt, system, StageDraft, cwd=cwd, effort="high", on_progress=progress, should_stop=should_stop)
    rec = req.result.get("lessons", {}).get(lesson.id, {})
    a = db.get(Assignment, rec.get("assignment_id")) if rec.get("assignment_id") else None
    if a is None:
        a = Assignment(slug=_unique(db, Assignment, f"{path.slug}-{n}"), path_id=path.id, published=False)
        db.add(a)
    a.title = stage_title(n, lesson.title)
    a.statement = draft.statement
    a.kind = path.kind
    a.forks = [{"id": f"f{i}", "question": f.question, "context": f.context, "reference": f.reference} for i, f in enumerate(draft.forks, 1)]
    a.tests = draft.tests
    a.reference_ids = []
    a.threshold = 3.0
    a.position = n
    a.goal = lesson.goal
    a.files_hint = list(lesson.files or [])
    a.fragment_ids = [f.id for f in frags]
    a.check_status = "queued"
    a.check_report = None
    db.commit()
    return a


def verify_stage(db: Session, assignment_id: int, files: dict) -> dict:
    """runner: на оригинале все тесты проходят, на пустой папке — нет."""
    a = db.get(Assignment, assignment_id)
    original = autotests.run(a.kind, files, a.tests)
    empty = autotests.run(a.kind, {"README.md": "# пусто\n"}, a.tests)
    problems = []
    if original.get("error"):
        problems.append(f"На оригинале: {original['error']}")
    failed = [f"{r['name']} — {r['message']}" for r in original.get("results", []) if not r["passed"]]
    if failed:
        problems.append("На оригинале не проходят: " + "; ".join(failed[:6]))
    if not original.get("results"):
        problems.append("Тестов не нашлось — объявите их через test(...) / def test_...")
    if empty.get("passed"):
        problems.append("Тесты проходят на пустой папке — этап получится пустым")
    a.check_status = "failed" if problems else "passed"
    a.check_report = {"problems": problems, "original": original, "passed": sum(r["passed"] for r in original.get("results", [])),
                      "total": len(original.get("results", []))}
    db.commit()
    return {"passed": not problems}


def _wait(db: Session, ids: list[int]) -> None:
    deadline = time.monotonic() + CHECK_WAIT_SECONDS
    while time.monotonic() < deadline:
        db.expire_all()
        if all(db.get(Assignment, i).check_status != "queued" for i in ids):
            return
        time.sleep(3)


def run_path_draft(db: Session, req: GenRequest, admin: User, steps, cwd: str, lesson_id: str, instruction: str) -> dict:
    plan = Plan.model_validate(req.plan)
    lessons = plan.modules[0].lessons
    targets = [(n, l) for n, l in enumerate(lessons, 1) if not lesson_id or l.id == lesson_id]
    for n, lesson in targets:
        done = not lesson_id and req.result.get("lessons", {}).get(lesson.id, {}).get("done")
        steps.set(f"lesson:{lesson.id}", "done" if done else "pending", label=stage_title(n, lesson.title))
    steps.set("checks", "pending", label="Автопроверки: тесты на оригинале и на пустой папке")
    steps.set("review", "skipped", "эталон — сам проект автора, Ревьюер ему не нужен", label="Ревьюер")

    path = ensure_path(db, req, plan, cwd)
    for n, lesson in targets:
        key = f"lesson:{lesson.id}"
        if not lesson_id and req.result.get("lessons", {}).get(lesson.id, {}).get("done"):
            continue
        checkpoint(req)
        steps.set(key, "running", "пишет этап")
        a = write_stage(db, req, path, plan, n, lesson, cwd, instruction or None, steps.progress(key), stop_now(req.id))
        lessons_map = dict(req.result.get("lessons", {}))
        lessons_map[lesson.id] = {"assignment_id": a.id, "theory": a.fragment_ids, "notes": [], "fixes": 0, "done": True}
        req.result = {**req.result, "lessons": lessons_map}
        flag_modified(req, "result")
        db.commit()
        steps.set(key, "done", f"развилок: {len(a.forks)}")

    # Автопроверки: оригинал проекта едет в runner вместе с задачей — у runner нет доступа к папкам владельца
    checkpoint(req)
    files, _, _ = from_folder(req.project, req.focus)
    ids = [req.result["lessons"][l.id]["assignment_id"] for _, l in targets]
    steps.set("checks", "running", "runner прогоняет тесты на оригинале и на пустой папке")
    for i in ids:
        enqueue(db, "runner", {"type": "verify_stage", "assignment_id": str(i), "files": files})
    _wait(db, ids)
    for _, lesson in targets:
        rec = req.result["lessons"][lesson.id]
        a = db.get(Assignment, rec["assignment_id"])
        if a.check_status != "failed" or rec.get("fixes", 0) >= 1:
            continue
        steps.set("checks", detail=f"чинит тесты «{a.title}» по отчёту")
        try:
            system, prompt = prompts.stage_fix_prompt(a.tests, a.check_report.get("problems", []), path.kind)
            fix = claude.run_structured("fix", prompt, system, StageFix, effort="high", max_turns=4, library=False, should_stop=stop_now(req.id))
            a.tests = fix.tests
            a.check_status = "queued"
            rec["notes"] = [*rec.get("notes", []), f"Тесты исправлены после автопроверки: {fix.note}"]
            db.commit()
            enqueue(db, "runner", {"type": "verify_stage", "assignment_id": str(a.id), "files": files})
        except claude.AgentUnavailable as exc:
            rec["notes"] = [*rec.get("notes", []), f"Не удалось исправить тесты: {exc}"]
        rec["fixes"] = rec.get("fixes", 0) + 1
        flag_modified(req, "result")
        db.commit()
    _wait(db, ids)
    checked = [db.get(Assignment, i) for i in ids]
    passed = sum(a.check_status == "passed" for a in checked)
    steps.set("checks", "done" if passed == len(checked) else "failed", f"прошли {passed} из {len(checked)}")
    req.status = GenStatus.draft_ready
    req.error = None
    db.commit()
    return {"stages": len(targets), "checks_passed": passed}
