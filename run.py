# -*- coding: utf-8 -*-
"""1단계 통합 실행: 데이터 → 팩터 점수 → 상위 후보.

사용:
    python run.py            # 전체 유니버스 (한국 200 + 미국 503)
    python run.py --quick    # 소규모 테스트 (각 30종목)
"""
import argparse, datetime as dt, sys
import pandas as pd
import config, data_sources as ds, factors

try:
    sys.stdout.reconfigure(encoding="utf-8")   # 콘솔 한글 출력
except Exception:
    pass

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)

OUT_COLS = ["code", "name", "market", "sector", "industry",
            "score_total", "score_value", "score_quality", "score_growth",
            "score_momentum", "forwardPE", "returnOnEquity", "revenueGrowth",
            "earningsGrowth", "ret_6m", "marketCap"]


def build(uni: pd.DataFrame, tag: str) -> pd.DataFrame:
    fund = ds.fetch_fundamentals(uni, tag)
    mom = ds.fetch_momentum(uni, tag)
    df = fund.merge(mom[["yahoo", "ret_3m", "ret_6m", "pct_from_high"]],
                    on="yahoo", how="left")
    return factors.compute_scores(df)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="각 30종목으로 빠른 테스트")
    args = ap.parse_args()

    kr = ds.get_kr_universe()
    us = ds.get_us_universe()
    suffix = ""
    if args.quick:
        kr, us = kr.head(30), us.head(30)
        suffix = "_quick"
    print(f"유니버스: 한국 {len(kr)} / 미국 {len(us)}")

    kr_scored = build(kr, "kr" + suffix)
    us_scored = build(us, "us" + suffix)
    # 미국 소형주 제외
    us_scored = us_scored[us_scored["marketCap"].fillna(0) >= config.US_MIN_MARCAP]

    krp = kr_scored.head(config.KR_PICKS)
    usp = us_scored.head(config.US_PICKS)

    today = dt.date.today().isoformat()
    krp[OUT_COLS].to_csv(f"{config.CACHE_DIR}/picks_kr_{today}.csv",
                         index=False, encoding="utf-8-sig")
    usp[OUT_COLS].to_csv(f"{config.CACHE_DIR}/picks_us_{today}.csv",
                         index=False, encoding="utf-8-sig")

    show = ["code", "score_total", "score_value", "score_quality",
            "score_growth", "score_momentum", "forwardPE",
            "returnOnEquity", "revenueGrowth", "ret_6m"]
    print("\n========== 한국 추천 후보 ==========")
    print(krp[show].round(3).to_string())
    print("\n========== 미국 추천 후보 ==========")
    print(usp[show].round(3).to_string())
    print(f"\n결과 저장: cache/picks_kr_{today}.csv , cache/picks_us_{today}.csv")


if __name__ == "__main__":
    main()
