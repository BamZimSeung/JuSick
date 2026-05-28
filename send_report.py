# -*- coding: utf-8 -*-
"""추천 리포트를 텔레그램으로 발송.

가장 최근 생성된 picks 파일을 자동으로 골라 보낸다(오늘자 있으면 오늘자).
헤더 날짜는 파일명에서 추출한 실제 데이터 날짜를 사용한다.
3단계 자동화(스케줄)에서도 이 스크립트를 호출한다.
"""
import sys, re, glob
import pandas as pd
import config, report, notify

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _latest(pattern):
    files = sorted(glob.glob(f"{config.CACHE_DIR}/{pattern}"))
    return files[-1] if files else None


def _date_of(path):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path or "")
    return m.group(1) if m else None


def main():
    krp, usp = _latest("picks_kr_*.csv"), _latest("picks_us_*.csv")
    if not krp or not usp:
        print("추천 파일이 없습니다. 먼저 `python run.py` 를 실행하세요.")
        return

    kr = pd.read_csv(krp, dtype={"code": str})
    us = pd.read_csv(usp, dtype={"code": str})

    note = ""
    try:
        import market_regime
        d = market_regime.market_regime()["decision"]
        note = f"🌡 시장 상태: {d['cadence']} — {d['action']}"
    except Exception:
        pass

    notify.send_telegram(report.build_message("🇰🇷 한국", kr, note, _date_of(krp)))
    notify.send_telegram(report.build_message("🇺🇸 미국", us, note, _date_of(usp)))
    print(f"발송 완료: {krp} / {usp}")


if __name__ == "__main__":
    main()
