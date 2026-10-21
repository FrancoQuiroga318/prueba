"""Aplicación FastAPI para estudiar Sistemas Operativos."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import study
from .database import init_db
from .models import AnswerIn, ExamCreate, ExamFinish, ExamGrade

APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    study.load_bank()  # valida el banco de preguntas al arrancar
    yield


app = FastAPI(title="Estudiar Sistemas Operativos", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")


@app.exception_handler(study.NotFound)
async def not_found_handler(request: Request, exc: study.NotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(study.InvalidRequest)
async def invalid_handler(request: Request, exc: study.InvalidRequest):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# --- Páginas HTML -----------------------------------------------------------

def render(request: Request, template: str, **context) -> HTMLResponse:
    return templates.TemplateResponse(request, template, {"units": study.units(), **context})


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return render(request, "index.html", stats=study.stats(), topics=study.topics_by_unit(), page="inicio")


@app.get("/estudiar", response_class=HTMLResponse)
def study_page(request: Request, unidad: str = "", modo: str = "estudio"):
    if modo not in ("estudio", "repaso"):
        modo = "estudio"
    return render(request, "study.html", selected_unit=unidad, mode=modo,
                  page="repaso" if modo == "repaso" else "estudiar")


@app.get("/repaso", response_class=HTMLResponse)
def review_page(request: Request):
    return study_page(request, modo="repaso")


@app.get("/tarjetas", response_class=HTMLResponse)
def flashcards_page(request: Request, unidad: str = ""):
    return render(request, "flashcards.html", selected_unit=unidad, page="tarjetas")


@app.get("/examen", response_class=HTMLResponse)
def exam_page(request: Request):
    return render(request, "exam.html", page="examen")


@app.get("/progreso", response_class=HTMLResponse)
def progress_page(request: Request):
    return render(request, "progress.html", stats=study.stats(), page="progreso")


# --- API JSON ---------------------------------------------------------------

@app.get("/api/units")
def api_units():
    return study.stats()["units"]


@app.get("/api/questions")
def api_questions(unit_id: str | None = None, only_due: bool = False):
    """Preguntas (con respuesta) en orden de estudio. La interfaz oculta la respuesta hasta revelarla."""
    return study.ordered_questions(unit_id or None, only_due)


@app.get("/api/review")
def api_review(unit_id: str | None = None):
    """Preguntas pendientes de repaso (falladas, parciales o con fecha de repaso vencida)."""
    return study.ordered_questions(unit_id or None, only_due=True)


@app.get("/api/flashcards")
def api_flashcards(unit_id: str | None = None):
    return [
        {"id": q["id"], "front": q["question"], "back": q["answer"], "page": q["page"],
         "from_image": q["from_image"], "unit_title": q["unit_title"], "topic": q["topic"],
         "status": q["status"], "status_label": q["status_label"], "due": q["due"]}
        for q in study.ordered_questions(unit_id or None)
    ]


@app.post("/api/answers")
def api_answer(data: AnswerIn):
    return study.record_answer(data.question_id, data.result, data.user_answer, data.mode)


@app.post("/api/exams")
def api_create_exam(data: ExamCreate):
    return study.create_exam(data.unit_ids, data.count)


@app.post("/api/exams/{exam_id}/finish")
def api_finish_exam(exam_id: int, data: ExamFinish):
    return study.finish_exam(exam_id, [a.model_dump() for a in data.answers])


@app.post("/api/exams/{exam_id}/grade")
def api_grade_exam(exam_id: int, data: ExamGrade):
    return study.grade_exam(exam_id, [r.model_dump() for r in data.results])


@app.get("/api/stats")
def api_stats():
    return study.stats()
