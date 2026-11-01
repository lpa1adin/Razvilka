"""Служебные команды:
  python -m app.cli create-user <login> --role admin
  python -m app.cli seed-demo-tasks      — три демо-задания (веб, Python, SQL) черновиками
  python -m app.cli seed-quizzes         — банки вопросов для тестов (опубликованные темы)
"""

import argparse
import getpass
import json
from pathlib import Path

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.auth.models import Role, User
from app.modules.auth.service import create_user
from app.modules.library.models import Fragment, Source
from app.modules.practice.models import Task
from app.modules.practice.schemas import TaskSpec
from app.modules.practice.service import create_task, slugify
from app.modules.quiz.models import Question, QuestionStatus, QuizTopic
from app.modules.quiz.schemas import QuestionIn

SEED_DIR = Path(__file__).parent / "modules" / "practice" / "seed"
QUIZ_DIR = Path(__file__).parent / "modules" / "quiz" / "seed"


def seed_quizzes() -> None:
    """Вопрос публикуется, только если нашлась статья-источник; иначе остаётся черновиком (BRIEF §3.3)."""
    with SessionLocal() as db:
        for file in sorted(QUIZ_DIR.glob("*.json")):
            data = json.loads(file.read_text(encoding="utf-8"))
            slug = slugify(data["title"])
            if db.scalar(select(QuizTopic.id).where(QuizTopic.slug == slug)):
                print(f"Уже есть: {data['title']}")
                continue
            topic = QuizTopic(slug=slug, title=data["title"], description=data["description"], size=data["size"], published=True)
            db.add(topic)
            db.flush()
            drafts = 0
            for raw in data["questions"]:
                fragment_id = db.scalar(
                    select(Fragment.id).join(Source).where(Source.slug == raw.pop("source"), Fragment.title == raw.pop("fragment"))
                )
                status = QuestionStatus.published if fragment_id else QuestionStatus.draft
                drafts += status is QuestionStatus.draft
                question = QuestionIn.model_validate({**raw, "fragment_id": fragment_id, "status": status})
                db.add(Question(topic_id=topic.id, **question.model_dump()))
            db.commit()
            print(f"Тема «{data['title']}»: вопросов {len(data['questions'])}, без источника (черновики): {drafts}")


def seed_demo_tasks() -> None:
    """Создаёт демо-задания черновиками. Опубликовать их — через Мастерскую, после автопроверки."""
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.role == Role.admin).order_by(User.id))
        if admin is None:
            raise SystemExit("Сначала создайте администратора")
        for file in sorted(SEED_DIR.glob("*.json")):
            data = json.loads(file.read_text(encoding="utf-8"))
            titles = data.pop("fragment_titles", [])
            if db.scalar(select(Task.id).where(Task.slug == slugify(data["title"]))):
                print(f"Уже есть: {data['title']}")
                continue
            data["fragment_ids"] = [
                fid for title in titles
                if (fid := db.scalar(select(Fragment.id).where(Fragment.title == title).order_by(Fragment.id)))
            ]
            spec = TaskSpec.model_validate(data)
            create_task(db, spec.title, spec.kind, admin, spec)
            print(f"Создано (черновик): {spec.title}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("create-user", help="создать пользователя")
    add.add_argument("login")
    add.add_argument("--role", choices=[r.value for r in Role], default=Role.user.value)
    add.add_argument("--name", help="отображаемое имя")
    sub.add_parser("seed-demo-tasks", help="создать три демо-задания черновиками")
    sub.add_parser("seed-quizzes", help="загрузить банки вопросов")
    sub.add_parser("seed-assessment", help="рубрика Оценщика, эталонные проекты и практикумы (этап 6)")
    sub.add_parser("export-reviewer", help="напечатать агента Ревьюера для Claude Code (.claude/agents/reviewer.md)")
    args = parser.parse_args()

    if args.command == "seed-assessment":
        from app.modules.assess.service import seed_all

        with SessionLocal() as db:
            print(seed_all(db))
        return

    if args.command == "export-reviewer":
        from app.modules.review.service import active_rules, agent_markdown

        with SessionLocal() as db:
            print(agent_markdown(active_rules(db)), end="")
        return

    if args.command == "seed-quizzes":
        seed_quizzes()
        return

    if args.command == "seed-demo-tasks":
        seed_demo_tasks()
        return

    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.login == args.login.lower())):
            parser.exit(1, f"Логин {args.login} уже занят\n")
        password = getpass.getpass("Пароль: ")
        if len(password) < 8:
            parser.exit(1, "Пароль должен быть не короче 8 символов\n")
        create_user(db, args.login, password, Role(args.role), args.name)
        print(f"Готово: {args.login} ({args.role})")


if __name__ == "__main__":
    main()
