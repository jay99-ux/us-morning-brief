#!/usr/bin/env python3
"""미국장 모닝 브리핑 빌더.

외부 패키지 없이 파이썬 기본 라이브러리만 사용합니다.

1. config.json 에 적힌 항목의 데이터를 받아 data/history/<미국장 날짜>.json 에 저장하고
2. 저장된 모든 기록으로 docs/index.html 과 docs/archive/*.html 을 만듭니다.

사용법:
    python scripts/build.py          # 실제 데이터로 생성
    python scripts/build.py --demo   # 네트워크 없이 샘플 데이터로 화면만 확인 (기록은 build/ 에만 저장)
"""
import json
import os
import random
import shutil
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import headline
import render
import sources

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def collect():
    now = datetime.now(timezone.utc)
    data = {"generated_at": now.isoformat(timespec="seconds")}
    for key in ("indices", "sectors", "stocks", "macro"):
        data[key] = [q for q in (sources.quote(i) for i in CONFIG[key]) if q]
    data["hy"] = sources.fred_level(CONFIG["risk"]["high_yield_fred"])
    data["yields"] = [y for y in (sources.yield_row(i) for i in CONFIG["yields"]) if y]
    data["news"] = sources.news(CONFIG["news_feeds"], CONFIG.get("news_limit", 12), CONFIG.get("news_hours", 30), now)
    data["fed"] = sources.fed(CONFIG["fed_feeds"])
    data["calendar"] = sources.calendar(CONFIG)
    data["market_date"] = market_date(data, now)
    data["headline"] = headline.pick(
        data["news"], data["stocks"], CONFIG["stocks"], os.environ.get("HEADLINE", "")
    ) or headline.fallback(data["indices"])
    return data


def market_date(data, now):
    spx = next((i for i in data["indices"] if i.get("symbol") == "^GSPC"), None)
    if spx:
        return spx["date"]
    dates = [i["date"] for i in data["indices"] + data["sectors"] + data["stocks"]]
    if dates:
        return Counter(dates).most_common(1)[0][0]
    return (now - timedelta(hours=5)).strftime("%Y-%m-%d")  # 미국 동부 날짜 근사치


# ---------------------------------------------------------------- 샘플 데이터

def demo_data(day, seed):
    rnd = random.Random(seed)

    end = date.fromisoformat(day)
    bdays, d = [], end
    while len(bdays) < 260:
        if d.weekday() < 5:
            bdays.append(d.isoformat())
        d -= timedelta(days=1)
    bdays.reverse()

    def fake(items, base_fn, vol):
        out = []
        for n, it in enumerate(items):
            drift = rnd.uniform(-0.0004, 0.0012)
            if it["symbol"] == "KRW=X":
                drift, vol = 0.0002, 0.004
            path = [base_fn(n) * 0.85]
            for _ in range(len(bdays) - 1):
                path.append(path[-1] * (1 + drift + rnd.gauss(0, vol)))
            q = sources._summarize(list(zip(bdays, path)))  # 실제 계산 로직을 그대로 사용
            q["src"] = "demo"
            q.update({k: v for k, v in it.items() if k in ("name", "symbol", "unit", "digits", "role")})
            out.append(q)
        return out

    levels = [52200, 7520, 25060, 2450]
    macro_levels = [68.4, 4120, 1452.3, 99.8, 17.2, 98500]
    gen = datetime.fromisoformat(day + "T22:40:00+00:00")
    data = {
        "generated_at": gen.isoformat(),
        "market_date": day,
        "indices": fake(CONFIG["indices"], lambda n: levels[n % len(levels)], 0.008),
        "hy": {"date": day, "value": round(rnd.uniform(2.8, 3.6), 2), "change": 0.02},
        "sectors": fake(CONFIG["sectors"], lambda n: 100 + n * 7, 0.011),
        "stocks": fake(CONFIG["stocks"], lambda n: 150 + n * 60, 0.018),
        "macro": fake(CONFIG["macro"], lambda n: macro_levels[n % len(macro_levels)], 0.01),
        "yields": [
            {"name": y["name"], "date": day, "value": v + rnd.uniform(-0.05, 0.05), "bp": rnd.randint(-8, 8)}
            for y, v in zip(CONFIG["yields"], (4.02, 4.31, 4.58))
        ],
        "news": [
            {"title": "샘플 헤드라인 " + str(i + 1) + " — 실제 실행 시 언론사 RSS 제목이 들어갑니다",
             "link": "https://www.cnbc.com/", "source": ["CNBC", "MarketWatch", "WSJ 마켓"][i % 3],
             "time": (gen - timedelta(hours=i * 2 + 1)).isoformat()}
            for i in range(6)
        ],
        "fed": [{"group": "통화정책 발표", "items": [
            {"title": "샘플 연준 발표 제목", "link": "https://www.federalreserve.gov/", "date": day}]}],
        "calendar": {"enabled": True, "events": [
            {"date": (date.fromisoformat(day) + timedelta(days=1)).isoformat(), "name": "신규 실업수당 청구", "star": 1},
            {"date": (date.fromisoformat(day) + timedelta(days=2)).isoformat(), "name": "소비자물가지수(CPI)", "star": 3},
            {"date": (date.fromisoformat(day) + timedelta(days=5)).isoformat(), "name": "FOMC 금리 결정", "star": 3},
        ]},
    }
    data["news"][0]["title"] = "Nvidia shares jump after earnings beat estimates and strong data center guidance"
    data["news"][1]["title"] = "Nvidia results lift chip stocks as AI spending holds up"
    data["headline"] = headline.pick(data["news"], data["stocks"], CONFIG["stocks"]) or headline.fallback(data["indices"])
    return data


