# -*- coding: utf-8 -*-
"""시장 상태(체온) 매일 체크.

지수의 추세(MA120 상회)·변동성(20일)·고점대비 낙폭으로 큰 흐름을 판정하고,
추천 발송 빈도(cadence)를 결정한다.  ※ 이 체크 자체는 매일 실행한다.
"""
import numpy as np
import pandas as pd
import FinanceDataReader as fdr
import yfinance as yf

ANNUALIZE = np.sqrt(252)


def _series_fdr(symbol: str, n: int = 400) -> pd.Series:
    return fdr.DataReader(symbol)["Close"].dropna().tail(n)


def _series_yf(symbol: str, n: int = 400) -> pd.Series:
    return yf.Ticker(symbol).history(period="2y")["Close"].dropna().tail(n)


def assess_index(close: pd.Series) -> dict:
    """단일 지수의 상태를 판정한다."""
    close = close.dropna()
    last = close.iloc[-1]
    ma120 = close.tail(120).mean()
    high_1y = close.tail(252).max()
    drawdown = last / high_1y - 1
    ret_1m = (last / close.iloc[-21] - 1) if len(close) > 21 else np.nan
    vol = close.pct_change().dropna().tail(20).std() * ANNUALIZE
    above_ma = bool(last >= ma120)

    if drawdown <= -0.15 or (not above_ma and ret_1m <= -0.08):
        regime = "약세"
    elif vol >= 0.25 or drawdown <= -0.08:
        regime = "변동"
    else:
        regime = "평온"
    return dict(last=float(last), ma120=float(ma120), drawdown=float(drawdown),
                ret_1m=float(ret_1m), vol=float(vol), above_ma=above_ma, regime=regime)


def decide_cadence(regimes: dict) -> dict:
    """시장별 상태를 모아 발송 빈도를 정한다(가장 보수적/능동적 쪽 채택)."""
    labels = [v["regime"] for v in regimes.values()]
    if "약세" in labels:
        return dict(cadence="주1회+경계", action="추천 자제·현금비중 점검",
                    note="약세 신호 감지")
    if "변동" in labels:
        return dict(cadence="매일", action="매일 점검·추천 갱신",
                    note="변동성 확대 구간")
    return dict(cadence="주1회", action="주 1회 정기 추천", note="평온 구간")


def market_regime() -> dict:
    out = {}
    try:
        out["KOSPI"] = assess_index(_series_fdr("KS11"))
    except Exception as e:
        out["KOSPI"] = {"regime": "미상", "err": str(e)[:80]}
    try:
        out["S&P500"] = assess_index(_series_yf("^GSPC"))
    except Exception as e:
        out["S&P500"] = {"regime": "미상", "err": str(e)[:80]}

    valid = {k: v for k, v in out.items() if v.get("regime") not in (None, "미상")}
    decision = decide_cadence(valid) if valid else \
        dict(cadence="주1회", action="주 1회 정기 추천", note="지수 데이터 미상")
    return {"indices": out, "decision": decision}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # 콘솔 한글/특수문자 출력
    except Exception:
        pass
    r = market_regime()
    for k, v in r["indices"].items():
        if "drawdown" in v:
            print(f"{k}: {v['regime']} | 고점대비 {v['drawdown']*100:+.1f}% | "
                  f"20일변동성 {v['vol']*100:.1f}% | MA120상회 {v['above_ma']}")
        else:
            print(f"{k}: {v['regime']} ({v.get('err', '')})")
    d = r["decision"]
    print(f"발송빈도: {d['cadence']} — {d['action']} ({d['note']})")
