# -*- coding: utf-8 -*-
"""추천 결과 → 텔레그램 메시지 포맷.

종목별: 종합점수 · 팩터 강점 태그 · 핵심 지표.
헤더: 시장 상태(체온)와 발송 빈도.
"""
import sys, datetime as dt, html
import pandas as pd
import config

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _per(x):
    return f"{x:.1f}배" if pd.notna(x) else "—"


def _signed_pct(x):
    """등락률 — 부호 포함 (+69%, -3%)."""
    return f"{x*100:+.0f}%" if pd.notna(x) else "—"


def _roe(x):
    """수익성(ROE). 비정상적으로 큰 값은 상한 표시."""
    if pd.isna(x):
        return "—"
    v = x * 100
    return "300%↑" if v > 300 else f"{v:.0f}%"


def _highlights(r):
    tags = []
    if r["score_value"] >= 0.70:
        tags.append("저평가")
    if r["score_quality"] >= 0.70:
        tags.append("우량")
    if r["score_growth"] >= 0.70:
        tags.append("고성장")
    if r["score_momentum"] >= 0.70:
        tags.append("강한 상승세")
    return " · ".join(tags) if tags else "균형형"


# yfinance 영문 업종 → 한국어 (없으면 원문 표시)
INDUSTRY_KO = {
    "Semiconductors": "반도체",
    "Semiconductor Equipment & Materials": "반도체 장비·소재",
    "Consumer Electronics": "전자제품",
    "Computer Hardware": "컴퓨터·저장장치",
    "Electronic Components": "전자부품",
    "Electronic Gaming & Multimedia": "게임",
    "Software—Infrastructure": "소프트웨어",
    "Software—Application": "소프트웨어",
    "Internet Content & Information": "인터넷·콘텐츠",
    "Steel": "철강",
    "Solar": "태양광",
    "Airlines": "항공",
    "Auto Parts": "자동차 부품",
    "Auto Manufacturers": "자동차",
    "Insurance—Life": "생명보험",
    "Insurance—Diversified": "보험",
    "Insurance—Property & Casualty": "손해보험",
    "Capital Markets": "증권·자본시장",
    "Asset Management": "자산운용",
    "Banks—Regional": "은행",
    "Electrical Equipment & Parts": "전기장비",
    "Specialty Industrial Machinery": "산업기계",
    "Conglomerates": "지주·복합기업",
    "Telecom Services": "통신",
    "Biotechnology": "바이오",
    "Drug Manufacturers—General": "제약",
    "Aerospace & Defense": "항공우주·방산",
    "Specialty Chemicals": "특수화학",
    "Chemicals": "화학",
    "Building Products & Equipment": "건자재",
}


def _business(r):
    """회사 업종 한 줄. 영문이면 한국어로 변환, 매핑 없으면 원문."""
    for key in ("industry", "sector"):
        v = r.get(key)
        if pd.notna(v) and str(v).strip():
            return INDUSTRY_KO.get(str(v), str(v))
    return "—"


LEGEND = (
    "📖 <b>용어 설명</b>\n"
    "· PER : 주가가 한 해 이익의 몇 배인지 — 낮을수록 저평가\n"
    "· 수익성(ROE) : 자기 돈으로 얼마나 버는지 — 높을수록 우량\n"
    "· 매출성장 : 1년 전보다 매출이 늘어난 비율\n"
    "· 6개월 주가 : 최근 6개월간 주가가 오르내린 비율"
)


def build_message(label, df, regime_note="", date_str=None):
    date_str = date_str or dt.date.today().isoformat()
    out = [f"📊 <b>{label} 추천 {len(df)}종목</b>", f"📅 {date_str}"]
    if regime_note:
        out.append(regime_note)
    out += ["", LEGEND, ""]
    for i, (_, r) in enumerate(df.iterrows(), 1):
        name = html.escape(str(r["name"]))
        code = html.escape(str(r["code"]))
        out.append("━━━━━━━━━━━━━━")
        out.append(f"<b>{i}. {name}</b>  ({code})")
        out.append(f"💼 {_business(r)}")
        out.append(f"종합점수 {r['score_total']:.2f} / 1.00")
        out.append(f"🏷 {_highlights(r)}")
        out.append(f"· PER  {_per(r['forwardPE'])}")
        out.append(f"· 수익성(ROE)  {_roe(r['returnOnEquity'])}")
        out.append(f"· 매출성장  {_signed_pct(r['revenueGrowth'])}")
        out.append(f"· 최근 6개월 주가  {_signed_pct(r['ret_6m'])}")
        out.append("")
    return "\n".join(out).strip()


def build_reports():
    today = dt.date.today().isoformat()
    kr = pd.read_csv(f"{config.CACHE_DIR}/picks_kr_{today}.csv", dtype={"code": str})
    us = pd.read_csv(f"{config.CACHE_DIR}/picks_us_{today}.csv", dtype={"code": str})
    note = ""
    try:
        import market_regime
        d = market_regime.market_regime()["decision"]
        note = f"🌡 시장 상태: {d['cadence']} — {d['action']}"
    except Exception:
        pass
    return build_message("🇰🇷 한국", kr, note), build_message("🇺🇸 미국", us, note)


if __name__ == "__main__":
    kr_msg, us_msg = build_reports()
    print(kr_msg)
    print("\n" + "=" * 45 + "\n")
    print(us_msg)
