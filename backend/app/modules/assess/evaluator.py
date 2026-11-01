"""Оценщик (BRIEF §5.6, ADR-012): ответы на развилки вместе с кодом, который их реализует.

Как у Ревьюера — новая сессия на каждую оценку, без инструментов и без переписки с наставником: на входе
ответы, код с номерами строк, результаты тестов, отчёт Ревьюера, рубрика, эталоны и прошлые сдачи этого
практикума. Модель ставит баллы и находит «сказал ≠ сделал»; адреса и цитаты проверяет код, итог считает код.
"""

import re

from app.modules.assess.schemas import EvaluatorReport

PRINCIPLES = """\
Ты — независимый Оценщик учебной платформы «Развилка». Ты оцениваешь не код сам по себе (дефекты кода уже
нашёл Ревьюер — его отчёт во входе), а РЕШЕНИЯ ученика: насколько они продуманы и совпадают с реализацией.

Главное — «сказал ≠ сделал». Сверь каждое заявление в ответах на развилки с кодом. Сказал «PostgreSQL и
миграции» — в коде должны быть Postgres и миграции, а не SQLite и ручной SQL. Сказал «модули разделены» — нет
импортов через слои. Каждое расхождение — в mismatches: дословная цитата из ответа (claim), файл и номер
строки из входа, где код говорит другое, что именно там написано. Без строки кода расхождение не засчитывается.

Рубрика: каждый критерий 0–5, объяснение со ссылками на ответы и строки кода, evidence — конкретные строки.
5 — образцово, 3 — приемлемо с оговорками, 0–1 — нет или противоречит. Не завышай: «назвал вариант без
причин» — это не 4. Слабое обоснование и расхождение — разные вещи: расхождение отмечай всегда.

Учитывай общую картину: если в прошлых сдачах этого практикума ученик выбирал иначе и не объяснил смену —
это contradictions. reference_view: как эту развилку решили бы в эталонных проектах и почему.
Не хвали и не смягчай. Всё на русском. Ответ — строго по JSON-схеме."""


def _answer_text(answer: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in answer.items() if v)


def build_prompt(assignment, submission, rubric, references, tests: dict | None, review: dict | None,
                 code: dict[str, str], left_out: list[str], history: list[dict]) -> tuple[str, str]:
    crit = "\n".join(
        f"- {c['id']} [{'обоснование' if c['block'] == 'reasoning' else 'реализация'}] {c['title']}. {c.get('description', '')}"
        for c in rubric.criteria
    )
    system = f"{PRINCIPLES}\n\nРубрика (v{rubric.version}):\n{crit}"

    parts = [f"Практикум: {assignment.title}", "Условие:", assignment.statement or "—", ""]
    parts.append("Развилки и ответы ученика (формат ADR):")
    for fork in assignment.forks:
        answer = submission.answers.get(fork["id"])
        parts.append(f"\n[{fork['id']}] {fork['question']}")
        if fork.get("context"):
            parts.append(f"Контекст: {fork['context']}")
        parts.append(_answer_text(answer) if answer else "(ученик не ответил)")
    parts += ["", f"Что сделал и почему (ученик): {submission.summary or '—'}", ""]

    if tests is None:
        parts.append("Автотесты: в практикуме их нет.")
    else:
        lines = [f"{'✓' if r['passed'] else '✗'} {r['name']}{': ' + r['message'] if r.get('message') else ''}" for r in tests.get("results", [])]
        parts += ["Автотесты:", tests.get("error") or "", *lines]
    if review:
        parts += ["", f"Отчёт Ревьюера (вердикт {review.get('verdict')}):"]
        parts += [f"- {f['severity']} {f['rule']} {f['file']}:{f['line']} — {f['problem']}" for f in review.get("findings", [])] or ["замечаний нет"]
    if references:
        parts += ["", "Эталонные проекты:"] + [f"- {r.name} ({r.url}): {r.about}" for r in references]
    if history:
        parts += ["", "Прошлые сдачи этого практикума (общая картина):"]
        for h in history:
            parts.append(f"- попытка {h['attempt']}: итог {h['score']}; выборы: " + "; ".join(f"{k}: {v}" for k, v in h["choices"].items()))

    parts += ["", "Код сдачи (номер строки | текст):"]
    for name, text in code.items():
        numbered = "\n".join(f"{i:>4} | {line}" for i, line in enumerate(text.splitlines(), 1))
        parts.append(f"\n=== {name} ===\n{numbered}")
    if left_out:
        parts.append(f"\n(Не вошли в объём, только названия: {', '.join(left_out[:30])})")
    return system, "\n".join(parts)


