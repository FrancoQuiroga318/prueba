"""Lógica de estudio: banco de preguntas, repetición espaciada, estadísticas y exámenes."""

import json
import random
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from .database import BASE_DIR, get_connection

QUESTIONS_PATH = BASE_DIR / "data" / "questions.json"

# Intervalos (en días) tras respuestas correctas consecutivas: 1.ª, 2.ª, 3.ª...
CORRECT_INTERVALS = [1, 3, 7, 14, 30, 60]
PARTIAL_INTERVAL = 1
MASTERED_STREAK = 2  # aciertos seguidos para considerar una pregunta "dominada"
RESULT_SCORE = {"no": 0.0, "parcial": 0.5, "bien": 1.0}

TYPE_LABELS = {
    "definicion": "Definición",
    "enumeracion": "Enumeración",
    "caracteristicas": "Características",
    "comparacion": "Comparación",
    "funcionamiento": "Funcionamiento",
    "relacion": "Relación",
}
STATUS_LABELS = {
    "nueva": "Nueva",
    "aprendiendo": "Aprendiendo",
    "en_repaso": "En repaso",
    "dominada": "Dominada",
}


class NotFound(Exception):
    pass


class InvalidRequest(Exception):
    pass


# --- Banco de preguntas -----------------------------------------------------

