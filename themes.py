# -*- coding: utf-8 -*-
"""메가테마 사전 + 종목 매칭.

목적: "효성중공업이 변압기·AI 데이터센터 수요로 크게 된 케이스"처럼,
구조적 메가트렌드와 연결된 종목을 별도 태그·점수로 부각시킨다.
산업 분류·회사명에서 키워드를 찾아 테마를 부여한다(영문·국문 모두 검색).

확장: 새 테마는 THEMES에 한 줄 추가하면 끝. 키워드는 너무 좁으면 0매칭,
너무 넓으면 노이즈 — 정밀도 우선으로 시작하고 추후 보정.
"""
from __future__ import annotations
import re
import pandas as pd


# 테마별 키워드 (소문자로 매칭, 한글·영문 혼합 가능)
THEMES: dict[str, list[str]] = {
    "AI인프라·전력": [
        "변압기", "전선", "전력기기", "송전", "배전", "전력케이블",
        "transformer", "power grid", "electrical equipment", "switchgear",
        "utilities—regulated electric", "grid", "high voltage",
    ],
    "방산·항공우주": [
        "방산", "항공우주", "미사일", "무기", "탄약",
        "defense", "aerospace", "missile", "munitions", "weapon", "military",
    ],
    "조선·해양": [
        "조선", "해양", "선박",
        "shipbuilding", "shipyard", "marine transportation", "shipping",
    ],
    "원전·SMR": [
        "원전", "원자력",
        "smr", "nuclear", "uranium", "atomic",
    ],
    "로봇·자동화": [
        "로봇", "자동화",
        "robot", "robotics", "automation",
    ],
    "반도체장비·소재": [
        "반도체장비", "반도체 장비", "반도체소재", "반도체 소재",
        "semiconductor equipment", "semiconductor materials",
        "photolithography", "wafer", "hbm",
    ],
    "AI반도체": [
        "ai 반도체", "ai chip", "gpu", "accelerator",
        "ai infrastructure",
    ],
    "2차전지": [
        "2차전지", "배터리", "전지", "양극재", "음극재", "분리막",
        "battery", "lithium", "cathode", "anode", "separator",
    ],
    "바이오·신약": [
        "바이오", "제약", "신약", "비만치료",
        "biotechnology", "drug manufacturers", "pharmaceutical",
        "glp-1", "pharma",
    ],
    "데이터센터·클라우드": [
        "데이터센터", "클라우드",
        "data center", "datacenter", "cloud", "ai cloud",
    ],
    "우주·위성": [
        "우주", "위성", "로켓", "발사체",
        "space", "satellite", "rocket", "launch",
    ],
    "전기차·자율주행": [
        "전기차", "자율주행", "ev", "충전",
        "electric vehicle", "autonomous", "ev charging",
    ],
    "신재생·태양광": [
        "태양광", "풍력", "수소", "신재생",
        "solar", "wind", "hydrogen", "renewable",
    ],
}


def _normalize(text) -> str:
    if pd.isna(text):
        return ""
    return str(text).lower().strip()


def match_themes_one(row: pd.Series) -> list[str]:
    """한 종목 → 매칭된 테마 이름 리스트."""
    haystack = " ".join([
        _normalize(row.get("industry", "")),
        _normalize(row.get("sector", "")),
        _normalize(row.get("name", "")),
        _normalize(row.get("longName", "")),
        _normalize(row.get("shortName", "")),
    ])
    if not haystack.strip():
        return []
    hits = []
    for theme, kws in THEMES.items():
        for kw in kws:
            if kw.lower() in haystack:
                hits.append(theme)
                break
    return hits


def match_themes(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame 각 행에 themes 컬럼(리스트) 추가."""
    df = df.copy()
    df["themes"] = df.apply(match_themes_one, axis=1)
    df["theme_count"] = df["themes"].apply(len)
    return df


# ── 동반강세 발굴 ─────────────────────────────────────────
def discover_hot_themes(
    scored_df: pd.DataFrame,
    group_col: str = "industry",
    min_stocks: int = 3,
    top_n: int = 5,
    momentum_col: str = "score_momentum",
) -> pd.DataFrame:
    """같은 산업의 여러 종목이 동시에 강세인 그룹을 찾는다.

    부상 중인 테마의 후행 신호 — 솔로 급등이 아니라 산업 전체가 움직일 때만 잡힌다.
    """
    df = scored_df.copy()
    df = df[df[group_col].notna() & (df[group_col].astype(str).str.strip() != "")]
    if df.empty:
        return pd.DataFrame(columns=[group_col, "n_stocks", "median_momentum",
                                     "median_ret_6m", "reps"])

    grp = (df.groupby(group_col)
           .agg(n_stocks=("code", "count"),
                median_momentum=(momentum_col, "median"),
                median_ret_6m=("ret_6m", "median"))
           .reset_index())
    grp = grp[grp["n_stocks"] >= min_stocks]
    grp = grp.sort_values("median_momentum", ascending=False).head(top_n)

    # 그룹별 모멘텀 상위 3종목을 대표로
    def reps_for(g):
        sub = df[df[group_col] == g].sort_values(momentum_col, ascending=False).head(3)
        return [(str(n), str(c)) for n, c in zip(sub["name"], sub["code"])]

    grp["reps"] = grp[group_col].map(reps_for)
    # CSV 저장용 문자열 (e.g. "삼성전자|005930;SK하이닉스|000660")
    grp["reps_str"] = grp["reps"].apply(
        lambda xs: ";".join(f"{n}|{c}" for n, c in xs)
    )
    return grp.reset_index(drop=True)


if __name__ == "__main__":
    # 간단 점검
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    samples = pd.DataFrame([
        {"name": "효성중공업", "industry": "Electrical Equipment & Parts", "sector": "Industrials"},
        {"name": "한화에어로스페이스", "industry": "Aerospace & Defense", "sector": "Industrials"},
        {"name": "HD현대중공업", "industry": "Shipbuilding", "sector": "Industrials"},
        {"name": "삼성전자", "industry": "Semiconductors", "sector": "Technology"},
        {"name": "NVIDIA", "industry": "Semiconductors", "sector": "Technology", "longName": "NVIDIA Corporation GPU AI"},
    ])
    out = match_themes(samples)
    for _, r in out.iterrows():
        print(f"{r['name']:20s} → {r['themes']}")