def _norm(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


def claim_found(claim: str, answers: dict, summary: str = "") -> bool:
    """Цитата действительно из слов ученика — ответов на развилки или «что сделал и почему»: дословно или почти
    (знаки препинания и регистр не важны)."""
    whole = _norm(" ".join(_answer_text(a) for a in answers.values()) + " " + summary)
    words = _norm(claim).split()
    if not words:
        return False
    if " ".join(words) in whole:
        return True
    present = sum(1 for w in words if w in whole.split())
    return present / len(words) >= 0.8


def finalize(report: EvaluatorReport, rubric, submission, files: dict[str, str], threshold: float, tests: dict | None) -> dict:
    """Проверка ответа модели и итог. Возвращает то, что сохранится в submission.evaluation."""
    known = {c["id"]: c for c in rubric.criteria}
    notes: list[str] = []

    criteria = []
    by_id = {c.id: c for c in report.criteria if c.id in known}
    for cid, c in known.items():
        got = by_id.get(cid)
        if got is None:
            notes.append(f"Оценщик пропустил критерий {cid} — засчитан 0.")
        evidence = []
        for e in (got.evidence if got else []):
            if e.file in files:
                count = len(files[e.file].splitlines())
                evidence.append({"file": e.file, "line": e.line if 1 <= e.line <= count else None, "note": e.note})
        criteria.append({
            "id": cid, "block": c["block"], "title": c["title"], "score": got.score if got else 0,
            "explanation": got.explanation if got else "Нет оценки.", "evidence": evidence,
        })

    mismatches, dropped = [], 0
    for m in report.mismatches:
        text = files.get(m.file)
        lines = text.splitlines() if text is not None else []
        if text is None or not (1 <= m.line <= len(lines)):
            dropped += 1  # без настоящей строки кода расхождение не засчитываем
            continue
        mismatches.append({
            "fork_id": m.fork_id, "claim": m.claim, "claim_verified": claim_found(m.claim, submission.answers, submission.summary),
            "file": m.file, "line": m.line, "code_line": lines[m.line - 1].strip()[:300],
            "code_says": m.code_says, "why": m.why,
        })
    if dropped:
        notes.append(f"Отброшено расхождений без верного адреса в коде: {dropped}.")
    counted = [m for m in mismatches if m["claim_verified"]]

    def avg(block: str) -> float:
        scores = [c["score"] for c in criteria if c["block"] == block]
        return round(sum(scores) / len(scores), 2) if scores else 0.0

    reasoning, implementation = avg("reasoning"), avg("implementation")
    # Штраф — за первые два расхождения: дальше они уже учтены нулями в R5 и R7, а итог не уходит в минус из-за повторов
    penalty = round(rubric.mismatch_penalty * min(len(counted), 2), 2)
    score = max(0.0, round((reasoning + implementation) / 2 - penalty, 2))
    tests_ok = tests is None or tests.get("passed", False)
    passed = score >= threshold and tests_ok and not counted
    if not tests_ok:
        notes.append("Этап не засчитан: автотесты не пройдены.")
    if counted:
        notes.append("Этап не засчитан: есть расхождение «сказал ≠ сделал» — исправьте код или ответ.")
    return {
        "criteria": criteria, "reasoning": reasoning, "implementation": implementation, "penalty": penalty,
        "mismatches": mismatches, "contradictions": report.contradictions,
        "reference_view": [r.model_dump() for r in report.reference_view],
        "summary": report.summary, "notes": notes, "score": score, "passed": passed,
    }
