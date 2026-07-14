"""Xuenwu AI 学习助手接口。"""

from __future__ import annotations

import json
from typing import Any

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
from app.routers.deps import get_service
from app.services.auth import get_current_user
from app.services.knowledge import KnowledgeMapService

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


def _node_brief(node: KnowledgeNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "title": node.title,
        "summary": node.summary,
        "status": node.status,
        "difficulty": node.difficulty,
        "depth": node.depth,
    }


def _fallback_exam_questions(session: LearningSession, nodes: list[KnowledgeNode], count: int) -> list[dict[str, str]]:
    usable_nodes = [node for node in nodes if node.parent_id] or nodes
    templates = [
        (
            "question",
            "basic",
            "选择题：关于「{title}」，下列哪一项最符合它在本章中的作用？\nA. 只用于记忆定义\nB. 是后续解题的基础工具\nC. 与后续知识没有联系\nD. 只在拓展题中出现",
            "参考答案：B。关键是说明它为什么会支撑后续题型，而不是只背定义。",
        ),
        (
            "question",
            "basic",
            "填空题：请写出「{title}」中最关键的一个公式、条件或判断标准，并说明每个符号/条件的含义。",
            "参考答案：以当前教材或课堂笔记为准。答案应包含公式/条件本身，以及各部分含义。",
        ),
        (
            "question",
            "medium",
            "计算/解答题：围绕「{title}」设计一道基础计算题并完成求解，要求写出主要步骤。",
            "参考答案：步骤应包括识别题型、列出已知条件、套用对应方法、得到结果并检查条件。",
        ),
        (
            "question",
            "medium",
            "综合题：把「{title}」和它前后的知识点联系起来，完成一道需要两步以上推理的题，并写出解题思路。",
            "参考答案：答案应体现知识点之间的衔接关系，而不是孤立套公式。",
        ),
        (
            "question",
            "hard",
            "应用题：给出一个接近考试压轴/综合应用的「{title}」题目，要求说明建模或转化过程。",
            "参考答案：重点看能否把题目条件转化为对应知识点的表达式或解题路径。",
        ),
    ]
    questions: list[dict[str, str]] = []
    for index in range(count):
        node = usable_nodes[index % len(usable_nodes)]
        item_type, difficulty, content_template, answer = templates[index % len(templates)]
        questions.append({
            "node_id": node.id,
            "item_type": item_type,
            "difficulty": difficulty,
            "content": content_template.format(title=node.title),
            "answer": answer,
            "explanation": f"本题根据当前学习地图「{session.title}」中的知识节点「{node.title}」生成。",
            "source": "local",
        })
    return questions


async def _ai_exam_questions(
    *,
    service: KnowledgeMapService,
    db: AsyncSession,
    session: LearningSession,
    nodes: list[KnowledgeNode],
    count: int,
) -> list[dict[str, str]]:
    current = next((node for node in nodes if node.id == session.current_node_id), None)
    usable_nodes = [node for node in nodes if node.parent_id] or nodes
    focus_nodes = ([current] if current else []) + usable_nodes[:12]
    seen: set[str] = set()
    focus_nodes = [node for node in focus_nodes if not (node.id in seen or seen.add(node.id))]
    prompt = {
        "task": "根据学生当前学习路线生成考试风格练习题",
        "rules": [
            "只输出合法 JSON object, 不要 Markdown, 不要解释。",
            "题目必须是可作答的考试题, 不要生成'解释概念'这类泛泛问题。",
            "题型优先包含选择题、填空题、计算/解答题、应用题。",
            "难度分布: basic 2题, medium 2题, hard 1题；如果 count 不是5,按相近比例生成。",
            "题目要贴合学习地图和知识节点, 不要脱离当前路线。",
            "数学题要有具体条件、数值、表达式或明确求解目标。",
            "参考答案要给出最终答案和关键步骤。",
        ],
        "json_schema": {
            "items": [
                {
                    "node_title": "对应知识点标题",
                    "item_type": "question",
                    "difficulty": "basic|medium|hard",
                    "content": "完整题干。选择题必须包含 A/B/C/D 选项。",
                    "answer": "参考答案和关键步骤",
                    "explanation": "为什么这题适合当前学习进度",
                }
            ]
        },
        "count": count,
        "session": {
            "title": session.title,
            "field": session.field,
            "goal": session.current_problem,
            "background": session.learning_background,
            "current_node": _node_brief(current) if current else None,
        },
        "knowledge_nodes": [_node_brief(node) for node in focus_nodes],
    }
    data = await service.ai_client.chat(
        [
            {"role": "system", "content": "你是严谨的课程练习题命题老师，擅长按学习路线生成考试风格练习题。"},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        temperature=0.35,
        enable_web_search=False,
        purpose="xuenwu_exam_questions",
        session_id=session.id,
        db=db,
    )
    raw_items = data.get("items") or []
    if not isinstance(raw_items, list):
        raise ValueError("AI 出题结果缺少 items")
    by_title = {node.title: node for node in nodes}
    fallback_node = (current or usable_nodes[0])
    items: list[dict[str, str]] = []
    for raw in raw_items[:count]:
        if not isinstance(raw, dict):
            continue
        node = by_title.get(str(raw.get("node_title") or "").strip()) or fallback_node
        content = str(raw.get("content") or "").strip()
        answer = str(raw.get("answer") or "").strip()
        if not content or not answer:
            continue
        difficulty = str(raw.get("difficulty") or "medium").strip()
        if difficulty not in {"basic", "medium", "hard"}:
            difficulty = "medium"
        items.append({
            "node_id": node.id,
            "item_type": "question",
            "difficulty": difficulty,
            "content": content,
            "answer": answer,
            "explanation": str(raw.get("explanation") or f"本题根据「{node.title}」和当前学习路线生成。").strip(),
            "source": "ai",
        })
    if not items:
        raise ValueError("AI 未生成有效题目")
    return items


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
    service: KnowledgeMapService = Depends(get_service),
) -> ReviewItemsOut:
    session = await _require_owned_session(db, session_id, user)
    nodes = await _session_nodes(db, session_id)
    usable_nodes = [node for node in nodes if node.parent_id] or nodes
    if not usable_nodes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前学习地图还没有知识节点")

    try:
        generated = await _ai_exam_questions(
            service=service,
            db=db,
            session=session,
            nodes=nodes,
            count=payload.count,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[xuenwu] AI exam question fallback: {exc}")
        generated = _fallback_exam_questions(session, nodes, payload.count)

    created: list[ReviewItem] = []
    for raw in generated[: payload.count]:
        item = ReviewItem(
            user_id=user.id,
            session_id=session.id,
            node_id=raw["node_id"],
            item_type=raw["item_type"],
            difficulty=raw["difficulty"],
            content=raw["content"],
            answer=raw["answer"],
            explanation=raw["explanation"],
            source=raw["source"],
        )
        db.add(item)
        created.append(item)

    suggestion = AssistantSuggestion(
        user_id=user.id,
        session_id=session.id,
        node_id=session.current_node_id,
        content=f"建议先完成 {len(created)} 道考试风格练习题，再根据错题本回头复习薄弱知识点。",
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
