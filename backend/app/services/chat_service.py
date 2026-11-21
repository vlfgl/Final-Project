"""AI 절약 코치 채팅.

두 가지 방식을 둔다.
- agent (기본): 모델이 질문을 보고 필요한 도구를 스스로 골라 호출(Function Calling)하고,
  도구 결과를 보고 다시 판단하는 루프를 돈다. 답변의 숫자는 도구 결과에서만 가져온다.
- baseline: 이전 방식. 코드가 미리 계산한 요약·목표를 프롬프트에 통째로 넣고 GPT를 1번 호출한다.
  (평가 스크립트에서 두 방식을 같은 질문으로 비교하기 위해 남겨 둔다. COACH_MODE=baseline)
"""
import json
import logging
from datetime import timedelta
from typing import Optional

from app.config import settings
from app.db import CONVERSATIONS, get_store, user_col
from app.schemas import CATEGORIES
from app.services import agent_tools, conversation_service, goal_service, summary_service
from app.services.llm import ChatError  # noqa: F401  (라우터가 chat_service.ChatError로 참조)
from app.services.llm import get_client as _get_client

logger = logging.getLogger("spending-coach.agent")

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

# ---------------------------------------------------------------- agent
AGENT_SYSTEM = """당신은 사용자의 소비 습관을 함께 관리하는 AI 절약 코치입니다. 사용자의 실제 거래 데이터는 도구로만 볼 수 있습니다.

[오늘] {today} ({weekday}요일) · 이번 달 {cur} · 지난달 {prev}
[데이터 범위] {data_range}  ← 도구 인자를 정할 때 참고. 금액 정보가 아님
[이번 달 목표] {goal_state}
[카테고리] {categories}

[규칙]
1. 금액·건수·비율·날짜 같은 숫자는 이번 대화에서 받은 도구 결과에 있는 값만 쓴다. 기억이나 추측으로 숫자를 만들지 않는다. 카테고리는 결과의 이름 그대로 말한다(예: '카페'가 아니라 '카페·간식' — 아이스크림·디저트도 포함되기 때문).
2. 사용자의 지출·목표에 관한 질문이면 먼저 필요한 도구를 호출한다. 필요하면 여러 도구를 함께 부르고, 결과를 보고 추가로 부른다.
3. 데이터가 필요 없는 질문(일반적인 절약 방법, 서비스 사용법, 인사)은 도구 없이 답한다.
4. '이번 달', '지난달', '최근 3개월', '9월' 같은 표현은 오늘 날짜 기준으로 YYYY-MM 또는 YYYY-MM-DD로 바꿔 넘긴다.
5. 진행 중인 달의 수치는 '현재까지'임을 밝힌다. 도구 결과에 없는 것은 모른다고 말한다.
6. 목표를 세우거나 바꿔 달라고 하면 근거 도구로 먼저 확인한 뒤 반드시 propose_goal을 호출해 제안한다. 제안 내용을 글로만 쓰면 [적용] 버튼이 생기지 않는다. propose_goal 결과를 받은 뒤에만 '아래 [적용] 버튼을 누르면 저장된다'고 안내하고, 저장됐다고 말하지 않는다. 진행 중인 달의 한도는 이미 쓴 금액보다 크게 잡는다.
7. 도구가 error를 돌려주면 인자를 고쳐 다시 부른다. 도구는 질문에 꼭 필요한 것만, 한 번에 4개 이하로 부른다.
8. 한국어로 3~6문장. 핵심 숫자를 들어 설명하고, 절약 조언은 실천할 수 있게 구체적으로 한다."""


