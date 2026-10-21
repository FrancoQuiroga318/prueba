import sqlite3
from datetime import date, timedelta

import pytest

from app import study


def first_question(client, unit_id="u1"):
    return client.get("/api/questions", params={"unit_id": unit_id}).json()[0]


# --- Páginas -----------------------------------------------------------------

@pytest.mark.parametrize("url, text", [
    ("/", "Estudiá Sistemas Operativos"),
    ("/estudiar", "Estudiar por tema"),
    ("/estudiar?unidad=u4", "Estudiar por tema"),
    ("/repaso", "Repaso de pendientes"),
    ("/tarjetas", "Tarjetas de memoria"),
    ("/examen", "Modo examen"),
    ("/progreso", "Tu progreso"),
])
def test_html_pages_load(client, url, text):
    r = client.get(url)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert text in r.text


def test_static_files(client):
    assert client.get("/static/css/style.css").status_code == 200
    assert client.get("/static/js/app.js").status_code == 200


# --- Preguntas ---------------------------------------------------------------

def test_every_unit_has_questions(client):
    units = client.get("/api/units").json()
    assert len(units) == 10
    for u in units:
        qs = client.get("/api/questions", params={"unit_id": u["id"]}).json()
        assert len(qs) == u["total"] > 0
        assert all(q["unit"] == u["id"] for q in qs)
        assert all(q["answer"] and q["question"] and q["page"] for q in qs)


def test_unknown_unit_returns_404(client):
    r = client.get("/api/questions", params={"unit_id": "nope"})
    assert r.status_code == 404


def test_flashcards(client):
    cards = client.get("/api/flashcards", params={"unit_id": "u2"}).json()
    assert cards and all({"front", "back", "page"} <= c.keys() for c in cards)


def test_question_types_cover_requested_kinds():
    kinds = {q["type"] for q in study.load_bank()["questions"]}
    assert kinds == {"definicion", "enumeracion", "caracteristicas", "comparacion", "funcionamiento", "relacion"}


def test_questions_have_valid_pdf_references():
    bank = study.load_bank()
    units = {u["id"]: u for u in bank["units"]}
    for q in bank["questions"]:
        first, last = units[q["unit"]]["pages"]
        assert 1 <= q["page"] <= bank["pdf_pages"], q["id"]
        assert first <= q["page"] <= last, f"{q['id']} pág. {q['page']} fuera de la unidad"


def test_pdf_page_count_matches_bank():
    pdf = study.BASE_DIR / "Sistemas Operativos.pdf"
    if not pdf.exists():
        pytest.skip("PDF no disponible")
    pymupdf = pytest.importorskip("pymupdf")
    assert len(pymupdf.open(pdf)) == study.load_bank()["pdf_pages"]


def test_text_based_questions_match_pdf_page():
    """Comprueba con el PDF que palabras clave de la pregunta aparecen en la página citada (o la anterior/siguiente)."""
    pdf = study.BASE_DIR / "Sistemas Operativos.pdf"
    if not pdf.exists():
        pytest.skip("PDF no disponible")
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open(pdf)
    pages = [p.get_text().lower() for p in doc]
    checks = {
        "u2-01": "ken thompson", "u3-10": "glibc", "u4-08": "mmu", "u4-20": "página 3",
        "u5-10": "system call", "u6-01": "instruction set architecture", "u7-11": "minix",
        "u8-03": "bare-metal", "u9-12": "comparación rápida", "u10-07": "20%",
    }
    for qid, keyword in checks.items():
        page = study.get_question(qid)["page"]
        window = " ".join(pages[max(0, page - 2):page + 1])
        assert keyword in window, f"{qid}: '{keyword}' no está cerca de la pág. {page}"


# --- Responder y guardar -----------------------------------------------------

def test_answer_is_saved_in_sqlite(client, db_path):
    q = first_question(client)
    r = client.post("/api/answers", json={"question_id": q["id"], "result": "parcial",
                                          "user_answer": "mi respuesta", "mode": "estudio"})
    assert r.status_code == 200
    data = r.json()
    # La respuesta revelada y la página vienen en el resultado.
    assert data["answer"] == q["answer"] and data["page"] == q["page"]
    assert data["status"] == "en_repaso"

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT question_id, result, user_answer FROM answers").fetchone()
    assert row == (q["id"], "parcial", "mi respuesta")
    prog = conn.execute("SELECT times_seen, last_result, next_review FROM progress").fetchone()
    assert prog == (1, "parcial", (date.today() + timedelta(days=1)).isoformat())


def test_answer_validation(client):
    q = first_question(client)
    assert client.post("/api/answers", json={"question_id": q["id"], "result": "quizas"}).status_code == 422
    assert client.post("/api/answers", json={"question_id": "zzz", "result": "bien"}).status_code == 404


def test_stats_reflect_answers(client):
    q = first_question(client)
    client.post("/api/answers", json={"question_id": q["id"], "result": "bien"})
    client.post("/api/answers", json={"question_id": q["id"], "result": "bien"})
    s = client.get("/api/stats").json()
    assert s["totals"]["studied"] == 1
    assert s["totals"]["mastered"] == 1
    assert s["answers"] == {"total": 2, "no": 0, "parcial": 0, "bien": 2}


