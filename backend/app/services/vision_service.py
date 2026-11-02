"""멀티모달 AI: 카드 내역 캡처 / 영수증 사진 → 거래 목록(JSON) 추출.

- 이미지 1장 = OpenAI 호출 1번 (실패해도 다른 이미지에 영향 없음)
- Structured Outputs(json_schema, strict)로 응답 형식을 강제 → 파싱 실패 방지
- 여기서는 '읽기'만 한다. 연도 보정·취소 제외·중복 감지 등 판단은 upload_service(코드)가 한다.
"""
import json
from datetime import date

from app.config import settings
from app.schemas import CATEGORIES
from app.services.chat_service import ChatError, _get_client

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["image_type", "transactions"],
    "properties": {
        "image_type": {"type": "string", "enum": ["card_statement", "transaction_detail", "receipt", "other"]},
        "transactions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["year", "month", "day", "weekday", "amount", "merchant", "category", "status", "confidence"],
                "properties": {
                    # 날짜는 '이미지에 보이는 값'만 칸별로. 안 보이면 null → 날짜 계산은 코드가 한다.
                    "year": {"type": ["integer", "null"]},
                    "month": {"type": ["integer", "null"]},
                    "day": {"type": ["integer", "null"]},
                    "weekday": {"type": ["string", "null"], "enum": WEEKDAYS + [None]},
                    "amount": {"type": "integer", "description": "거래 금액(원), 양수. 쉼표·부호·원 제외"},
                    "merchant": {"type": "string"},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "status": {"type": "string", "enum": ["spent", "income", "canceled"]},
                    "confidence": {"type": "string", "enum": ["high", "low"]},
                },
            },
        },
    },
}

PROMPT = """너는 한국 카드·은행·간편결제 앱 화면과 영수증에서 거래를 읽는 도우미다. 보이는 그대로 추출해 JSON으로 답한다.

[이미지 종류 image_type]
- card_statement: 카드·은행·간편결제 앱의 거래 내역 '목록' 화면 (여러 건)
- transaction_detail: 거래 1건의 '상세' 화면 (가맹점명, 거래 일시, 거래 금액 등이 크게 나옴)
- receipt: 종이 또는 전자 영수증
- other: 거래 내역이 아닌 이미지 → transactions는 빈 배열

[status — 돈의 방향]
- spent: 나간 돈(결제·출금·이체 출금). 카드 목록의 부호 없는 금액, 통장의 '-' 금액·'출금'이 여기에 해당한다.
- income: 들어온 돈. 통장의 '+' 금액, '입금', '환불', '급여' 등.
- canceled: 화면에 '취소', '승인취소', '결제취소' 글자가 실제로 있을 때만. '-' 부호만으로 취소라고 판단하지 않는다.

[금액 amount]
- 거래 금액 자체만 양수 정수로. 잔액, 캐시백, 적립, 할인 예정, 포인트, 한도 금액은 거래 금액이 아니다.
- 할부는 전체 금액. 해외 결제는 원화 금액.

[날짜 — 보이는 것만, 추측 금지]
- year, month, day, weekday는 이미지에 실제로 보이는 값만 적는다. 화면에 없으면 반드시 null.
- 목록의 날짜 머리글(예: "10.28 (화)", "15일(목)", "2026년 10월")은 그 아래 행에 적용한다.
- "15일(목)"처럼 일과 요일만 있으면 year=null, month=null, day=15, weekday="목".
- 연도·월을 계산하거나 추측하지 않는다.

[목록 화면]
- 각 행이 거래 1건. 합계, 결제 예정 금액, 광고·혜택 배너, 검색·필터 영역은 넣지 않는다.
- 화면 위아래에서 잘린 행은 가맹점과 금액이 모두 보일 때만 넣는다.

[영수증·상세 화면]
- 상호명(또는 큰 제목)이 merchant, 실제 결제 금액(합계/받을 금액/거래 금액)이 amount.
- 공급가액, 부가세, 개별 품목 금액을 amount로 쓰지 않는다.

[공통]
- merchant는 화면에 적힌 이름 그대로. 카드번호·계좌번호는 적지 않는다.
- category는 다음 중 하나: {categories}
  힌트: 배달의민족·쿠팡이츠·요기요=배달 / 편의점·마트·다이소·올리브영=장보기·생활 / 커피·베이커리·디저트=카페·간식
  / 택시·지하철·버스·교통카드·주유=교통 / 무신사·쿠팡·29CM 등 온라인몰=쇼핑 / 통신요금·관리비·월세=주거·통신
  / 넷플릭스·유튜브·AI 서비스 등 정기 결제(SUB, 구독)=구독 / 병원·약국=의료·건강 / 학원·인강·교재=교육
  / 사람 이름으로 된 이체·입금이나 판단이 어려우면 기타
- 글자가 흐리거나 확실하지 않으면 confidence="low". 값을 지어내지 않는다."""


def extract(data_url: str, today: date) -> dict:
    """이미지 1장에서 거래 후보 추출. 실패 시 ChatError."""
    try:
        resp = _get_client().chat.completions.create(
            model=settings.OPENAI_VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT.format(categories=", ".join(CATEGORIES))},
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                ],
            }],
            response_format={"type": "json_schema", "json_schema": {"name": "extracted", "strict": True, "schema": SCHEMA}},
            max_completion_tokens=settings.VISION_MAX_TOKENS,
            temperature=0,
        )
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)
    except ChatError:
        raise
    except json.JSONDecodeError as e:
        raise ChatError("이미지 인식 결과를 해석하지 못했어요.") from e
    except Exception as e:
        raise ChatError(f"이미지 인식 중 오류: {type(e).__name__}") from e
