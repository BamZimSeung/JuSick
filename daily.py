# -*- coding: utf-8 -*-
"""GitHub Actions에서 매일 호출되는 오케스트레이터.

흐름:
  1. market_regime → cadence 판정
  2. KST 요일 확인
  3. 평온/매일/약세 분기로 발송 결정
  4. 풀 발송이면 run.py + send_report.py 호출
     아니면 짧은 시장 체크 한 줄 또는 약세 경고만 발송
오류 발생 시 텔레그램으로 한국어 알림 1건 보내고 종료.
"""
from __future__ import annotations
import sys, traceback
from datetime import datetime, timezone, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KST = timezone(timedelta(hours=9))


def _regime_line(m: dict) -> str:
    parts = []
    for label, key in [("KOSPI", "KOSPI"), ("S&P500", "S&P500")]:
        v = m["indices"].get(key, {})
        parts.append(f"{label} {v.get('regime', '미상')}")
    return " · ".join(parts)


def main() -> int:
    from notify import send_telegram
    try:
        import market_regime
        regime = market_regime.market_regime()
        cadence = regime["decision"]["cadence"]
        regime_str = _regime_line(regime)
        weekday = datetime.now(KST).weekday()  # 월=0
        is_monday = (weekday == 0)
        print(f"cadence={cadence} | KST weekday={weekday} | regime={regime_str}")

        full_send = (cadence == "매일") or (cadence == "주1회" and is_monday)
        bear = cadence == "주1회+경계"

        if bear:
            send_telegram(
                "⚠ <b>시장 약세 신호</b>\n"
                "추천 발송을 자제합니다. 현금비중 점검을 권고드립니다.\n"
                f"{regime_str}",
                parse_mode="HTML",
            )
            print("발송: 약세 경고")
            return 0

        if not full_send:
            send_telegram(
                "🌡 <b>시장 체크</b>\n"
                "오늘은 평온 구간 — 추천은 월요일에 갱신됩니다.\n"
                f"{regime_str}",
                parse_mode="HTML",
            )
            print("발송: 평온/비월요일 한 줄")
            return 0

        # 풀 발송 — run.py로 점수 산출 → send_report.py로 발송
        import run, send_report
        run.main()           # 내부에서 cache/picks_kr_*.csv, picks_us_*.csv 생성
        send_report.main()   # 최신 picks 자동 선택 → 텔레그램 발송
        print("발송: 풀 추천 리포트")
        return 0

    except Exception as e:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        try:
            send_telegram(
                "❌ <b>추천 자동 발송 실패</b>\n"
                f"<pre>{type(e).__name__}: {str(e)[:300]}</pre>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
