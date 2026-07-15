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
    NodeMastery,
    PracticeAttempt,
    PracticeItem,
    PracticeSession,
    ReviewAttempt,
    ReviewItem,
    WrongQuestion,
    now_utc,
)
from app.schemas.xuenwu import (
    GenerateReviewIn,
    NodeMasteryListOut,
    PracticeAttemptOut,
    PracticeAttemptSubmitIn,
    PracticeFinishOut,
    PracticeItemOut,
    PracticeSessionCreateIn,
    PracticeSessionDetailOut,
    PracticeSessionOut,
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


def _score_for_result(result: str) -> int:
    return {
        "correct": 100,
        "partial": 50,
        "wrong": 0,
        "unknown": 0,
        "skipped": 0,
    }.get(result, 0)


def _question_type_for_content(content: str) -> tuple[str, bool]:
    text = content.strip()
    if all(option in text for option in ("A", "B", "C", "D")):
        return "choice", True
    if "填空" in text:
        return "fill_blank", True
    if "计算" in text or "求" in text:
        return "calculation", False
    if "代码" in text or "程序" in text:
        return "code", False
    return "short_answer", False


def _mastery_state(score: int, valid_count: int, medium_or_hard_count: int) -> str:
    if valid_count <= 0:
        return "not_started"
    if valid_count < 5:
        return "learning"
    if score < 60:
        return "needs_consolidation"
    if score < 90:
        return "basic_mastery" if medium_or_hard_count >= 2 else "learning"
    return "fluent_mastery" if medium_or_hard_count >= 5 else "basic_mastery"


async def _practice_items(db: AsyncSession, practice_session_id: str) -> list[PracticeItem]:
    result = await db.execute(
        select(PracticeItem)
        .where(PracticeItem.practice_session_id == practice_session_id)
        .order_by(PracticeItem.created_at.asc(), PracticeItem.id.asc())
    )
    return list(result.scalars().all())


async def _require_owned_practice_session(
    db: AsyncSession, practice_session_id: str, user: AppUser
) -> PracticeSession:
    practice = await db.get(PracticeSession, practice_session_id)
    if practice is None or practice.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="练习批次不存在")
    return practice


async def _update_node_mastery(db: AsyncSession, *, user: AppUser, node_id: str | None) -> NodeMastery | None:
    if not node_id:
        return None
    result = await db.execute(
        select(PracticeAttempt)
        .where(PracticeAttempt.user_id == user.id, PracticeAttempt.node_id == node_id)
        .order_by(PracticeAttempt.created_at.desc())
        .limit(10)
    )
    attempts = list(result.scalars().all())
    valid = attempts
    valid_count = len(valid)
    score = round(sum(a.score for a in valid) / valid_count) if valid_count else 0

    item_ids = [a.practice_item_id for a in valid]
    medium_or_hard_count = 0
    if item_ids:
        item_result = await db.execute(select(PracticeItem).where(PracticeItem.id.in_(item_ids)))
        items_by_id = {item.id: item for item in item_result.scalars().all()}
        medium_or_hard_count = sum(
            1
            for attempt in valid
            if items_by_id.get(attempt.practice_item_id)
            and items_by_id[attempt.practice_item_id].difficulty in {"medium", "hard"}
        )

    mastery_result = await db.execute(
        select(NodeMastery).where(
            NodeMastery.user_id == user.id,
            NodeMastery.node_id == node_id,
        )
    )
    mastery = mastery_result.scalars().first()
    if mastery is None:
        attempt = valid[0] if valid else None
        mastery = NodeMastery(
            user_id=user.id,
            session_id=attempt.session_id if attempt else "",
            node_id=node_id,
        )
        db.add(mastery)

    mastery.mastery_score = score
    mastery.valid_attempt_count = valid_count
    mastery.medium_or_hard_count = medium_or_hard_count
    mastery.recent_window = [
        {"attempt_id": a.id, "result": a.final_result, "score": a.score, "created_at": a.created_at.isoformat()}
        for a in reversed(valid)
    ]
    mastery.correct_streak = 0
    for attempt in attempts:
        if attempt.final_result == "correct":
            mastery.correct_streak += 1
        else:
            break
    mastery.mastery_state = _mastery_state(score, valid_count, medium_or_hard_count)
    mastery.last_practiced_at = attempts[0].created_at if attempts else None
    return mastery


async def _ai_exam_questions(
    *,
    service: KnowledgeMapService,
    db: AsyncSession,
    session: LearningSession,
    nodes: list[KnowledgeNode],
    count: int,
    focus_node_ids: list[str] | None = None,
) -> list[dict[str, str]]:
    current = next((node for node in nodes if node.id == session.current_node_id), None)
    usable_nodes = [node for node in nodes if node.parent_id] or nodes
    focus_set = set(focus_node_ids or [])
    focus_nodes = [node for node in nodes if node.id in focus_set]
    focus_nodes = focus_nodes or (([current] if current else []) + usable_nodes[:12])
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
    fallback_node = (focus_nodes[0] if focus_nodes else current or usable_nodes[0])
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


