#!/usr/bin/env python3
"""미국장 모닝 브리핑 빌더.

외부 패키지 없이 파이썬 기본 라이브러리만 사용합니다.
데이터를 받아 docs/index.html 과 docs/data.json 을 만듭니다.

사용법:
    python scripts/build.py          # 실제 데이터로 생성
    python scripts/build.py --demo   # 네트워크 없이 샘플 데이터로 화면만 확인
"""
import csv
import io
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
import xml.etree.ElementTree as ET

KST = timezone(timedelta(hours=9))
DOCS = Path(__file__).resolve().parent.parent / "docs"
UA = {"User-Agent": "us-morning-brief/1.0 (+https://github.com/jay99-ux/us-morning-brief)"}

# (표시 이름, Stooq 심볼)
INDICES = [
    ("다우존스 산업평균", "^dji"),
    ("S&P 500", "^spx"),
    ("나스닥 종합", "^ndq"),
]
# (표시 이름, FRED 시리즈)
YIELDS = [("2년물", "DGS2"), ("10년물", "DGS10"), ("30년물", "DGS30")]
FED_FEEDS = [
    ("통화정책 발표", "https://www.federalreserve.gov/feeds/press_monetary.xml"),
    ("연설·증언", "https://www.federalreserve.gov/feeds/speeches_and_testimony.xml"),
]


def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_index(symbol):
    text = get("https://stooq.com/q/d/l/?s=" + urllib.parse.quote(symbol) + "&i=d")
    rows = [r for r in csv.DictReader(io.StringIO(text)) if r.get("Close")]
    if len(rows) < 2:
        raise ValueError("종가 데이터가 2일치 미만입니다: " + text[:80].replace("\n", " "))
    last, prev = rows[-1], rows[-2]
    close, before = float(last["Close"]), float(prev["Close"])
    return {
        "date": last["Date"],
        "close": close,
        "change": close - before,
        "pct": (close - before) / before * 100,
    }