def agent_system_prompt(uid: str) -> str:
    today = summary_service.today_kst()
    cur = today.strftime("%Y-%m")
    prev = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    rows = agent_tools.list_transactions(uid, descending=False)
    data_range = f"거래 {len(rows)}건, {rows[0]['date']} ~ {rows[-1]['date']}" if rows else "아직 거래 없음"
    goal, inherited = goal_service.get_goal(uid, cur)
    goal_state = ("없음" if not goal else
                  "있음" + (f" ({inherited} 목표를 이어서 적용 중)" if inherited else ""))
    return AGENT_SYSTEM.format(today=today.isoformat(), weekday=WEEKDAYS[today.weekday()], cur=cur, prev=prev,
                               data_range=data_range, goal_state=goal_state, categories=", ".join(CATEGORIES))


def _history(uid: str, conversation_id: Optional[str]) -> list[dict]:
    if not conversation_id:
        return []
    conv = get_store().get(user_col(uid, CONVERSATIONS), conversation_id)  # 없으면 NotFoundError
    # 저장된 근거(trace)는 화면용. 모델에게는 질문·답변 글만 넘긴다(숫자는 매번 도구로 다시 확인).
    return [{"role": m["role"], "content": m["content"]} for m in conv.get("messages", [])[-settings.CHAT_HISTORY_LIMIT:]]


def run_agent(uid: str, messages: list[dict]) -> dict:
    """Function Calling 루프. 모델이 도구를 고르고 → 코드가 실행 → 결과를 보고 모델이 다시 판단."""
    client = _get_client()
    tools = agent_tools.openai_tools()
    trace: list[dict] = []
    actions: list[dict] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "model_calls": 0}
    reply = None

    def call(**extra):
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL, messages=messages, tools=tools,
            max_completion_tokens=settings.OPENAI_MAX_TOKENS, **extra)
        usage["model_calls"] += 1
        u = getattr(resp, "usage", None)
        if u is not None and isinstance(getattr(u, "prompt_tokens", None), int):
            usage["prompt_tokens"] += u.prompt_tokens
            usage["completion_tokens"] += u.completion_tokens
        return resp.choices[0].message

    nudged = False
    for step in range(1, settings.AGENT_MAX_STEPS + 1):
        msg = call(tool_choice="auto")
        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            reply = msg.content
            # 답변 검증: [적용] 버튼을 안내했는데 제안 도구를 부르지 않았으면 화면과 말이 어긋난다 → 한 번만 되돌려 보낸다
            if not nudged and not actions and "[적용]" in (reply or "") and step < settings.AGENT_MAX_STEPS:
                nudged = True
                logger.info("agent step=%s: [적용] 안내했지만 propose_goal 호출 없음 → 재요청", step)
                trace.append({"step": step, "tool": "self_check", "label": "답변 검증",
                              "args": {}, "ok": False, "summary": "제안 도구 호출 없이 [적용]을 안내해 다시 요청"})
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": (
                    "[시스템 검증] 방금 답변은 [적용] 버튼을 안내했지만 propose_goal을 호출하지 않아 화면에 버튼이 없다. "
                    "목표를 제안하려면 propose_goal을 호출한 뒤 다시 답하라. 제안하지 않을 거라면 [적용] 안내를 빼고 답하라.")})
                reply = None
                continue
            break
        # 모델의 '도구를 부르겠다'는 결정을 대화에 남겨야 다음 호출에서 결과와 짝이 맞는다
        messages.append({"role": "assistant", "content": msg.content or None, "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in tool_calls]})
        cap = settings.AGENT_MAX_CALLS_PER_STEP
        for i, tc in enumerate(tool_calls):
            if i >= cap:  # 한 번에 너무 많이 부르면(예: 모든 카테고리 추이) 나머지는 실행하지 않고 이유를 돌려준다
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(
                    {"error": f"한 번에 최대 {cap}개까지만 실행합니다. 질문에 꼭 필요한 것만 골라 부르세요."}, ensure_ascii=False)})
                continue
            r = agent_tools.execute(uid, tc.function.name, tc.function.arguments)
            logger.info("agent step=%s tool=%s ok=%s args=%s → %s", step, r["name"], r["ok"], r["args"], r["summary"])
            trace.append({"step": step, "tool": r["name"], "label": r["label"], "args": r["args"],
                          "ok": r["ok"], "summary": r["summary"]})
            if r["ok"] and r["name"] == "propose_goal":
                actions.append({"type": "goal_proposal", **r["result"]["proposal"]})
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(r["result"], ensure_ascii=False)})
    if reply is None:  # 단계 한도에 닿음 → 지금까지의 결과로 답만 하게 한다
        reply = call(tool_choice="none").content
    return {"reply": (reply or "").strip() or "답변을 생성하지 못했습니다.",
            "trace": trace, "actions": actions, "usage": usage}


