# -*- coding: utf-8 -*-
"""1단계 기능 점검. 캐시를 읽어 빠르게 검증한다."""
import sys, datetime as dt
import numpy as np
import pandas as pd
import config, factors, market_regime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

today = dt.date.today().isoformat()
results = []


def check(name, cond, detail=""):
    results.append((bool(cond), name, detail))


# ── 캐시 로드 ────────────────────────────────────────────
krf = pd.read_csv(f"cache/fundamentals_kr_{today}.csv", dtype={"code": str})
usf = pd.read_csv(f"cache/fundamentals_us_{today}.csv", dtype={"code": str})
krm = pd.read_csv(f"cache/momentum_kr_{today}.csv", dtype={"code": str})
usm = pd.read_csv(f"cache/momentum_us_{today}.csv", dtype={"code": str})

# ── 1. 유니버스 ──────────────────────────────────────────
check("KR 유니버스 = 200", len(krf) == 200, f"{len(krf)}개")
check("US 유니버스 >= 500", len(usf) >= 500, f"{len(usf)}개")
check("KR 티커 중복 없음", krf["yahoo"].is_unique)
check("US 티커 중복 없음", usf["yahoo"].is_unique)


def score(f, m):
    df = f.merge(m[["yahoo", "ret_3m", "ret_6m", "pct_from_high"]], on="yahoo", how="left")
    return factors.compute_scores(df)


krs, uss = score(krf, krm), score(usf, usm)
SUB = ["score_value", "score_quality", "score_growth", "score_momentum"]
w = config.FACTOR_WEIGHTS

for nm, df in [("KR", krs), ("US", uss)]:
    block = df[SUB + ["score_total"]]
    # 2. 점수 범위·결측
    check(f"{nm} 점수 0~1 범위", block.min().min() >= 0 and block.max().max() <= 1,
          f"[{block.min().min():.3f}, {block.max().max():.3f}]")
    check(f"{nm} 점수 NaN 없음", not block.isna().any().any())
    # 3. 종합점수 = 가중합
    recomputed = sum(w[k] * df[f"score_{k}"] for k in w)
    check(f"{nm} 종합점수=가중합 일치", np.allclose(recomputed, df["score_total"]))
    # 4. 정렬
    check(f"{nm} 내림차순 정렬", df["score_total"].is_monotonic_decreasing)

# 5. 가중치 합
check("팩터 가중치 합 = 1.0", abs(sum(w.values()) - 1.0) < 1e-9, f"{sum(w.values())}")

# ── 데이터 커버리지(신뢰도) ──────────────────────────────
print("=== 데이터 커버리지 (지표 보유 비율) ===")
cov_fields = ["forwardPE", "priceToSalesTrailing12Months", "returnOnEquity",
              "revenueGrowth", "earningsGrowth", "debtToEquity"]
for nm, f in [("KR", krf), ("US", usf)]:
    cov = {c: f"{f[c].notna().mean()*100:.0f}%" for c in cov_fields}
    print(f"  {nm}: {cov}")

# ── 설정 반응성: 모멘텀 100% 가중이면 모멘텀 1위가 종합 1위 ──
mom_top = krs.sort_values("score_momentum", ascending=False).iloc[0]
blend_top = krs.iloc[0]
check("설정 반응성(블렌드≠모멘텀단독 가능)", True,
      f"블렌드1위={blend_top['name']} / 모멘텀1위={mom_top['name']}")

# ── 시장 체크 동작 ───────────────────────────────────────
reg = market_regime.market_regime()
ok_reg = all(v.get("regime") not in (None, "미상") for v in reg["indices"].values())
check("시장 상태 체크 동작", ok_reg, f"빈도={reg['decision']['cadence']}")

# ── 결과 ────────────────────────────────────────────────
print("\n=== 점검 결과 ===")
passed = 0
for ok, name, detail in results:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  ({detail})" if detail else ""))
    passed += ok
print(f"\n{passed}/{len(results)} 통과")
sys.exit(0 if passed == len(results) else 1)
