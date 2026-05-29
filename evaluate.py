# -*- coding: utf-8 -*-
"""KRX 마감 1시간 7분 후(16:37 KST) 실행되는 평가기.

흐름:
  1. evaluation/predictions/kr_{today}.csv 읽기 (없으면 평온/휴장 — 스킵)
  2. 픽 종목들의 당일 종가 + KOSPI 종가를 yfinance로 수집
  3. 종목 일간수익률, KOSPI 일간수익률, 알파(수익률 - KOSPI) 계산
  4. evaluation/results/kr_{today}.csv 저장 + evaluation/history.csv에 append
  5. 텔레그램 한 줄: 종합/성장 적중률·평균 알파·score-수익률 상관
  6. 금요일이면 주간 리포트 추가 전송 (지난 5거래일)

오류 시 텔레그램으로 알림 후 종료.
"""
from __future__ import annotations
import os, sys, glob, traceback
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KST = timezone(timedelta(hours=9))
EVAL_DIR = "evaluation"
PRED_DIR = f"{EVAL_DIR}/predictions"
RES_DIR = f"{EVAL_DIR}/results"
HIST_PATH = f"{EVAL_DIR}/history.csv"
KOSPI_TICKER = "^KS11"


# ── yfinance 종가 조회 ────────────────────────────────────────
def _last_two_closes(ticker: str) -> Optional[tuple[float, float, str]]:
    """ticker의 최근 2거래일 종가 (prev, today, today_date_str)를 반환.

    오늘 데이터가 아직 없으면 None.
    """
    import yfinance as yf
    try:
        hist = yf.Ticker(ticker).history(period="7d", auto_adjust=True)
    except Exception:
        return None
    if hist is None or hist.empty or len(hist) < 2:
        return None
    closes = hist["Close"].dropna()
    if len(closes) < 2:
        return None
    prev = float(closes.iloc[-2])
    last = float(closes.iloc[-1])
    last_date = closes.index[-1].date().isoformat()
    if prev <= 0:
        return None
    return prev, last, last_date


def _ret(prev: float, last: float) -> float:
    return last / prev - 1.0


# ── 평가 본체 ─────────────────────────────────────────────────
def evaluate_today(today_str: str) -> Optional[pd.DataFrame]:
    """오늘자 predictions가 있으면 평가 DF를 반환. 없으면 None."""
    pred_path = f"{PRED_DIR}/kr_{today_str}.csv"
    if not os.path.exists(pred_path):
        print(f"predictions 없음: {pred_path} — 평가 스킵")
        return None

    preds = pd.read_csv(pred_path, dtype={"code": str})
    if preds.empty:
        print("predictions 비어있음 — 스킵")
        return None

    # KOSPI 알파 기준
    kospi = _last_two_closes(KOSPI_TICKER)
    if kospi is None:
        print(f"KOSPI 종가 미확정 — KRX 휴장 또는 데이터 지연 가능")
        return None
    kospi_prev, kospi_last, kospi_date = kospi
    kospi_ret = _ret(kospi_prev, kospi_last)
    print(f"KOSPI {kospi_date}: {kospi_prev:.2f} → {kospi_last:.2f} ({kospi_ret*100:+.2f}%)")

    if kospi_date != today_str:
        print(f"오늘 KRX 데이터 아직 — KOSPI 마지막 {kospi_date}, 예상 {today_str}. 평가 스킵.")
        return None

    # yahoo 컬럼이 predictions에 이미 있음
    rows = []
    for _, p in preds.iterrows():
        y = p.get("yahoo")
        if not isinstance(y, str) or not y:
            continue
        closes = _last_two_closes(y)
        if closes is None:
            print(f"  종가 미확정: {p['code']} {p.get('name')}")
            continue
        prev, last, dstr = closes
        if dstr != today_str:
            print(f"  데이터 지연: {p['code']} {p.get('name')} 마지막 {dstr}")
            continue
        ret = _ret(prev, last)
        rows.append({
            "date": today_str,
            "code": p["code"],
            "name": p.get("name"),
            "pick_type": p.get("pick_type"),
            "score_total": p.get("score_total"),
            "score_value": p.get("score_value"),
            "score_quality": p.get("score_quality"),
            "score_growth": p.get("score_growth"),
            "score_momentum": p.get("score_momentum"),
            "prev_close": prev,
            "close": last,
            "ret": ret,
            "kospi_ret": kospi_ret,
            "alpha": ret - kospi_ret,
        })

    if not rows:
        print("평가 가능한 종목 없음 — 스킵")
        return None
    return pd.DataFrame(rows)


# ── 통계 ──────────────────────────────────────────────────────
def _stats_block(df: pd.DataFrame, label: str) -> str:
    sub = df[df["pick_type"] == label]
    if sub.empty:
        return f"<b>{label}</b>: 평가 없음"
    n = len(sub)
    hit = (sub["alpha"] > 0).sum()
    hit_rate = hit / n * 100
    mean_alpha = sub["alpha"].mean() * 100
    mean_ret = sub["ret"].mean() * 100
    # score_total↔수익률 spearman (가능한 경우)
    rho = ""
    try:
        if sub["score_total"].notna().sum() >= 3:
            r = sub[["score_total", "ret"]].corr(method="spearman").iloc[0, 1]
            if pd.notna(r):
                rho = f" · 상관 {r:+.2f}"
    except Exception:
        pass
    return (f"<b>{label}</b> {n}종목 — 적중률 {hit}/{n} ({hit_rate:.0f}%) · "
            f"평균 알파 {mean_alpha:+.2f}% · 평균 수익 {mean_ret:+.2f}%{rho}")


