"""Modelos de validación para las peticiones JSON."""

from typing import Literal

from pydantic import BaseModel, Field

Result = Literal["no", "parcial", "bien"]


class AnswerIn(BaseModel):
    question_id: str = Field(min_length=1, max_length=20)
    result: Result
    user_answer: str = Field(default="", max_length=5000)
    mode: Literal["estudio", "tarjetas", "repaso"] = "estudio"


class ExamCreate(BaseModel):
    unit_ids: list[str] = Field(min_length=1)
    count: int = Field(default=10, ge=1, le=100)


class ExamAnswer(BaseModel):
    question_id: str
    user_answer: str = Field(default="", max_length=5000)


class ExamFinish(BaseModel):
    answers: list[ExamAnswer]


class ExamResultItem(BaseModel):
    question_id: str
    result: Result


class ExamGrade(BaseModel):
    results: list[ExamResultItem]