@lru_cache
def load_bank(path: Path = QUESTIONS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        bank = json.load(f)
    unit_ids = {u["id"] for u in bank["units"]}
    seen = set()
    for q in bank["questions"]:
        if q["id"] in seen:
            raise ValueError(f"Pregunta duplicada: {q['id']}")
        if q["unit"] not in unit_ids:
            raise ValueError(f"Unidad inexistente en {q['id']}: {q['unit']}")
        seen.add(q["id"])
    return bank


def units() -> list[dict]:
    return load_bank()["units"]


def questions_by_id() -> dict[str, dict]:
    return {q["id"]: q for q in load_bank()["questions"]}


def get_unit(unit_id: str) -> dict:
    for u in units():
        if u["id"] == unit_id:
            return u
    raise NotFound(f"No existe la unidad '{unit_id}'")


def get_question(question_id: str) -> dict:
    q = questions_by_id().get(question_id)
    if q is None:
        raise NotFound(f"No existe la pregunta '{question_id}'")
    return q


def questions_for_unit(unit_id: str | None) -> list[dict]:
    if unit_id:
        get_unit(unit_id)
        return [q for q in load_bank()["questions"] if q["unit"] == unit_id]
    return list(load_bank()["questions"])


def topics_by_unit() -> dict[str, list[str]]:
    """Temas de cada unidad, en el orden en que aparecen en el banco."""
    result = {u["id"]: [] for u in units()}
    for q in load_bank()["questions"]:
        if q["topic"] not in result[q["unit"]]:
            result[q["unit"]].append(q["topic"])
    return result


def public_question(q: dict, include_answer: bool = True) -> dict:
    """Pregunta lista para enviar al navegador (con títulos legibles)."""
    data = {
        "id": q["id"],
        "unit": q["unit"],
        "unit_title": get_unit(q["unit"])["title"],
        "topic": q["topic"],
        "type": q["type"],
        "type_label": TYPE_LABELS.get(q["type"], q["type"]),
        "question": q["question"],
        "page": q["page"],
        "from_image": q.get("from_image", False),
    }
    if include_answer:
        data["answer"] = q["answer"]
    return data


# --- Repetición espaciada ---------------------------------------------------

def today() -> date:
    return date.today()


def schedule(previous: dict | None, result: str) -> dict:
    """Calcula el nuevo estado de una pregunta según la autoevaluación.

    - "no": vuelve a aparecer en la próxima sesión (hoy mismo).
    - "parcial": repaso próximo (mañana).
    - "bien": el intervalo crece 1, 3, 7, 14, 30, 60 días.
    """
    streak = previous["streak"] if previous else 0
    if result == "bien":
        streak += 1
        interval = CORRECT_INTERVALS[min(streak, len(CORRECT_INTERVALS)) - 1]
        status = "dominada" if streak >= MASTERED_STREAK else "en_repaso"
    elif result == "parcial":
        streak = 0
        interval = PARTIAL_INTERVAL
        status = "en_repaso"
    else:
        streak = 0
        interval = 0
        status = "aprendiendo"
    return {
        "streak": streak,
        "interval_days": interval,
        "status": status,
        "next_review": (today() + timedelta(days=interval)).isoformat(),
    }


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _apply_result(conn, question_id: str, result: str, user_answer: str, mode: str) -> dict:
    row = conn.execute("SELECT * FROM progress WHERE question_id = ?", (question_id,)).fetchone()
    previous = dict(row) if row else None
    new = schedule(previous, result)
    now = _now()
    conn.execute(
        """INSERT INTO progress (question_id, status, streak, interval_days, times_seen,
                                 times_correct, last_result, last_review, next_review)
           VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
           ON CONFLICT(question_id) DO UPDATE SET
               status = excluded.status, streak = excluded.streak,
               interval_days = excluded.interval_days,
               times_seen = progress.times_seen + 1,
               times_correct = progress.times_correct + excluded.times_correct,
               last_result = excluded.last_result, last_review = excluded.last_review,
               next_review = excluded.next_review""",
        (question_id, new["status"], new["streak"], new["interval_days"],
         1 if result == "bien" else 0, result, now, new["next_review"]),
    )
    conn.execute(
        "INSERT INTO answers (question_id, mode, result, user_answer, created_at) VALUES (?, ?, ?, ?, ?)",
        (question_id, mode, result, user_answer, now),
    )
    return new


def record_answer(question_id: str, result: str, user_answer: str = "", mode: str = "estudio") -> dict:
    q = get_question(question_id)
    with get_connection() as conn:
        new = _apply_result(conn, question_id, result, user_answer, mode)
    return {
        "question_id": question_id,
        "result": result,
        "status": new["status"],
        "status_label": STATUS_LABELS[new["status"]],
        "next_review": new["next_review"],
        "interval_days": new["interval_days"],
        "answer": q["answer"],
        "page": q["page"],
    }


def progress_map() -> dict[str, dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM progress").fetchall()
    return {r["question_id"]: dict(r) for r in rows}


def is_due(p: dict | None) -> bool:
    return p is not None and p["next_review"] <= today().isoformat()


def ordered_questions(unit_id: str | None = None, only_due: bool = False) -> list[dict]:
    """Preguntas en orden de estudio: pendientes de repaso, luego nuevas, luego el resto."""
    progress = progress_map()
    due, new, rest = [], [], []
    for q in questions_for_unit(unit_id):
        p = progress.get(q["id"])
        if is_due(p):
            due.append((p["next_review"], q))
        elif p is None:
            new.append(q)
        else:
            rest.append((p["next_review"], q))
    due.sort(key=lambda t: t[0])
    rest.sort(key=lambda t: t[0])
    if only_due:
        selected = [q for _, q in due]
    else:
        selected = [q for _, q in due] + new + [q for _, q in rest]
    result = []
    for q in selected:
        item = public_question(q)
        p = progress.get(q["id"])
        item["status"] = p["status"] if p else "nueva"
        item["status_label"] = STATUS_LABELS[item["status"]]
        item["due"] = is_due(p)
        result.append(item)
    return result


# --- Estadísticas -----------------------------------------------------------

def stats() -> dict:
    progress = progress_map()
    unit_stats = []
    totals = {"total": 0, "studied": 0, "mastered": 0, "learning": 0, "reviewing": 0, "due": 0}
    for u in units():
        qs = questions_for_unit(u["id"])
        s = {"total": len(qs), "studied": 0, "mastered": 0, "learning": 0, "reviewing": 0, "due": 0}
        for q in qs:
            p = progress.get(q["id"])
            if not p:
                continue
            s["studied"] += 1
            s["mastered"] += p["status"] == "dominada"
            s["learning"] += p["status"] == "aprendiendo"
            s["reviewing"] += p["status"] == "en_repaso"
            s["due"] += is_due(p)
        s["progress_pct"] = round(100 * s["mastered"] / s["total"], 1) if s["total"] else 0
        s["studied_pct"] = round(100 * s["studied"] / s["total"], 1) if s["total"] else 0
        for k in totals:
            totals[k] += s[k]
        unit_stats.append({**u, **s})
    t = totals["total"]
    totals["progress_pct"] = round(100 * totals["mastered"] / t, 1) if t else 0
    totals["studied_pct"] = round(100 * totals["studied"] / t, 1) if t else 0

    with get_connection() as conn:
        counts = {r["result"]: r["n"] for r in conn.execute(
            "SELECT result, COUNT(*) AS n FROM answers GROUP BY result")}
        exams = [dict(r) for r in conn.execute(
            "SELECT id, created_at, finished_at, unit_ids, total, score, percentage FROM exams "
            "WHERE status = 'finalizado' ORDER BY id DESC LIMIT 20")]
        hardest = conn.execute(
            "SELECT question_id, COUNT(*) AS fails FROM answers WHERE result != 'bien' "
            "GROUP BY question_id ORDER BY fails DESC, question_id LIMIT 10").fetchall()
    for e in exams:
        e["unit_titles"] = [get_unit(uid)["title"] for uid in json.loads(e["unit_ids"])]
    bank = questions_by_id()
    hardest_list = [
        {**public_question(bank[r["question_id"]], include_answer=False), "fails": r["fails"]}
        for r in hardest if r["question_id"] in bank
    ]
    return {
        "totals": totals,
        "units": unit_stats,
        "answers": {"total": sum(counts.values()), "no": counts.get("no", 0),
                    "parcial": counts.get("parcial", 0), "bien": counts.get("bien", 0)},
        "exams": exams,
        "hardest": hardest_list,
    }


# --- Exámenes ---------------------------------------------------------------

def create_exam(unit_ids: list[str], count: int) -> dict:
    unit_ids = list(dict.fromkeys(unit_ids))  # sin duplicados, respetando el orden
    pool = []
    for uid in unit_ids:
        pool.extend(questions_for_unit(uid))  # lanza NotFound si la unidad no existe
    chosen = random.sample(pool, min(count, len(pool)))
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO exams (created_at, unit_ids, question_ids, status, total) VALUES (?, ?, ?, 'en_curso', ?)",
            (_now(), json.dumps(unit_ids), json.dumps([q["id"] for q in chosen]), len(chosen)),
        )
        exam_id = cur.lastrowid
    return {"exam_id": exam_id, "total": len(chosen),
            "questions": [public_question(q, include_answer=False) for q in chosen]}


def _get_exam(conn, exam_id: int) -> dict:
    row = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    if row is None:
        raise NotFound(f"No existe el examen {exam_id}")
    exam = dict(row)
    exam["question_ids"] = json.loads(exam["question_ids"])
    return exam


def finish_exam(exam_id: int, answers: list[dict]) -> dict:
    """Guarda las respuestas escritas y revela las respuestas correctas."""
    with get_connection() as conn:
        exam = _get_exam(conn, exam_id)
        if exam["status"] == "finalizado":
            raise InvalidRequest("El examen ya fue finalizado")
        given = {a["question_id"]: a["user_answer"] for a in answers}
        unknown = set(given) - set(exam["question_ids"])
        if unknown:
            raise InvalidRequest(f"Preguntas que no pertenecen al examen: {sorted(unknown)}")
        for qid in exam["question_ids"]:
            conn.execute(
                "INSERT INTO exam_answers (exam_id, question_id, user_answer) VALUES (?, ?, ?) "
                "ON CONFLICT(exam_id, question_id) DO UPDATE SET user_answer = excluded.user_answer",
                (exam_id, qid, given.get(qid, "")),
            )
        conn.execute("UPDATE exams SET status = 'respondido' WHERE id = ?", (exam_id,))
    return {
        "exam_id": exam_id,
        "questions": [
            {**public_question(get_question(qid)), "user_answer": given.get(qid, "")}
            for qid in exam["question_ids"]
        ],
    }


def compute_score(results: list[str]) -> tuple[float, float]:
    """Puntaje: 1 por 'bien', 0,5 por 'parcial', 0 por 'no'. Devuelve (puntos, porcentaje)."""
    if not results:
        return 0.0, 0.0
    score = sum(RESULT_SCORE[r] for r in results)
    return score, round(100 * score / len(results), 1)


def grade_exam(exam_id: int, results: list[dict]) -> dict:
    """Guarda la autoevaluación, calcula la puntuación y actualiza la repetición espaciada."""
    with get_connection() as conn:
        exam = _get_exam(conn, exam_id)
        if exam["status"] == "finalizado":
            raise InvalidRequest("El examen ya fue finalizado")
        if exam["status"] != "respondido":
            raise InvalidRequest("Primero hay que entregar las respuestas del examen")
        given = {r["question_id"]: r["result"] for r in results}
        if set(given) != set(exam["question_ids"]):
            raise InvalidRequest("Hay que evaluar todas las preguntas del examen (y solo esas)")
        user_answers = {r["question_id"]: r["user_answer"] for r in conn.execute(
            "SELECT question_id, user_answer FROM exam_answers WHERE exam_id = ?", (exam_id,))}
        for qid in exam["question_ids"]:
            conn.execute("UPDATE exam_answers SET result = ? WHERE exam_id = ? AND question_id = ?",
                         (given[qid], exam_id, qid))
            _apply_result(conn, qid, given[qid], user_answers.get(qid, ""), "examen")
        score, pct = compute_score([given[qid] for qid in exam["question_ids"]])
        conn.execute(
            "UPDATE exams SET status = 'finalizado', score = ?, percentage = ?, finished_at = ? WHERE id = ?",
            (score, pct, _now(), exam_id),
        )

    by_unit: dict[str, dict] = {}
    to_review: dict[tuple, dict] = {}
    for qid in exam["question_ids"]:
        q = get_question(qid)
        u = by_unit.setdefault(q["unit"], {"unit": q["unit"], "unit_title": get_unit(q["unit"])["title"],
                                           "total": 0, "score": 0.0})
        u["total"] += 1
        u["score"] += RESULT_SCORE[given[qid]]
        if given[qid] != "bien":
            key = (q["unit"], q["topic"])
            t = to_review.setdefault(key, {"unit_title": u["unit_title"], "topic": q["topic"],
                                           "pages": set(), "count": 0})
            t["pages"].add(q["page"])
            t["count"] += 1
    for u in by_unit.values():
        u["percentage"] = round(100 * u["score"] / u["total"], 1)
    topics = sorted(
        ({**t, "pages": sorted(t["pages"])} for t in to_review.values()),
        key=lambda t: (-t["count"], t["unit_title"], t["topic"]),
    )
    return {
        "exam_id": exam_id,
        "total": len(exam["question_ids"]),
        "score": score,
        "percentage": pct,
        "counts": {r: list(given.values()).count(r) for r in ("bien", "parcial", "no")},
        "by_unit": list(by_unit.values()),
        "topics_to_review": topics,
    }
