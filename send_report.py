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


def _latest_pair(market: str):
    """picks_{market}_*.csv 중 growth가 아닌 최신본과 growth 최신본."""
    files = sorted(glob.glob(f"{config.CACHE_DIR}/picks_{market}_*.csv"))
    main = [f for f in files if "_growth_" not in f]
    growth = [f for f in files if "_growth_" in f]
    return (main[-1] if main else None), (growth[-1] if growth else None)


def main():
    krp, krg = _latest_pair("kr")
    usp, usg = _latest_pair("us")
    if not krp or not usp:
        print("종합 추천 파일이 없습니다. 먼저 `python run.py` 를 실행하세요.")
        return

    note = ""
    try:
        import market_regime
        d = market_regime.market_regime()["decision"]
        note = f"🌡 시장 상태: {d['cadence']} — {d['action']}"
    except Exception:
        pass

    kr = pd.read_csv(krp, dtype={"code": str})
    us = pd.read_csv(usp, dtype={"code": str})
    # 1) 한국 종합 (cadence note 포함)
    notify.send_telegram(report.build_message("🇰🇷 한국", kr, note, _date_of(krp)))
    # 2) 한국 성장 단일축
    if krg:
        krg_df = pd.read_csv(krg, dtype={"code": str})
        notify.send_telegram(report.build_growth_message("🇰🇷 한국", krg_df, _date_of(krg)))
    # 3) 한국 동반강세 산업
    krh = _latest("hot_themes_kr_*.csv")
    if krh:
        try:
            krh_df = pd.read_csv(krh)
            if not krh_df.empty:
                notify.send_telegram(report.build_discovery_message("🇰🇷 한국", krh_df, _date_of(krh)))
        except Exception as e:
            print(f"한국 동반강세 발송 스킵: {e}")
    # 4) 미국 종합
    notify.send_telegram(report.build_message("🇺🇸 미국", us, "", _date_of(usp)))
    # 5) 미국 성장 단일축
    if usg:
        usg_df = pd.read_csv(usg, dtype={"code": str})
        notify.send_telegram(report.build_growth_message("🇺🇸 미국", usg_df, _date_of(usg)))
    # 6) 미국 동반강세 산업
    ush = _latest("hot_themes_us_*.csv")
    if ush:
        try:
            ush_df = pd.read_csv(ush)
            if not ush_df.empty:
                notify.send_telegram(report.build_discovery_message("🇺🇸 미국", ush_df, _date_of(ush)))
        except Exception as e:
            print(f"미국 동반강세 발송 스킵: {e}")

    print(f"발송 완료: 종합({krp}, {usp}) / 성장({krg}, {usg}) / 동반강세({krh}, {ush})")


if __name__ == "__main__":
    main()
