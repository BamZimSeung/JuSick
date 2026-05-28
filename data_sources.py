# -*- coding: utf-8 -*-
"""데이터 수집 계층.

- 유니버스: FinanceDataReader (한국 코스피/코스닥, 미국 S&P500)
- 펀더멘털: yfinance .info  (한국·미국 통일)
- 모멘텀:  yfinance 가격 일괄 다운로드
캐싱으로 yfinance 호출을 줄인다.
"""
from __future__ import annotations
import os, time, datetime as dt
import pandas as pd
import FinanceDataReader as fdr
import yfinance as yf

import config

os.makedirs(config.CACHE_DIR, exist_ok=True)

# 펀더멘털에서 뽑을 yfinance .info 필드
_FUND_FIELDS = [
    "shortName", "longName", "sector", "industry", "marketCap", "currentPrice",
    "forwardPE", "priceToSalesTrailing12Months", "trailingPegRatio",     # 가치
    "returnOnEquity", "profitMargins", "debtToEquity",                    # 우량
    "revenueGrowth", "earningsGrowth",                                    # 성장
    "trailingPE", "priceToBook",                                          # (미국 보조)
]


# ── 캐시 유틸 ────────────────────────────────────────────
def _cache_path(name: str) -> str:
    return os.path.join(config.CACHE_DIR, name)


def _is_fresh(path: str) -> bool:
    if not os.path.exists(path):
        return False
    age_h = (time.time() - os.path.getmtime(path)) / 3600
    return age_h < config.CACHE_HOURS


# ── 야후 티커 매핑 ───────────────────────────────────────
def _yahoo_kr(code: str, market: str) -> str:
    suffix = ".KQ" if str(market).upper().startswith("KOSDAQ") else ".KS"
    return f"{str(code).zfill(6)}{suffix}"


def _yahoo_us(symbol: str) -> str:
    return str(symbol).replace(".", "-")  # BRK.B -> BRK-B


# ── 유니버스 ─────────────────────────────────────────────
def get_kr_universe(size: int = None) -> pd.DataFrame:
    """코스피+코스닥 시총 상위 보통주 N개."""
    size = size or config.KR_UNIVERSE_SIZE
    frames = []
    for mkt in ["KOSPI", "KOSDAQ"]:
        df = fdr.StockListing(mkt)
        df = df.rename(columns={"Code": "code", "Name": "name", "Marcap": "marcap"})
        df["market"] = mkt
        frames.append(df[["code", "name", "market", "marcap"]])
    uni = pd.concat(frames, ignore_index=True)

    # 보통주만(코드 끝 0), 스팩 제외, 최소 시총 필터
    uni = uni[uni["code"].astype(str).str.endswith("0")]
    uni = uni[~uni["name"].str.contains("스팩", na=False)]
    uni = uni[uni["marcap"].fillna(0) >= config.KR_MIN_MARCAP]
    uni = uni.sort_values("marcap", ascending=False).head(size).reset_index(drop=True)
    uni["yahoo"] = [_yahoo_kr(c, m) for c, m in zip(uni["code"], uni["market"])]
    return uni


def get_us_universe() -> pd.DataFrame:
    """S&P500 구성종목."""
    df = fdr.StockListing("S&P500")
    df.columns = [c.lower() for c in df.columns]
    sym_col = "symbol" if "symbol" in df.columns else df.columns[0]
    name_col = "name" if "name" in df.columns else sym_col
    out = pd.DataFrame({
        "code": df[sym_col].astype(str),
        "name": df[name_col].astype(str),
        "market": "S&P500",
    })
    out["marcap"] = pd.NA          # 미국은 yfinance marketCap으로 채움
    out["yahoo"] = out["code"].map(_yahoo_us)
    return out


# ── 펀더멘털 ─────────────────────────────────────────────
def _fetch_one_info(yahoo: str) -> dict:
    for attempt in range(config.YF_RETRY + 1):
        try:
            info = yf.Ticker(yahoo).info or {}
            return {f: info.get(f) for f in _FUND_FIELDS}
        except Exception:
            if attempt < config.YF_RETRY:
                time.sleep(0.6)
    return {f: None for f in _FUND_FIELDS}


def fetch_fundamentals(uni: pd.DataFrame, tag: str) -> pd.DataFrame:
    """유니버스 각 종목의 펀더멘털 수집(캐시 사용)."""
    today = dt.date.today().isoformat()
    cache = _cache_path(f"fundamentals_{tag}_{today}.csv")
    if _is_fresh(cache):
        return pd.read_csv(cache, dtype={"code": str})

    records = []
    n = len(uni)
    for i, row in uni.reset_index(drop=True).iterrows():
        data = _fetch_one_info(row["yahoo"])
        data.update({"code": row["code"], "name": row["name"],
                     "market": row["market"], "yahoo": row["yahoo"]})
        records.append(data)
        if (i + 1) % 25 == 0:
            print(f"  [{tag}] 펀더멘털 {i + 1}/{n}")
        time.sleep(config.YF_SLEEP)

    out = pd.DataFrame(records)
    out.to_csv(cache, index=False, encoding="utf-8-sig")
    return out


# ── 모멘텀(가격) ─────────────────────────────────────────
def fetch_momentum(uni: pd.DataFrame, tag: str) -> pd.DataFrame:
    """일괄 가격 다운로드 → 3·6개월 수익률, 52주 고가 근접도."""
    today = dt.date.today().isoformat()
    cache = _cache_path(f"momentum_{tag}_{today}.csv")
    if _is_fresh(cache):
        return pd.read_csv(cache, dtype={"code": str})

    tickers = uni["yahoo"].tolist()
    px = yf.download(tickers, period="1y", interval="1d",
                     auto_adjust=True, progress=False, threads=True)["Close"]
    if isinstance(px, pd.Series):       # 단일 종목 방어
        px = px.to_frame()

    rows = []
    for _, row in uni.iterrows():
        y = row["yahoo"]
        s = px[y].dropna() if y in px.columns else pd.Series(dtype=float)
        rec = {"code": row["code"], "yahoo": y,
               "ret_3m": None, "ret_6m": None, "pct_from_high": None}
        if len(s) > 130:
            last = s.iloc[-1]
            rec["ret_3m"] = last / s.iloc[-63] - 1
            rec["ret_6m"] = last / s.iloc[-126] - 1
            rec["pct_from_high"] = last / s.max()
        rows.append(rec)

    out = pd.DataFrame(rows)
    out.to_csv(cache, index=False, encoding="utf-8-sig")
    return out