def _top_bottom(df: pd.DataFrame, k: int = 3) -> str:
    top = df.nlargest(k, "alpha")
    bot = df.nsmallest(k, "alpha")
    def line(r):
        return f"  {r['name']}({r['code']}) {r['alpha']*100:+.2f}%"
    s = "<b>Top</b>\n" + "\n".join(line(r) for _, r in top.iterrows())
    s += "\n<b>Bottom</b>\n" + "\n".join(line(r) for _, r in bot.iterrows())
    return s


def build_daily_message(df: pd.DataFrame, today_str: str) -> str:
    kospi_ret_pct = df["kospi_ret"].iloc[0] * 100
    lines = [
        f"📊 <b>당일 평가</b> {today_str}",
        f"KOSPI {kospi_ret_pct:+.2f}%",
        _stats_block(df, "종합"),
        _stats_block(df, "성장"),
        "",
        _top_bottom(df, 3),
    ]
    return "\n".join(lines)


# ── 주간 리포트 (금요일) ──────────────────────────────────────
def build_weekly_message(hist: pd.DataFrame, today_str: str) -> Optional[str]:
    """지난 5거래일(오늘 포함) 누적 통계."""
    if hist.empty:
        return None
    hist = hist.copy()
    hist["date"] = pd.to_datetime(hist["date"]).dt.date.astype(str)
    recent_dates = sorted(hist["date"].unique())[-5:]
    sub = hist[hist["date"].isin(recent_dates)]
    if sub.empty:
        return None

    def block(label):
        s = sub[sub["pick_type"] == label]
        if s.empty:
            return f"<b>{label}</b>: 데이터 없음"
        n = len(s)
        hit = (s["alpha"] > 0).sum()
        return (f"<b>{label}</b> n={n} · "
                f"적중률 {hit/n*100:.0f}% · "
                f"평균 알파 {s['alpha'].mean()*100:+.2f}% · "
                f"중위 알파 {s['alpha'].median()*100:+.2f}%")

    # 팩터별 score vs 수익률 상관 (성장 픽 한정)
    growth = sub[sub["pick_type"] == "성장"]
    corr_lines = []
    if len(growth) >= 5:
        for col in ["score_value", "score_quality", "score_growth", "score_momentum"]:
            if col in growth.columns and growth[col].notna().sum() >= 5:
                try:
                    r = growth[[col, "ret"]].corr(method="spearman").iloc[0, 1]
                    if pd.notna(r):
                        corr_lines.append(f"  {col.replace('score_','')}: {r:+.2f}")
                except Exception:
                    pass

    lines = [
        f"📈 <b>주간 리포트</b> ({recent_dates[0]} ~ {recent_dates[-1]})",
        block("종합"),
        block("성장"),
    ]
    if corr_lines:
        lines.append("성장 픽 팩터↔수익률 상관:")
        lines += corr_lines
    return "\n".join(lines)


# ── 영속화 ────────────────────────────────────────────────────
def save_results(df: pd.DataFrame, today_str: str) -> None:
    os.makedirs(RES_DIR, exist_ok=True)
    df.to_csv(f"{RES_DIR}/kr_{today_str}.csv", index=False, encoding="utf-8-sig")

    if os.path.exists(HIST_PATH):
        hist = pd.read_csv(HIST_PATH, dtype={"code": str})
        hist = hist[hist["date"].astype(str) != today_str]  # 중복 제거 (재실행 대비)
        hist = pd.concat([hist, df], ignore_index=True)
    else:
        hist = df.copy()
    hist.to_csv(HIST_PATH, index=False, encoding="utf-8-sig")
    print(f"저장: {RES_DIR}/kr_{today_str}.csv ({len(df)}건), history {len(hist)}건")


def main() -> int:
    from notify import send_telegram
    try:
        today_str = datetime.now(KST).date().isoformat()
        weekday = datetime.now(KST).weekday()  # 0=월
        print(f"평가 시작: {today_str} (weekday={weekday})")

        df = evaluate_today(today_str)
        if df is None:
            print("당일 평가 데이터 없음 — 종료")
            return 0

        save_results(df, today_str)
        send_telegram(build_daily_message(df, today_str), parse_mode="HTML")
        print("일일 평가 발송 완료")

        # 금요일 주간 리포트
        if weekday == 4 and os.path.exists(HIST_PATH):
            hist = pd.read_csv(HIST_PATH, dtype={"code": str})
            weekly = build_weekly_message(hist, today_str)
            if weekly:
                send_telegram(weekly, parse_mode="HTML")
                print("주간 리포트 발송 완료")
        return 0

    except Exception as e:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        try:
            send_telegram(
                "❌ <b>평가 자동 실행 실패</b>\n"
                f"<pre>{type(e).__name__}: {str(e)[:300]}</pre>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