def fetch_yield(series):
    start = (datetime.now(timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%d")
    text = get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + series + "&cosd=" + start)
    reader = csv.reader(io.StringIO(text))
    next(reader, None)
    values = []
    for row in reader:
        if len(row) >= 2:
            try:
                values.append((row[0], float(row[1])))
            except ValueError:
                continue  # 휴장일은 "." 로 표시됨
    if len(values) < 2:
        raise ValueError("금리 데이터가 2일치 미만입니다")
    (d1, v1), (_, v0) = values[-1], values[-2]
    return {"date": d1, "value": v1, "bp": round((v1 - v0) * 100)}


def fetch_feed(url, limit=5):
    root = ET.fromstring(get(url))
    items = []
    for item in root.iter("item"):
        items.append(
            {
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "date": (item.findtext("pubDate") or "").strip()[:16],
            }
        )
        if len(items) >= limit:
            break
    return items


def attempt(label, func, *args):
    """한 항목이 실패해도 나머지는 계속 진행합니다."""
    try:
        return func(*args)
    except Exception as exc:  # noqa: BLE001
        print("[경고] " + label + " 실패: " + str(exc), file=sys.stderr)
        return None


def collect(demo=False):
    if demo:
        return {
            "indices": [
                {"name": n, "date": "2026-11-10", "close": c, "change": ch, "pct": p}
                for n, c, ch, p in [
                    ("다우존스 산업평균", 52231.89, -157.86, -0.30),
                    ("S&P 500", 7525.88, -24.06, -0.32),
                    ("나스닥 종합", 25065.87, -187.27, -0.74),
                ]
            ],
            "yields": [
                {"name": n, "date": "2026-11-10", "value": v, "bp": b}
                for n, v, b in [("2년물", 4.95, 16), ("10년물", 4.98, 10), ("30년물", 5.10, 7)]
            ],
            "fed": [
                {
                    "group": "통화정책 발표",
                    "items": [
                        {
                            "title": "샘플 제목입니다",
                            "link": "https://www.federalreserve.gov/",
                            "date": "Tue, 10 Nov 2026",
                        }
                    ],
                }
            ],
        }
    indices = []
    for name, sym in INDICES:
        data = attempt(name, fetch_index, sym)
        if data:
            data["name"] = name
            indices.append(data)
    yields = []
    for name, series in YIELDS:
        data = attempt(name, fetch_yield, series)
        if data:
            data["name"] = name
            yields.append(data)
    fed = []
    for group, url in FED_FEEDS:
        items = attempt(group, fetch_feed, url)
        if items:
            fed.append({"group": group, "items": items})
    return {"indices": indices, "yields": yields, "fed": fed}


def sign_class(value):
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


def render_indices(indices):
    if not indices:
        return '<p class="empty">지수 데이터를 가져오지 못했습니다.</p>'
    cards = []
    for it in indices:
        cls = sign_class(it["pct"])
        width = min(abs(it["pct"]) / 3 * 100, 100)  # 등락률 3%를 100%로 환산
        cards.append(
            '<div class="idx">'
            '<span class="name">' + escape(it["name"]) + "</span>"
            '<span class="level">' + format(it["close"], ",.2f") + "</span>"
            '<span class="chg ' + cls + '"><span>' + format(it["pct"], "+.2f") + "%</span>"
            "<span>" + format(it["change"], "+,.2f") + "pt</span></span>"
            '<div class="bar ' + cls + '" aria-hidden="true"><i style="width:'
            + format(width, ".1f") + '%"></i></div>'
            '<span class="date">' + escape(it["date"]) + " 마감</span>"
            "</div>"
        )
    return '<div class="indices">' + "".join(cards) + "</div>"


def render_yields(yields):
    if not yields:
        return '<p class="empty">금리 데이터를 가져오지 못했습니다.</p>'
    rows = []
    for it in yields:
        cls = sign_class(it["bp"])
        width = min(abs(it["bp"]) / 20 * 100, 100)  # 20bp를 100%로 환산
        rows.append(
            '<div class="yrow"><span class="t">' + escape(it["name"]) + "</span>"
            '<div class="bar ' + cls + '" aria-hidden="true"><i style="width:'
            + format(width, ".1f") + '%"></i></div>'
            '<span class="v ' + cls + '">' + format(it["bp"], "+d") + "bp</span>"
            '<span class="lvl">' + format(it["value"], ".2f") + "%</span></div>"
        )
    asof = escape(yields[0]["date"])
    return '<div class="yields">' + "".join(rows) + '</div><p class="note">기준일 ' + asof + " (FRED 일별 종가 기준)</p>"


def render_fed(fed):
    if not fed:
        return '<p class="empty">연준 발표를 가져오지 못했습니다.</p>'
    blocks = []
    for group in fed:
        lis = []
        for it in group["items"]:
            title = escape(it["title"])
            if it["link"].startswith("https://"):
                title = '<a href="' + escape(it["link"], quote=True) + '" target="_blank" rel="noopener noreferrer">' + title + "</a>"
            lis.append("<li>" + title + '<span class="date">' + escape(it["date"]) + "</span></li>")
        blocks.append("<h3>" + escape(group["group"]) + '</h3><ul class="feed">' + "".join(lis) + "</ul>")
    return "".join(blocks)


def render(data):
    now = datetime.now(KST)
    stamp = now.strftime("%Y-%m-%d %H:%M") + " KST"
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>미국장 모닝 브리핑</title>"
        '<link rel="stylesheet" href="style.css"></head><body><div class="wrap">'
        '<header><div class="label">US Market Morning Brief</div><h1>미국장 모닝 브리핑</h1>'
        '<div class="asof">자동 갱신 <b>' + stamp + "</b></div></header>"
        "<section><h2>지수 마감</h2>" + render_indices(data["indices"]) + "</section>"
        "<section><h2>국채 금리 변동</h2>" + render_yields(data["yields"]) + "</section>"
        "<section><h2>연준 발표</h2>" + render_fed(data["fed"]) + "</section>"
        "<footer><p>정보 제공용이며 투자 조언이 아닙니다. 지수는 Stooq, 금리는 FRED, 연준 발표는 연준 공식 RSS에서 가져옵니다.</p></footer>"
        "</div></body></html>"
    )


def main():
    demo = "--demo" in sys.argv
    data = collect(demo)
    if not (data["indices"] or data["yields"] or data["fed"]):
        print("모든 데이터 수집에 실패했습니다. 이전 페이지를 그대로 유지합니다.", file=sys.stderr)
        sys.exit(1)
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(render(data), encoding="utf-8")
    (DOCS / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("docs/index.html 생성 완료")


if __name__ == "__main__":
    main()
