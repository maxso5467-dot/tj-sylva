"""Xuenwu 学习助手 schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PracticeMode = Literal["current_progress", "specified_node", "wrong_retry"]
PracticeResult = Literal["correct", "partial", "wrong", "unknown", "skipped"]
MasteryState = Literal["not_started", "learning", "needs_consolidation", "basic_mastery", "fluent_mastery"]
WrongReviewStatus = Literal["to_review", "reviewing", "mastered"]


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


class PracticeSessionCreateIn(BaseModel):
    mode: PracticeMode = "current_progress"
    target_node_id: str | None = Field(default=None, max_length=64)
    question_count: int = Field(default=5, ge=1, le=10)


class PracticeSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    session_id: str
    mode: str
    target_node_id: str | None
    status: str
    question_count: int
    config_version: str
    ai_model: str
    ai_generation_version: str
    source_plan: dict
    stats: dict
    feedback: dict
    created_at: datetime
    completed_at: datetime | None


class PracticeItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    practice_session_id: str
    user_id: str
    session_id: str
    node_id: str | None
    generation_basis: str
    question_type: str
    difficulty: str
    content: str
    standard_answer: str
    explanation: str
    options: list
    answer_key: str
    auto_gradable: bool
    validation_status: str
    validation_errors: list
    source: str
    ai_model: str
    created_at: datetime


class PracticeSessionDetailOut(BaseModel):
    session: PracticeSessionOut
    items: list[PracticeItemOut]


class PracticeAttemptSubmitIn(BaseModel):
    student_answer: str = Field(default="", max_length=10000)
    student_confirmed_result: PracticeResult
    ai_suggested_result: PracticeResult | None = None
    ai_feedback: str = Field(default="", max_length=5000)
    error_reason: str = Field(default="", max_length=40)
    used_hint: bool = False
    viewed_answer: bool = False
    attempt_count: int = Field(default=1, ge=1, le=20)
    time_spent_seconds: int = Field(default=0, ge=0, le=86400)


class PracticeAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    practice_item_id: str
    practice_session_id: str
    user_id: str
    session_id: str
    node_id: str | None
    student_answer: str
    ai_suggested_result: str
    ai_feedback: str
    student_confirmed_result: str
    final_result: str
    score: int
    error_reason: str
    used_hint: bool
    viewed_answer: bool
    attempt_count: int
    time_spent_seconds: int
    created_at: datetime


class PracticeFinishOut(BaseModel):
    session: PracticeSessionOut
    stats: dict
    feedback: dict


class NodeMasteryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    session_id: str
    node_id: str
    mastery_state: str
    mastery_score: int
    valid_attempt_count: int
    medium_or_hard_count: int
    recent_window: list
    correct_streak: int
    last_practiced_at: datetime | None
    updated_at: datetime


class NodeMasteryListOut(BaseModel):
    items: list[NodeMasteryOut]