# --- Repetición espaciada ----------------------------------------------------

def test_schedule_rules():
    s = study.schedule(None, "no")
    assert (s["interval_days"], s["status"]) == (0, "aprendiendo")
    s = study.schedule(None, "parcial")
    assert (s["interval_days"], s["status"]) == (1, "en_repaso")
    s1 = study.schedule(None, "bien")
    s2 = study.schedule(s1, "bien")
    s3 = study.schedule(s2, "bien")
    assert [s1["interval_days"], s2["interval_days"], s3["interval_days"]] == [1, 3, 7]
    assert s1["status"] == "en_repaso" and s2["status"] == "dominada"
    assert study.schedule(s3, "no")["streak"] == 0


def test_failed_questions_appear_in_review(client, monkeypatch):
    qs = client.get("/api/questions", params={"unit_id": "u4"}).json()
    failed, partial, ok = qs[0]["id"], qs[1]["id"], qs[2]["id"]
    client.post("/api/answers", json={"question_id": failed, "result": "no"})
    client.post("/api/answers", json={"question_id": partial, "result": "parcial"})
    client.post("/api/answers", json={"question_id": ok, "result": "bien"})

    review = [q["id"] for q in client.get("/api/review").json()]
    assert review == [failed]
    # La pregunta fallada aparece primero en la siguiente sesión de estudio.
    assert client.get("/api/questions", params={"unit_id": "u4"}).json()[0]["id"] == failed

    # Mañana también vencen la parcial y la correcta (intervalo de 1 día).
    monkeypatch.setattr(study, "today", lambda: date.today() + timedelta(days=1))
    review = {q["id"] for q in client.get("/api/review").json()}
    assert review == {failed, partial, ok}


# --- Examen ------------------------------------------------------------------

def test_exam_scoring(client, db_path):
    exam = client.post("/api/exams", json={"unit_ids": ["u1", "u2"], "count": 4}).json()
    assert exam["total"] == 4
    assert all("answer" not in q for q in exam["questions"])  # respuestas ocultas
    ids = [q["id"] for q in exam["questions"]]

    revealed = client.post(f"/api/exams/{exam['exam_id']}/finish",
                           json={"answers": [{"question_id": i, "user_answer": "x"} for i in ids]}).json()
    assert all(q["answer"] for q in revealed["questions"])

    results = dict(zip(ids, ["bien", "parcial", "no", "bien"]))
    r = client.post(f"/api/exams/{exam['exam_id']}/grade",
                    json={"results": [{"question_id": i, "result": v} for i, v in results.items()]})
    assert r.status_code == 200
    data = r.json()
    assert data["score"] == 2.5
    assert data["percentage"] == 62.5
    assert data["counts"] == {"bien": 2, "parcial": 1, "no": 1}
    review_topics = {(t["topic"]) for t in data["topics_to_review"]}
    for qid in (ids[1], ids[2]):
        assert study.get_question(qid)["topic"] in review_topics

    # Guardado en SQLite y visible en estadísticas.
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT status, score, percentage FROM exams").fetchone() == ("finalizado", 2.5, 62.5)
    assert client.get("/api/stats").json()["exams"][0]["percentage"] == 62.5
    # La pregunta no recordada en el examen pasa al repaso.
    assert ids[2] in [q["id"] for q in client.get("/api/review").json()]


def test_exam_errors(client):
    assert client.post("/api/exams", json={"unit_ids": []}).status_code == 422
    assert client.post("/api/exams", json={"unit_ids": ["x"]}).status_code == 404
    assert client.post("/api/exams/999/finish", json={"answers": []}).status_code == 404

    exam = client.post("/api/exams", json={"unit_ids": ["u3"], "count": 2}).json()
    ids = [q["id"] for q in exam["questions"]]
    grade = {"results": [{"question_id": i, "result": "bien"} for i in ids]}
    # No se puede corregir antes de entregar.
    assert client.post(f"/api/exams/{exam['exam_id']}/grade", json=grade).status_code == 400
    client.post(f"/api/exams/{exam['exam_id']}/finish", json={"answers": []})
    # Hay que evaluar todas las preguntas.
    partial = {"results": grade["results"][:1]}
    assert client.post(f"/api/exams/{exam['exam_id']}/grade", json=partial).status_code == 400
    assert client.post(f"/api/exams/{exam['exam_id']}/grade", json=grade).status_code == 200
    # Y no se puede corregir dos veces.
    assert client.post(f"/api/exams/{exam['exam_id']}/grade", json=grade).status_code == 400


def test_exam_count_limited_to_available(client):
    total_u3 = len(study.questions_for_unit("u3"))
    exam = client.post("/api/exams", json={"unit_ids": ["u3"], "count": 100}).json()
    assert exam["total"] == total_u3


def test_compute_score():
    assert study.compute_score([]) == (0.0, 0.0)
    assert study.compute_score(["bien", "bien", "no"]) == (2.0, 66.7)
    assert study.compute_score(["parcial"]) == (0.5, 50.0)