# ---------------------------------------------------------------- baseline (이전 방식, 비교용)
BASELINE_TEMPLATE = """당신은 사용자의 소비 습관을 함께 관리하는 AI 절약 코치입니다.
아래는 사용자의 실제 소비 지출 데이터 요약입니다. 금액 단위는 원(KRW)입니다.

[사용자 지출 데이터 요약]
{summary}

[절약 목표]
{goal}

규칙:
- 반드시 위 데이터를 근거로 구체적인 숫자를 들어 답하세요.
- 요약에 없는 정보(예: 특정 날짜의 개별 거래)는 추측하지 말고, 요약으로 알 수 있는 범위를 밝히세요.
- 절약 조언은 카테고리 비중과 추세를 근거로 실천 가능한 형태로 제시하세요.
- 절약 목표가 있으면 목표 대비 진행 상황(사용률, 월말 예상)을 기준으로 조언하세요. 목표가 없으면 목표 설정을 권할 수 있습니다.
- 한국어로, 3~6문장 이내로 간결하게 답하세요."""


def build_system_prompt(summary: dict, goal_text: str = "- 이번 달 절약 목표: 아직 없음") -> str:
    return BASELINE_TEMPLATE.format(summary=summary_service.to_prompt_text(summary), goal=goal_text)


def run_baseline(uid: str, messages: list[dict]) -> dict:
    summary = summary_service.get_summary(uid)
    messages[0] = {"role": "system", "content": build_system_prompt(summary, goal_service.prompt_text(uid))}
    resp = _get_client().chat.completions.create(
        model=settings.OPENAI_MODEL, messages=messages, max_completion_tokens=settings.OPENAI_MAX_TOKENS)
    return {"reply": (resp.choices[0].message.content or "").strip() or "답변을 생성하지 못했습니다.",
            "trace": [], "actions": [], "usage": {"model_calls": 1}}


# ---------------------------------------------------------------- 진입점
def chat(uid: str, message: str, conversation_id: Optional[str] = None, mode: Optional[str] = None) -> dict:
    mode = mode or settings.COACH_MODE
    messages = [{"role": "system", "content": agent_system_prompt(uid) if mode == "agent" else ""},
                *_history(uid, conversation_id), {"role": "user", "content": message}]
    try:
        out = run_agent(uid, messages) if mode == "agent" else run_baseline(uid, messages)
    except ChatError:
        raise
    except Exception as e:  # 네트워크/인증/쿼터 오류 등
        logger.exception("chat failed")
        raise ChatError(f"AI 응답 생성 중 오류: {type(e).__name__}") from e

    # 대화 자동 저장 — 답변과 함께 근거(trace)·제안(actions)도 남겨, 불러온 대화에서도 근거를 보여준다
    new_msgs = [{"role": "user", "content": message},
                {"role": "assistant", "content": out["reply"], "trace": out["trace"], "actions": out["actions"]}]
    if conversation_id:
        conversation_service.append_messages(uid, conversation_id, new_msgs)
    else:
        conversation_id = conversation_service.create_conversation(uid, new_msgs)["id"]

    return {"conversation_id": conversation_id, "reply": out["reply"], "mode": mode,
            "trace": out["trace"], "actions": out["actions"], "usage": out["usage"],
            "summary": summary_service.get_summary(uid)}
