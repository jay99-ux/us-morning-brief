"""데이터 수집.

외부 패키지 없이 파이썬 기본 라이브러리만 씁니다.
각 항목은 실패해도 None 을 돌려주고, 나머지 수집은 계속 진행합니다.
"""
import csv
import io
import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) us-morning-brief/2.0 (+https://github.com/jay99-ux/us-morning-brief)"
}
ET_TZ = timezone(timedelta(hours=-5))  # 미국 동부 표준시 근사치(일정 창 계산용)


def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def warn(label, exc):
    print("[경고] " + label + " 실패: " + str(exc)[:160], file=sys.stderr)


# ---------------------------------------------------------------- 가격 데이터

def _base(points, cutoff):
    """cutoff 날짜(포함) 이전의 마지막 종가."""
    prior = [v for d, v in points if d <= cutoff]
    return prior[-1] if prior else None


def _ret(last, base):
    return (last / base - 1) * 100 if base else None


def _summarize(points):
    """[(YYYY-MM-DD, close), ...] 날짜 오름차순 → 종가·전일 대비·기간 수익률·추세 지표."""
    if len(points) < 2:
        raise ValueError("종가 데이터가 2일치 미만입니다")
    (d1, close), (_, before) = points[-1], points[-2]
    last = date.fromisoformat(d1)
    year = [(d, v) for d, v in points if d > (last - timedelta(days=365)).isoformat()]
    closes = [v for _, v in points]
    out = {
        "date": d1,
        "close": close,
        "change": close - before,
        "pct": (close - before) / before * 100 if before else 0.0,
        "spark": [round(v, 4) for v in closes[-22:]],
        "perf": {
            "w1": _ret(close, _base(points, (last - timedelta(days=7)).isoformat())),
            "m1": _ret(close, _base(points, (last - timedelta(days=30)).isoformat())),
            "ytd": _ret(close, _base(points, date(last.year - 1, 12, 31).isoformat())),
        },
    }
    if len(year) >= 200:
        hi = max(v for _, v in year)
        ma200 = sum(closes[-200:]) / 200
        out.update({"hi52": hi, "dd52": (close / hi - 1) * 100, "ma200": ma200,
                    "vs200": (close / ma200 - 1) * 100})
    return out


def yahoo_daily(symbol):
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(symbol, safe="")
        + "?range=1y&interval=1d"
    )
    res = json.loads(get(url))["chart"]["result"][0]
    offset = res["meta"].get("gmtoffset", 0)
    closes = res["indicators"]["quote"][0]["close"]
    by_date = {}
    for ts, value in zip(res.get("timestamp") or [], closes):
        if value is None:
            continue
        d = datetime.fromtimestamp(ts + offset, timezone.utc).strftime("%Y-%m-%d")
        by_date[d] = float(value)  # 같은 날짜가 두 번 오면 나중 값을 씀
    return _summarize(sorted(by_date.items()))


def fred_series(series, days=400):
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    text = get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + series + "&cosd=" + start)
    reader = csv.reader(io.StringIO(text))
    next(reader, None)
    points = []
    for row in reader:
        if len(row) >= 2:
            try:
                points.append((row[0], float(row[1])))
            except ValueError:
                continue  # 휴장일은 "." 로 표시됨
    return points


def fred_daily(series):
    return _summarize(fred_series(series))


def quote(item):
    """Yahoo 를 먼저 쓰고, 실패하면 설정에 적힌 FRED 시리즈로 대체합니다."""
    try:
        data = yahoo_daily(item["symbol"])
        data["src"] = "Yahoo"
    except Exception as exc:  # noqa: BLE001
        warn(item["name"] + " (Yahoo)", exc)
        if not item.get("fred"):
            return None
        try:
            data = fred_daily(item["fred"])
            data["src"] = "FRED"
        except Exception as exc2:  # noqa: BLE001
            warn(item["name"] + " (FRED)", exc2)
            return None
    data.update({k: v for k, v in item.items() if k in ("name", "symbol", "unit", "digits", "role")})
    return data


