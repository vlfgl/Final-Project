"""체험 모드용 가상 소비 데이터 생성기 (2026-05-01 ~ 2026-10-31, 6개월).

- 레코드 1건 = 결제 1건 (date, amount, merchant, category)
- 절약 코치가 할 말이 생기도록 패턴을 심어둔다:
  * 배달: 최근 3개월 동안 빈도가 늘어남 (과소비 탐지 대상)
  * 카페: 평일 거의 매일 (습관성 소비)
  * 8월 여름휴가, 9월 추석 무렵 지출 증가
- 재현 가능하도록 seed 고정

실행: python scripts/generate_data.py  →  data/sample_transactions.csv
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 2026
START = date(2026, 5, 1)
END = date(2026, 10, 31)
OUT = Path(__file__).resolve().parent.parent / "data" / "sample_transactions.csv"

# (카테고리, 가맹점 후보, 최소, 최대, 평일 확률, 주말 확률)
VARIABLE = [
    ("식비", ["김밥천국", "한솥도시락", "본죽", "서브웨이", "학생식당", "버거킹", "맘스터치"], 6000, 14000, 0.75, 0.35),
    ("식비", ["교촌치킨", "아웃백스테이크하우스", "이자카야 하루", "삼겹살 한마당"], 18000, 60000, 0.05, 0.22),
    ("카페·간식", ["스타벅스", "메가MGC커피", "투썸플레이스", "이디야커피", "배스킨라빈스"], 2000, 8500, 0.8, 0.45),
    ("장보기·생활", ["GS25", "CU", "세븐일레븐"], 1500, 9000, 0.35, 0.3),
    ("장보기·생활", ["이마트", "홈플러스", "다이소", "올리브영"], 8000, 70000, 0.04, 0.25),
    ("교통", ["티머니 교통카드"], 1400, 2900, 0.85, 0.3),
    ("교통", ["카카오T 택시"], 6000, 22000, 0.07, 0.12),
    ("쇼핑", ["쿠팡", "무신사", "29CM", "11번가"], 12000, 90000, 0.06, 0.12),
    ("문화·여가", ["CGV", "인터파크티켓", "교보문고", "볼링장"], 9000, 45000, 0.03, 0.18),
    ("의료·건강", ["온누리약국", "연세내과의원"], 3000, 18000, 0.03, 0.01),
]

# (매월 일자, 카테고리, 가맹점, 금액)
FIXED = [
    (1, "주거·통신", "월세 자동이체", 450000),
    (5, "주거·통신", "SKT 통신요금", 59000),
    (10, "구독", "넷플릭스", 13500),
    (15, "구독", "유튜브 프리미엄", 14900),
    (20, "교육", "토익 인강", 39000),
    (25, "주거·통신", "관리비", 0),
]


def utility(month: int) -> int:
    return {7: 98000, 8: 112000}.get(month, 76000)


def delivery_prob(d: date, weekend: bool) -> float:
    """배달 빈도가 8월부터 눈에 띄게 증가."""
    base = 0.22 if weekend else 0.12
    return base * (1.0 if d.month <= 7 else 1.9)


def multiplier(d: date) -> float:
    m = 1.0
    if d.month == 8 and 1 <= d.day <= 15:   # 여름휴가
        m *= 1.25
    if d.month == 9 and 20 <= d.day <= 30:  # 추석 무렵
        m *= 1.2
    return m


def r100(x: float) -> int:
    return max(100, int(round(x / 100.0)) * 100)


def generate():
    rng = random.Random(SEED)
    rows = []
    d = START
    while d <= END:
        weekend = d.weekday() >= 5
        mult = multiplier(d)
        for day, cat, merchant, amount in FIXED:
            if d.day == day:
                rows.append((d.isoformat(), utility(d.month) if merchant == "관리비" else amount, merchant, cat))
        for cat, merchants, lo, hi, p_wd, p_we in VARIABLE:
            if rng.random() < (p_we if weekend else p_wd):
                rows.append((d.isoformat(), r100(rng.uniform(lo, hi) * mult), rng.choice(merchants), cat))
        if rng.random() < delivery_prob(d, weekend):
            rows.append((d.isoformat(), r100(rng.uniform(16000, 32000)), rng.choice(["배달의민족", "쿠팡이츠", "요기요"]), "배달"))
        d += timedelta(days=1)

    rows += [
        ("2026-06-14", 289000, "애플 공식몰", "쇼핑"),
        ("2026-08-07", 386000, "제주 게스트하우스", "문화·여가"),
        ("2026-08-06", 154000, "제주항공", "교통"),
        ("2026-09-27", 120000, "추석 선물세트", "쇼핑"),
    ]
    rows.sort(key=lambda r: r[0])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "amount", "merchant", "category"])
        w.writerows(rows)
    print(f"{len(rows)}건 생성 → {OUT}")


if __name__ == "__main__":
    generate()
