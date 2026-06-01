# -*- coding: utf-8 -*-
"""1단계 통합 실행: 데이터 → 팩터 점수 → 상위 후보.

사용:
    python run.py            # 전체 유니버스 (한국 200 + 미국 503)
    python run.py --quick    # 소규모 테스트 (각 30종목)
"""
import argparse, datetime as dt, sys
import pandas as pd
import config, data_sources as ds, factors, themes

try:
    sys.stdout.reconfigure(encoding="utf-8")   # 콘솔 한글 출력
except Exception:
    pass

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)

OUT_COLS = ["code", "name", "market", "sector", "industry",
            "score_total", "score_value", "score_quality", "score_growth",
            "score_momentum", "themes_str", "theme_count", "theme_bonus",
            "forwardPE", "returnOnEquity", "revenueGrowth",
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
    # 성장 단일축 Top N — 성장 점수 기준 재정렬
    krg = kr_scored.sort_values("score_growth", ascending=False).head(config.KR_GROWTH_PICKS)
    usg = us_scored.sort_values("score_growth", ascending=False).head(config.US_GROWTH_PICKS)

    today = dt.date.today().isoformat()
    krp[OUT_COLS].to_csv(f"{config.CACHE_DIR}/picks_kr_{today}.csv",
                         index=False, encoding="utf-8-sig")
    usp[OUT_COLS].to_csv(f"{config.CACHE_DIR}/picks_us_{today}.csv",
                         index=False, encoding="utf-8-sig")
    krg[OUT_COLS].to_csv(f"{config.CACHE_DIR}/picks_kr_growth_{today}.csv",
                         index=False, encoding="utf-8-sig")
    usg[OUT_COLS].to_csv(f"{config.CACHE_DIR}/picks_us_growth_{today}.csv",
                         index=False, encoding="utf-8-sig")

    # 동반강세 산업 발굴 (full scored universe 기반)
    HOT_COLS = ["industry", "n_stocks", "median_momentum", "median_ret_6m", "reps_str"]
    kr_hot = themes.discover_hot_themes(
        kr_scored, min_stocks=config.HOT_THEME_MIN_STOCKS, top_n=config.HOT_THEME_TOP_N)
    us_hot = themes.discover_hot_themes(
        us_scored, min_stocks=config.HOT_THEME_MIN_STOCKS, top_n=config.HOT_THEME_TOP_N)
    kr_hot[HOT_COLS].to_csv(f"{config.CACHE_DIR}/hot_themes_kr_{today}.csv",
                            index=False, encoding="utf-8-sig")
    us_hot[HOT_COLS].to_csv(f"{config.CACHE_DIR}/hot_themes_us_{today}.csv",
                            index=False, encoding="utf-8-sig")

    # 관심 테마 조사 (국장) — 로봇·양자·우주
    THEME_OUT_COLS = OUT_COLS + ["watch_theme"]
    kr_theme = themes.pick_by_themes(
        kr_scored, config.THEME_WATCH, top_n=config.THEME_PICKS_TOP_N)
    # 매칭 0이어도 헤더만 남겨 저장 (발송 측이 '없음' 표기)
    kr_theme = kr_theme.reindex(columns=THEME_OUT_COLS)
    kr_theme.to_csv(f"{config.CACHE_DIR}/theme_picks_kr_{today}.csv",
                    index=False, encoding="utf-8-sig")

    show = ["code", "score_total", "score_value", "score_quality",
            "score_growth", "score_momentum", "forwardPE",
            "returnOnEquity", "revenueGrowth", "ret_6m"]
    print("\n========== 한국 종합 추천 ==========")
    print(krp[show].round(3).to_string())
    print("\n========== 한국 성장 단일축 추천 ==========")
    print(krg[show].round(3).to_string())
    print("\n========== 미국 종합 추천 ==========")
    print(usp[show].round(3).to_string())
    print("\n========== 미국 성장 단일축 추천 ==========")
    print(usg[show].round(3).to_string())
    print("\n========== 한국 동반강세 산업 ==========")
    print(kr_hot[["industry", "n_stocks", "median_momentum", "median_ret_6m"]].round(3).to_string())
    print("\n========== 미국 동반강세 산업 ==========")
    print(us_hot[["industry", "n_stocks", "median_momentum", "median_ret_6m"]].round(3).to_string())
    print("\n========== 한국 관심 테마 조사 (로봇·양자·우주) ==========")
    if kr_theme.dropna(how="all").empty:
        print("매칭 종목 없음")
    else:
        print(kr_theme[["watch_theme", "code", "name", "score_total", "score_momentum", "ret_6m"]].round(3).to_string())
    print(f"\n결과 저장: cache/picks_(kr|us)(_growth)?_{today}.csv , hot_themes_(kr|us)_{today}.csv")


if __name__ == "__main__":
    main()
