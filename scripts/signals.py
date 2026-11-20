"""규칙 기반 해석: 기간별 성과, 리스크 신호판.

임계값은 널리 쓰이는 관례적 기준이며, 투자 판단의 근거가 아니라 참고용입니다.
수준(level): 0 안정 · 1 보통 · 2 경계 · 3 위험
"""

LEVEL_LABEL = ["안정", "보통", "경계", "위험"]


def _find(d, symbol):
    for key in ("indices", "stocks", "macro", "sectors"):
        for q in d.get(key) or []:
            if q.get("symbol") == symbol:
                return q
    return None


# ---------------------------------------------------------------- 기간별 성과

def _krw(r, fx):
    if r is None or fx is None:
        return None
    return ((1 + r / 100) * (1 + fx / 100) - 1) * 100


def performance(d, symbols):
    krw = _find(d, "KRW=X")
    fx = (krw or {}).get("perf") or {}
    rows = []
    for sym in symbols:
        q = _find(d, sym)
        if not q or not q.get("perf"):
            continue
        p = q["perf"]
        rows.append({"name": q["name"], "symbol": sym, "w1": p.get("w1"), "m1": p.get("m1"),
                     "ytd": p.get("ytd"), "ytd_krw": _krw(p.get("ytd"), fx.get("ytd"))})
    return rows, fx.get("ytd")


# ---------------------------------------------------------------- 리스크 신호판

def _band(v, cuts):
    """cuts = [안정 상한, 보통 상한, 경계 상한] (값이 클수록 위험)."""
    for i, c in enumerate(cuts):
        if v < c:
            return i
    return 3


def risk(d):
    out = []
    vix = _find(d, "^VIX")
    if vix:
        out.append({"name": "VIX 변동성", "value": format(vix["close"], ".1f"),
                    "level": _band(vix["close"], [15, 20, 30]),
                    "rule": "15 미만 안정 · 20 이상 경계 · 30 이상 위험"})
    hy = d.get("hy")
    if hy:
        out.append({"name": "하이일드 스프레드", "value": format(hy["value"], ".2f") + "%p",
                    "level": _band(hy["value"], [3.5, 5, 7]),
                    "rule": "3.5%p 미만 안정 · 5 이상 경계 · 7 이상 위험 (" + hy["date"] + ")"})
    ys = {y["name"]: y["value"] for y in d.get("yields") or []}
    if "2년물" in ys and "10년물" in ys:
        sp = (ys["10년물"] - ys["2년물"]) * 100
        out.append({"name": "10년−2년 금리차", "value": format(sp, "+.0f") + "bp",
                    "level": 2 if sp < 0 else 1 if sp < 25 else 0,
                    "rule": "마이너스(역전)면 경기 둔화 경계 신호"})
    for sym, label in (("^GSPC", "S&P 500"), ("^IXIC", "나스닥")):
        q = _find(d, sym)
        if q and q.get("dd52") is not None:
            dd = q["dd52"]
            out.append({"name": label + " 52주 고점 대비", "value": format(dd, "+.1f") + "%",
                        "level": 0 if dd > -5 else 1 if dd > -10 else 2 if dd > -20 else 3,
                        "rule": "−10% 조정 · −20% 약세장 기준"})
    spx = _find(d, "^GSPC")
    if spx and spx.get("vs200") is not None:
        v = spx["vs200"]
        out.append({"name": "S&P 500 200일선 대비", "value": format(v, "+.1f") + "%",
                    "level": 0 if v >= 3 else 1 if v >= 0 else 2 if v >= -5 else 3,
                    "rule": "200일 이동평균 아래면 중장기 추세 약화"})
    for r in out:
        r["label"] = LEVEL_LABEL[r["level"]]
    return out