@router.post(
    "/sessions/{session_id}/practice-sessions",
    response_model=PracticeSessionDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_practice_session(
    session_id: str,
    payload: PracticeSessionCreateIn,
    db: AsyncSession = Depends(get_session),
    user: AppUser = Depends(get_current_user),
    service: KnowledgeMapService = Depends(get_service),
) -> PracticeSessionDetailOut:
    session = await _require_owned_session(db, session_id, user)
    nodes = await _session_nodes(db, session_id)
    usable_nodes = [node for node in nodes if node.parent_id] or nodes
    if not usable_nodes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前学习地图还没有知识节点")

    if payload.mode == "specified_node" and payload.target_node_id:
        if not any(node.id == payload.target_node_id for node in nodes):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="指定节点不属于当前学习地图")

    wrong_node_ids: list[str] = []
    if payload.mode == "wrong_retry":
        wrong_result = await db.execute(
            select(WrongQuestion.node_id)
            .where(
                WrongQuestion.user_id == user.id,
                WrongQuestion.session_id == session.id,
                WrongQuestion.node_id.is_not(None),
            )
            .order_by(WrongQuestion.created_at.desc())
            .limit(payload.question_count)
        )
        wrong_node_ids = [node_id for node_id in wrong_result.scalars().all() if node_id]
        if not wrong_node_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前错题本还没有可用于再练的错题")

    target_node_id = payload.target_node_id or session.current_node_id or usable_nodes[0].id
    if payload.mode == "wrong_retry":
        target_node_id = wrong_node_ids[0]
    source_plan = {
        "mode": payload.mode,
        "target_node_id": target_node_id,
        "question_count": payload.question_count,
        "default_difficulty": ["basic", "basic", "medium", "medium", "hard"][: payload.question_count],
        "basis_plan": (
            ["SPECIFIED_NODE"] * payload.question_count
            if payload.mode == "specified_node"
            else ["WRONG_KNOWLEDGE_POINT"] * payload.question_count
            if payload.mode == "wrong_retry"
            else ["CURRENT_NODE", "CURRENT_NODE", "COMPLETED_NODE", "WEAK_PREREQUISITE", "WRONG_KNOWLEDGE_POINT"][
                : payload.question_count
            ]
        ),
        "wrong_node_ids": wrong_node_ids,
    }
    practice = PracticeSession(
        user_id=user.id,
        session_id=session.id,
        mode=payload.mode,
        target_node_id=target_node_id,
        question_count=payload.question_count,
        source_plan=source_plan,
    )
    db.add(practice)
    await db.flush()

    try:
        focused_node_ids = (
            [payload.target_node_id]
            if payload.mode == "specified_node" and payload.target_node_id
            else wrong_node_ids
            if payload.mode == "wrong_retry"
            else None
        )
        generated = await _ai_exam_questions(
            service=service,
            db=db,
            session=session,
            nodes=nodes,
            count=payload.question_count,
            focus_node_ids=focused_node_ids,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[xuenwu] practice AI question fallback: {exc}")
        fallback_nodes = [node for node in nodes if focused_node_ids and node.id in set(focused_node_ids)]
        generated = _fallback_exam_questions(session, fallback_nodes or nodes, payload.question_count)

    basis_plan = source_plan["basis_plan"]
    items: list[PracticeItem] = []
    for index, raw in enumerate(generated[: payload.question_count]):
        question_type, auto_gradable = _question_type_for_content(raw["content"])
        item = PracticeItem(
            practice_session_id=practice.id,
            user_id=user.id,
            session_id=session.id,
            node_id=raw["node_id"],
            generation_basis=basis_plan[index] if index < len(basis_plan) else "CURRENT_NODE",
            question_type=question_type,
            difficulty=raw["difficulty"],
            content=raw["content"],
            standard_answer=raw["answer"],
            explanation=raw["explanation"],
            answer_key=raw["answer"][:255],
            auto_gradable=auto_gradable,
            validation_status="passed",
            source=raw["source"],
            ai_model=service.ai_client._model(),
        )
        db.add(item)
        items.append(item)

    await db.commit()
    await db.refresh(practice)
    for item in items:
        await db.refresh(item)
    return PracticeSessionDetailOut(
        session=PracticeSessionOut.model_validate(practice),
        items=[PracticeItemOut.model_validate(item) for item in items],
    )


@router.get("/practice-sessions/{practice_session_id}", response_model=PracticeSessionDetailOut)
async def get_practice_session(
    practice_session_id: str,
    db: AsyncSession = Depends(get_session),
    user: AppUser = Depends(get_current_user),
) -> PracticeSessionDetailOut:
    practice = await _require_owned_practice_session(db, practice_session_id, user)
    items = await _practice_items(db, practice.id)
    return PracticeSessionDetailOut(
        session=PracticeSessionOut.model_validate(practice),
        items=[PracticeItemOut.model_validate(item) for item in items],
    )


@router.post("/practice-items/{practice_item_id}/attempts", response_model=PracticeAttemptOut)
async def submit_practice_attempt(
    practice_item_id: str,
    payload: PracticeAttemptSubmitIn,
    db: AsyncSession = Depends(get_session),
    user: AppUser = Depends(get_current_user),
) -> PracticeAttemptOut:
    item = await db.get(PracticeItem, practice_item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="练习题不存在")
    practice = await _require_owned_practice_session(db, item.practice_session_id, user)
    final_result = payload.student_confirmed_result
    attempt = PracticeAttempt(
        practice_item_id=item.id,
        practice_session_id=practice.id,
        user_id=user.id,
        session_id=item.session_id,
        node_id=item.node_id,
        student_answer=payload.student_answer,
        ai_suggested_result=payload.ai_suggested_result or "",
        ai_feedback=payload.ai_feedback,
        student_confirmed_result=payload.student_confirmed_result,
        final_result=final_result,
        score=_score_for_result(final_result),
        error_reason=payload.error_reason,
        used_hint=payload.used_hint,
        viewed_answer=payload.viewed_answer,
        attempt_count=payload.attempt_count,
        time_spent_seconds=payload.time_spent_seconds,
    )
    db.add(attempt)

    if final_result in {"partial", "wrong", "unknown"}:
        wrong = WrongQuestion(
            user_id=user.id,
            session_id=item.session_id,
            node_id=item.node_id,
            practice_item_id=item.id,
            question=item.content,
            student_answer=payload.student_answer,
            correct_answer=item.standard_answer,
            practice_mode=practice.mode,
            question_type=item.question_type,
            difficulty=item.difficulty,
            result=final_result,
            error_reason=payload.error_reason,
            source=item.source,
            review_status="to_review",
            first_wrong_at=now_utc(),
            last_practiced_at=now_utc(),
        )
        db.add(wrong)

    await db.flush()
    await _update_node_mastery(db, user=user, node_id=item.node_id)
    await db.commit()
    await db.refresh(attempt)
    return PracticeAttemptOut.model_validate(attempt)


@router.post("/practice-sessions/{practice_session_id}/finish", response_model=PracticeFinishOut)
async def finish_practice_session(
    practice_session_id: str,
    db: AsyncSession = Depends(get_session),
    user: AppUser = Depends(get_current_user),
) -> PracticeFinishOut:
    practice = await _require_owned_practice_session(db, practice_session_id, user)
    result = await db.execute(
        select(PracticeAttempt).where(
            PracticeAttempt.practice_session_id == practice.id,
            PracticeAttempt.user_id == user.id,
        )
    )
    attempts = list(result.scalars().all())
    counts = {"correct": 0, "partial": 0, "wrong": 0, "unknown": 0, "skipped": 0}
    for attempt in attempts:
        counts[attempt.final_result] = counts.get(attempt.final_result, 0) + 1
    total_questions = max(practice.question_count, 1)
    answered = len(attempts) - counts.get("skipped", 0)
    score = round(sum(attempt.score for attempt in attempts) / total_questions)
    completion_rate = round(answered / total_questions * 100)
    node_scores: dict[str, list[int]] = {}
    for attempt in attempts:
        if attempt.node_id:
            node_scores.setdefault(attempt.node_id, []).append(attempt.score)
    weak_nodes = [
        {"node_id": node_id, "score": round(sum(scores) / len(scores))}
        for node_id, scores in node_scores.items()
        if scores and round(sum(scores) / len(scores)) < 60
    ]
    stats = {
        "score": score,
        "completion_rate": completion_rate,
        "answered": answered,
        "total": total_questions,
        "result_counts": counts,
        "weak_nodes": weak_nodes,
    }
    feedback = {
        "summary": f"本次练习得分 {score}%，完成率 {completion_rate}%。",
        "next_action": "优先复习薄弱节点后再继续学习。" if weak_nodes else "可以继续当前学习路线。",
    }
    practice.status = "completed"
    practice.completed_at = now_utc()
    practice.stats = stats
    practice.feedback = feedback
    await db.commit()
    await db.refresh(practice)
    return PracticeFinishOut(session=PracticeSessionOut.model_validate(practice), stats=stats, feedback=feedback)


@router.get("/sessions/{session_id}/node-mastery", response_model=NodeMasteryListOut)
async def list_node_mastery(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user: AppUser = Depends(get_current_user),
) -> NodeMasteryListOut:
    await _require_owned_session(db, session_id, user)
    result = await db.execute(
        select(NodeMastery)
        .where(NodeMastery.user_id == user.id, NodeMastery.session_id == session_id)
        .order_by(NodeMastery.updated_at.desc())
    )
    return NodeMasteryListOut(items=list(result.scalars().all()))


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