# ---------------------------------------------------------------- 출력

def write_site(history_dir):
    files = sorted(history_dir.glob("*.json"))
    entries = [(f.stem, json.loads(f.read_text(encoding="utf-8"))) for f in files]
    if not entries:
        return
    arch = DOCS / "archive"
    if arch.exists():
        shutil.rmtree(arch)
    arch.mkdir(parents=True)
    dates = [d for d, _ in entries]
    for n, (md, data) in enumerate(entries):
        prev_d = dates[n - 1] if n > 0 else None
        next_d = dates[n + 1] if n + 1 < len(dates) else None
        (arch / (md + ".html")).write_text(
            render.page(data, "../", prev_d, next_d, is_latest=False, perf_symbols=CONFIG["performance"]), encoding="utf-8")
    latest_date, latest = entries[-1]
    prev_latest = dates[-2] if len(dates) > 1 else None
    (DOCS / "index.html").write_text(render.page(latest, "", prev_latest, None, is_latest=True, perf_symbols=CONFIG["performance"]), encoding="utf-8")
    (DOCS / "data.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    (arch / "index.html").write_text(render.archive_index(list(reversed(entries))), encoding="utf-8")
    print("docs/ 생성 완료: 최신 " + latest_date + ", 보관 " + str(len(entries)) + "건")


def main():
    if "--demo" in sys.argv:
        history = ROOT / "build" / "demo-history"
        history.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).date()
        days, d = [], today
        while len(days) < 3:
            d -= timedelta(days=1)
            if d.weekday() < 5:
                days.append(d.isoformat())
        for n, day in enumerate(sorted(days)):
            (history / (day + ".json")).write_text(
                json.dumps(demo_data(day, n), ensure_ascii=False, indent=2), encoding="utf-8")
        write_site(history)
        return

    data = collect()
    has_market = data["indices"] or data["sectors"] or data["stocks"] or data["yields"]
    if not has_market:
        print("시세 데이터를 하나도 받지 못했습니다. 기록을 저장하지 않고 이전 페이지를 유지합니다.", file=sys.stderr)
        sys.exit(1)
    history = ROOT / "data" / "history"
    history.mkdir(parents=True, exist_ok=True)
    (history / (data["market_date"] + ".json")).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    write_site(history)


if __name__ == "__main__":
    main()
