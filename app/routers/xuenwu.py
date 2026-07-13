"""Xuenwu AI 学习助手接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models import (
    AppUser,
    AssistantSuggestion,
    KnowledgeNode,
    LearningReflection,
    LearningSession,
    ReviewAttempt,
    ReviewItem,
    WrongQuestion,
    now_utc,
)
from app.schemas.xuenwu import (
    GenerateReviewIn,
    ReflectionIn,
    ReflectionOut,
    ReviewAttemptOut,
    ReviewItemsOut,
    SubmitReviewAttemptIn,
    SuggestionIn,
    SuggestionOut,
    SuggestionsOut,
    WrongQuestionsOut,
)
from app.services.auth import get_current_user

router = APIRouter(prefix="/api/xuenwu", tags=["xuenwu"])


async def _require_owned_session(db: AsyncSession, session_id: str, user: AppUser) -> LearningSession:
    session = await db.get(LearningSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学习地图不存在")
    return session


async def _session_nodes(db: AsyncSession, session_id: str) -> list[KnowledgeNode]:
    result = await db.execute(
        select(KnowledgeNode)
        .where(KnowledgeNode.session_id == session_id)
        .order_by(KnowledgeNode.depth.asc(), KnowledgeNode.sort_order.asc(), KnowledgeNode.created_at.asc())
    )
    return list(result.scalars().all())


@router.get("/sessions/{session_id}/review-items", response_model=ReviewItemsOut)
async def list_review_items(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user: AppUser = Depends(get_current_user),
) -> ReviewItemsOut:
    await _require_owned_session(db, session_id, user)
    result = await db.execute(
        select(ReviewItem)
        .where(ReviewItem.user_id == user.id, ReviewItem.session_id == session_id)
        .order_by(ReviewItem.created_at.desc())
        .limit(30)
    )
    return ReviewItemsOut(items=list(result.scalars().all()))


@router.post("/sessions/{session_id}/review-items/generate", response_model=ReviewItemsOut)
async def generate_review_items(
    session_id: str,
    payload: GenerateReviewIn,
    db: AsyncSession = Depends(get_session),
    user: AppUser = Depends(get_current_user),
) -> ReviewItemsOut:
    session = await _require_owned_session(db, session_id, user)
    nodes = await _session_nodes(db, session_id)
    usable_nodes = [node for node in nodes if node.parent_id] or nodes
    if not usable_nodes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前学习地图还没有知识节点")

    templates = [
        ("concept", "basic", "用自己的话快速解释「{title}」的核心含义。", "能说出核心定义和用途即可。"),
        ("question", "basic", "围绕「{title}」完成一道基础题，并写出关键步骤。", "答案需体现基本概念和步骤。"),
        ("question", "medium", "把「{title}」和前后知识点联系起来，完成一道综合理解题。", "答案需说明知识之间的关系。"),
        ("question", "hard", "请解决一个稍复杂的「{title}」应用题，并说明思路。", "答案需包含完整推理过程。"),
        ("reflection", "basic", "回顾最近学习「{title}」时最容易卡住的地方，并写一句反思。", "反思应具体到概念、步骤或题型。"),
    ]
    created: list[ReviewItem] = []
    for index in range(payload.count):
        node = usable_nodes[index % len(usable_nodes)]
        item_type, difficulty, content_template, answer = templates[index % len(templates)]
        item = ReviewItem(
            user_id=user.id,
            session_id=session.id,
            node_id=node.id,
            item_type=item_type,
            difficulty=difficulty,
            content=content_template.format(title=node.title),
            answer=answer,
            explanation=f"该内容根据当前学习地图「{session.title}」中的知识节点「{node.title}」生成。",
            source="local",
        )
        db.add(item)
        created.append(item)

    suggestion = AssistantSuggestion(
        user_id=user.id,
        session_id=session.id,
        node_id=session.current_node_id,
        content=f"建议先完成 {len(created)} 个轻量复习内容，再继续学习当前知识地图。",
        suggestion_type="review",
    )
    db.add(suggestion)
    await db.commit()
    for item in created:
        await db.refresh(item)
    return ReviewItemsOut(items=created)


@router.post("/review-items/{review_item_id}/attempts", response_model=ReviewAttemptOut)
async def submit_review_attempt(
    review_item_id: str,
    payload: SubmitReviewAttemptIn,
    db: AsyncSession = Depends(get_session),
    user: AppUser = Depends(get_current_user),
) -> ReviewAttemptOut:
    item = await db.get(ReviewItem, review_item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="复习内容不存在")

    attempt = ReviewAttempt(
        review_item_id=item.id,
        user_id=user.id,
        student_answer=payload.student_answer,
        is_correct=payload.is_correct,
    )
    item.status = "done"
    item.reviewed_at = now_utc()
    db.add(attempt)

    wrong_question_id = None
    if not payload.is_correct:
        wrong = WrongQuestion(
            user_id=user.id,
            session_id=item.session_id,
            node_id=item.node_id,
            review_item_id=item.id,
            question=item.content,
            student_answer=payload.student_answer,
            correct_answer=item.answer,
        )
        db.add(wrong)
        await db.flush()
        wrong_question_id = wrong.id

    await db.commit()
    await db.refresh(attempt)
    return ReviewAttemptOut.model_validate(attempt).model_copy(update={"wrong_question_id": wrong_question_id})


@router.get("/sessions/{session_id}/wrong-questions", response_model=WrongQuestionsOut)
async def list_wrong_questions(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user: AppUser = Depends(get_current_user),
) -> WrongQuestionsOut:
    await _require_owned_session(db, session_id, user)
    result = await db.execute(
        select(WrongQuestion)
        .where(WrongQuestion.user_id == user.id, WrongQuestion.session_id == session_id)
        .order_by(WrongQuestion.created_at.desc())
        .limit(50)
    )
    return WrongQuestionsOut(items=list(result.scalars().all()))


@router.post("/reflections", response_model=ReflectionOut, status_code=status.HTTP_201_CREATED)
async def create_reflection(
    payload: ReflectionIn,
    db: AsyncSession = Depends(get_session),
    user: AppUser = Depends(get_current_user),
) -> ReflectionOut:
    await _require_owned_session(db, payload.session_id, user)
    reflection = LearningReflection(user_id=user.id, **payload.model_dump())
    db.add(reflection)
    await db.commit()
    await db.refresh(reflection)
    return ReflectionOut.model_validate(reflection)


@router.get("/sessions/{session_id}/suggestions", response_model=SuggestionsOut)
async def list_suggestions(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user: AppUser = Depends(get_current_user),
) -> SuggestionsOut:
    await _require_owned_session(db, session_id, user)
    result = await db.execute(
        select(AssistantSuggestion)
        .where(AssistantSuggestion.user_id == user.id, AssistantSuggestion.session_id == session_id)
        .order_by(AssistantSuggestion.created_at.desc())
        .limit(30)
    )
    return SuggestionsOut(items=list(result.scalars().all()))


@router.post("/suggestions", response_model=SuggestionOut, status_code=status.HTTP_201_CREATED)
async def create_suggestion(
    payload: SuggestionIn,
    db: AsyncSession = Depends(get_session),
    user: AppUser = Depends(get_current_user),
) -> SuggestionOut:
    await _require_owned_session(db, payload.session_id, user)
    suggestion = AssistantSuggestion(user_id=user.id, **payload.model_dump())
    db.add(suggestion)
    await db.commit()
    await db.refresh(suggestion)
    return SuggestionOut.model_validate(suggestion)
