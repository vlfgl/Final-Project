from fastapi import APIRouter, Depends, HTTPException, Path

from app.auth import CurrentUser, require_consent
from app.schemas import GoalSave
from app.services import goal_service

router = APIRouter(prefix="/api/goals", tags=["goals"])
MONTH = Path(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM")


def _view(uid: str, month: str) -> dict:
    goal, inherited = goal_service.get_goal(uid, month)
    return {
        "month": month,
        "goal": None if not goal else {
            "total_budget": goal["total_budget"],
            "category_limits": goal.get("category_limits", []),
            "history": goal.get("history", []) if not inherited else [],
            "updated_at": goal.get("updated_at"),
        },
        "inherited_from": inherited,          # 이 달 목표가 없어 이전 달 목표를 이어받은 경우 그 달
        "editable": month >= goal_service.current_month(),
        "progress": goal_service.progress(uid, month, goal),
    }


@router.get("/{month}", summary="월 목표 + 진행률·페이스 (없으면 이전 달 목표를 이어받아 보여줌)")
def get_goal(month: str = MONTH, user: CurrentUser = Depends(require_consent)):
    return _view(user.uid, month)


@router.put("/{month}", summary="월 목표 저장 (변경 시 이전 값은 이력으로 남음, 지난 달은 수정 불가)")
def save_goal(payload: GoalSave, month: str = MONTH, user: CurrentUser = Depends(require_consent)):
    try:
        goal_service.save_goal(user.uid, month, payload.total_budget,
                               [c.model_dump() for c in payload.category_limits])
    except goal_service.GoalError as e:
        raise HTTPException(400, str(e))
    return _view(user.uid, month)


@router.delete("/{month}", summary="월 목표 해제", status_code=204)
def delete_goal(month: str = MONTH, user: CurrentUser = Depends(require_consent)):
    try:
        goal_service.delete_goal(user.uid, month)
    except goal_service.GoalError as e:
        raise HTTPException(400, str(e))


@router.get("/{month}/suggestion", summary="추천 목표 (최근 3개월 평균 기반, AI 미사용)")
def suggestion(month: str = MONTH, user: CurrentUser = Depends(require_consent)):
    return goal_service.suggest(user.uid, month)
