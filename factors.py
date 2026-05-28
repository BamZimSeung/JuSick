# -*- coding: utf-8 -*-
"""멀티팩터 점수 계산.

각 지표를 시장 내 백분위(0~1)로 환산해 팩터 점수를 만들고,
config 가중치로 합산해 종합 점수를 낸다.
- 결측 지표는 랭킹에서 빠지고, 팩터 전체가 결측이면 중립(0.5).
- '낮을수록 좋은' 가치 지표는 음수/0(적자 등)을 제외한다.
"""
import pandas as pd
import config
import themes


def _rank_low_good(s: pd.Series) -> pd.Series:
    """낮을수록 좋은 지표 → 높은 점수. 음수/0은 제외(NaN)."""
    s = pd.to_numeric(s, errors="coerce").where(lambda x: x > 0)
    return 1 - s.rank(pct=True)


def _rank_high_good(s: pd.Series) -> pd.Series:
    """높을수록 좋은 지표 → 높은 점수."""
    s = pd.to_numeric(s, errors="coerce")
    return s.rank(pct=True)


def _avg(*series: pd.Series) -> pd.Series:
    return pd.concat(series, axis=1).mean(axis=1)


def compute_scores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 가치: forwardPE·PSR·PEG (낮을수록 좋음)
    df["score_value"] = _avg(
        _rank_low_good(df["forwardPE"]),
        _rank_low_good(df["priceToSalesTrailing12Months"]),
        _rank_low_good(df["trailingPegRatio"]),
    )
    # 우량: ROE·이익률(높을수록) + 부채비율(낮을수록)
    df["score_quality"] = _avg(
        _rank_high_good(df["returnOnEquity"]),
        _rank_high_good(df["profitMargins"]),
        1 - _rank_high_good(df["debtToEquity"]),
    )
    # 성장: 매출·이익 성장률(높을수록)
    df["score_growth"] = _avg(
        _rank_high_good(df["revenueGrowth"]),
        _rank_high_good(df["earningsGrowth"]),
    )
    # 모멘텀: 3·6개월 수익률 + 52주고가 근접도(높을수록)
    df["score_momentum"] = _avg(
        _rank_high_good(df["ret_3m"]),
        _rank_high_good(df["ret_6m"]),
        _rank_high_good(df["pct_from_high"]),
    )

    sub = ["score_value", "score_quality", "score_growth", "score_momentum"]
    df[sub] = df[sub].fillna(0.5)   # 결측 팩터는 중립

    w = config.FACTOR_WEIGHTS
    df["score_total"] = (
        w["value"] * df["score_value"]
        + w["quality"] * df["score_quality"]
        + w["growth"] * df["score_growth"]
        + w["momentum"] * df["score_momentum"]
    )

    # 테마 매칭 → 테마 태그 + score_total 보너스
    df = themes.match_themes(df)
    df["themes_str"] = df["themes"].apply(lambda xs: ";".join(xs))   # CSV 저장용
    bonus = (df["theme_count"] * config.THEME_BOOST_PER_HIT).clip(upper=config.THEME_BOOST_MAX)
    df["theme_bonus"] = bonus
    df["score_total"] = df["score_total"] + bonus

    return df.sort_values("score_total", ascending=False).reset_index(drop=True)
