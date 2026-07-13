"""Xuenwu 学习助手 schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    session_id: str
    node_id: str | None
    item_type: str
    difficulty: str
    content: str
    answer: str
    explanation: str
    source: str
    status: str
    created_at: datetime
    reviewed_at: datetime | None


class ReviewItemsOut(BaseModel):
    items: list[ReviewItemOut]


class GenerateReviewIn(BaseModel):
    count: int = Field(default=5, ge=1, le=10)


class SubmitReviewAttemptIn(BaseModel):
    student_answer: str = Field(default="", max_length=5000)
    is_correct: bool = False


class ReviewAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_item_id: str
    user_id: str
    student_answer: str
    is_correct: bool
    created_at: datetime
    wrong_question_id: str | None = None


class WrongQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    session_id: str
    node_id: str | None
    review_item_id: str | None
    question: str
    student_answer: str
    correct_answer: str
    review_status: str
    created_at: datetime
    updated_at: datetime


class WrongQuestionsOut(BaseModel):
    items: list[WrongQuestionOut]


class ReflectionIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    node_id: str | None = Field(default=None, max_length=64)
    wrong_question_id: str | None = Field(default=None, max_length=64)
    content: str = Field(min_length=1, max_length=5000)


class ReflectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    session_id: str
    node_id: str | None
    wrong_question_id: str | None
    content: str
    created_at: datetime


class SuggestionIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    node_id: str | None = Field(default=None, max_length=64)
    content: str = Field(min_length=1, max_length=5000)
    suggestion_type: str = Field(default="review", max_length=30)


class SuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    session_id: str
    node_id: str | None
    content: str
    suggestion_type: str
    created_at: datetime


class SuggestionsOut(BaseModel):
    items: list[SuggestionOut]