def fred_level(series):
    """최근 값과 전일 대비 변화(하이일드 스프레드 등)."""
    try:
        points = fred_series(series, days=60)
        if len(points) < 2:
            raise ValueError("데이터가 2일치 미만입니다")
        (d1, v1), (_, v0) = points[-1], points[-2]
        return {"date": d1, "value": v1, "change": v1 - v0}
    except Exception as exc:  # noqa: BLE001
        warn(series, exc)
        return None


def yield_row(item):
    try:
        points = fred_series(item["fred"], days=45)
        if len(points) < 2:
            raise ValueError("금리 데이터가 2일치 미만입니다")
        (d1, v1), (_, v0) = points[-1], points[-2]
        return {"name": item["name"], "date": d1, "value": v1, "bp": round((v1 - v0) * 100)}
    except Exception as exc:  # noqa: BLE001
        warn(item["name"], exc)
        return None


# ---------------------------------------------------------------- 뉴스·연준

def _parse_time(text):
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def rss_items(url):
    root = ET.fromstring(get(url))
    out = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        out.append(
            {
                "title": " ".join((item.findtext("title") or "").split()),
                "link": link if link.startswith("https://") else "",
                "time": _parse_time((item.findtext("pubDate") or "").strip()),
            }
        )
    return [i for i in out if i["title"]]


def news(feeds, limit, hours, now):
    cutoff = now - timedelta(hours=hours)
    per_source = max(3, limit // 2)
    seen, pool = set(), []
    for feed in feeds:
        try:
            items = rss_items(feed["url"])
        except Exception as exc:  # noqa: BLE001
            warn("뉴스 " + feed["source"], exc)
            continue
        taken = 0
        for it in items:
            key = it["title"].lower()
            if key in seen or (it["time"] and it["time"] < cutoff):
                continue
            seen.add(key)
            pool.append({**it, "source": feed["source"]})
            taken += 1
            if taken >= per_source:
                break
    pool.sort(key=lambda i: i["time"] or cutoff, reverse=True)
    return [
        {"title": i["title"], "link": i["link"], "source": i["source"],
         "time": i["time"].isoformat() if i["time"] else ""}
        for i in pool[:limit]
    ]


def fed(feeds, limit=4):
    groups = []
    for feed in feeds:
        try:
            items = rss_items(feed["url"])[:limit]
        except Exception as exc:  # noqa: BLE001
            warn(feed["group"], exc)
            continue
        groups.append(
            {
                "group": feed["group"],
                "items": [
                    {"title": i["title"], "link": i["link"],
                     "date": i["time"].strftime("%Y-%m-%d") if i["time"] else ""}
                    for i in items
                ],
            }
        )
    return groups


# ---------------------------------------------------------------- 경제지표 일정

def calendar(cfg):
    """FRED API 키(FRED_API_KEY)가 있으면 발표 일정을 받아오고, 수동 일정과 합칩니다."""
    start = datetime.now(ET_TZ).date() + timedelta(days=1)
    end = start + timedelta(days=cfg.get("calendar_days", 7))
    events = []
    key = os.environ.get("FRED_API_KEY", "").strip()
    if key:
        params = urllib.parse.urlencode(
            {
                "api_key": key,
                "file_type": "json",
                "realtime_start": start.isoformat(),
                "realtime_end": end.isoformat(),
                "include_release_dates_with_no_data": "true",
                "sort_order": "asc",
                "limit": 1000,
            }
        )
        try:
            rows = json.loads(get("https://api.stlouisfed.org/fred/releases/dates?" + params))["release_dates"]
            for row in rows:
                name = row.get("release_name", "")
                for rule in cfg["calendar_releases"]:
                    if rule["match"].lower() in name.lower():
                        events.append({"date": row["date"], "name": rule["name"], "star": rule["star"]})
                        break
        except Exception as exc:  # noqa: BLE001 (키가 담긴 주소는 출력하지 않음)
            warn("경제지표 일정", exc)
    for ev in cfg.get("manual_events", []):
        try:
            d = date.fromisoformat(ev.get("date", ""))
        except ValueError:
            continue
        if start <= d <= end and ev.get("name"):
            events.append({"date": d.isoformat(), "name": ev["name"], "star": ev.get("star", 2)})
    uniq = {(e["date"], e["name"]): e for e in events}
    return {
        "enabled": bool(key) or bool(uniq),
        "events": sorted(uniq.values(), key=lambda e: (e["date"], -e["star"], e["name"])),
    }
