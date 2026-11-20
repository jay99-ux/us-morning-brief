"""HTML 렌더링. 모든 외부 문자열은 escape 해서 넣습니다."""
from datetime import date, datetime, timedelta, timezone
from html import escape

import signals

KST = timezone(timedelta(hours=9))
WEEKDAYS = "월화수목금토일"


def sign(v):
    return "up" if v > 0 else "down" if v < 0 else "flat"


def pct(v):
    return format(v, "+.2f") + "%"


def kdate(iso):
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return escape(iso)
    return d.strftime("%Y-%m-%d") + " (" + WEEKDAYS[d.weekday()] + ")"


def link(title, url):
    t = escape(title)
    if url.startswith("https://"):
        return '<a href="' + escape(url, quote=True) + '" target="_blank" rel="noopener noreferrer">' + t + "</a>"
    return t


def spark(values, cls):
    if not values or len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    n = len(values) - 1
    pts = " ".join(
        format(i / n * 100, ".2f") + "," + format(26 - (v - lo) / span * 24, ".2f")
        for i, v in enumerate(values)
    )
    return (
        '<svg class="spark ' + cls + '" viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">'
        '<polyline points="' + pts + '" fill="none" stroke="currentColor" stroke-width="1.6" '
        'vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>'
    )


def empty(msg):
    return '<p class="empty">' + escape(msg) + "</p>"


# ---------------------------------------------------------------- 한눈에 보기

def summary_lines(d):
    lines = []
    idx = d.get("indices") or []
    main = [i for i in idx if i["name"] != "러셀 2000"] or idx
    if main:
        ups = sum(1 for i in main if i["pct"] > 0)
        mood = "일제히 상승" if ups == len(main) else "일제히 하락" if ups == 0 else "혼조"
        parts = ", ".join(escape(i["name"]) + ' <b class="' + sign(i["pct"]) + '">' + pct(i["pct"]) + "</b>" for i in main)
        lines.append("주요 지수는 " + mood + "로 마감했어요. " + parts)
    sec = d.get("sectors") or []
    if sec:
        s = sorted(sec, key=lambda x: x["pct"])
        best, worst = s[-1], s[0]
        ups = sum(1 for x in sec if x["pct"] > 0)
        lines.append(
            "섹터는 " + str(len(sec)) + "개 중 " + str(ups) + "개가 올랐어요. 가장 강한 곳은 "
            + escape(best["name"]) + ' <b class="' + sign(best["pct"]) + '">' + pct(best["pct"]) + "</b>, 가장 약한 곳은 "
            + escape(worst["name"]) + ' <b class="' + sign(worst["pct"]) + '">' + pct(worst["pct"]) + "</b>"
        )
    st = d.get("stocks") or []
    if st:
        top = max(st, key=lambda x: abs(x["pct"]))
        lines.append(
            "대형 기술주 중 가장 크게 움직인 종목은 " + escape(top["name"]) + ' <b class="' + sign(top["pct"]) + '">'
            + pct(top["pct"]) + "</b>"
        )
    ten = next((y for y in d.get("yields") or [] if y["name"] == "10년물"), None)
    macro = {m["name"]: m for m in (d.get("macro") or [])}
    tail = []
    if ten:
        tail.append("10년물 금리 " + format(ten["value"], ".2f") + '% (<b class="' + sign(ten["bp"]) + '">' + format(ten["bp"], "+d") + "bp</b>)")
    for key in ("VIX 변동성", "달러/원", "WTI 유가"):
        m = macro.get(key)
        if m:
            tail.append(escape(key) + " " + format(m["close"], ",." + str(m.get("digits", 2)) + "f")
                        + ' (<b class="' + sign(m["pct"]) + '">' + pct(m["pct"]) + "</b>)")
    if tail:
        lines.append(", ".join(tail))
    return lines


# ---------------------------------------------------------------- 섹션

def render_indices(items):
    if not items:
        return empty("지수 데이터를 가져오지 못했습니다.")
    cards = []
    for it in items:
        c = sign(it["pct"])
        cards.append(
            '<div class="card idx"><span class="name">' + escape(it["name"]) + "</span>"
            '<span class="level">' + format(it["close"], ",.2f") + "</span>"
            '<span class="chg ' + c + '"><span>' + pct(it["pct"]) + "</span><span>"
            + format(it["change"], "+,.2f") + "</span></span>"
            + spark(it.get("spark"), c)
            + '<span class="date">' + escape(it["date"]) + " 마감</span></div>"
        )
    return '<div class="grid4">' + "".join(cards) + "</div>"


def render_sectors(items):
    if not items:
        return empty("섹터 데이터를 가져오지 못했습니다.")
    scale = max(1.0, max(abs(i["pct"]) for i in items))
    rows = []
    for it in sorted(items, key=lambda x: x["pct"], reverse=True):
        c = sign(it["pct"])
        w = abs(it["pct"]) / scale * 50
        left = 50 if it["pct"] >= 0 else 50 - w
        rows.append(
            '<div class="srow"><span class="t">' + escape(it["name"]) + ' <small>' + escape(it["symbol"]) + "</small></span>"
            '<div class="dbar ' + c + '" aria-hidden="true"><i style="left:' + format(left, ".1f") + "%;width:"
            + format(max(w, 0.6), ".1f") + '%"></i></div>'
            '<span class="v ' + c + '">' + pct(it["pct"]) + "</span></div>"
        )
    return '<div class="card sectors">' + "".join(rows) + '</div><p class="note">SPDR 섹터 ETF 기준 등락률</p>'


def render_stocks(items):
    if not items:
        return empty("종목 데이터를 가져오지 못했습니다.")
    tiles = []
    for it in sorted(items, key=lambda x: x["pct"], reverse=True):
        c = sign(it["pct"])
        tiles.append(
            '<div class="tile"><span class="name">' + escape(it["name"]) + ' <small>' + escape(it["symbol"]) + "</small></span>"
            '<span class="px">$' + format(it["close"], ",.2f") + '</span><span class="v ' + c + '">' + pct(it["pct"]) + "</span></div>"
        )
    return '<div class="tiles">' + "".join(tiles) + "</div>"


def render_macro(items):
    if not items:
        return empty("원자재·환율 데이터를 가져오지 못했습니다.")
    tiles = []
    for it in items:
        c = sign(it["pct"])
        digits = str(it.get("digits", 2))
        unit = it.get("unit", "")
        val = format(it["close"], ",." + digits + "f")
        val = "$" + val if unit == "$" else val + unit if unit else val
        tiles.append(
            '<div class="tile"><span class="name">' + escape(it["name"]) + "</span>"
            '<span class="px">' + escape(val) + '</span><span class="v ' + c + '">' + pct(it["pct"]) + "</span>"
            + spark(it.get("spark"), c) + "</div>"
        )
    return '<div class="tiles">' + "".join(tiles) + '</div><p class="note">유가·금은 근월물 선물, 기준 시각은 수집 시점</p>'


def _val(it):
    digits = str(it.get("digits", 2))
    unit = it.get("unit", "")
    val = format(it["close"], ",." + digits + "f")
    return "$" + val if unit == "$" else val + unit if unit else val


def _cell(v):
    if v is None:
        return '<td class="flat">–</td>'
    return '<td class="' + sign(v) + '">' + format(v, "+.1f") + "%</td>"


def render_perf(d, symbols):
    rows, fx = signals.performance(d, symbols)
    if not rows:
        return empty("기간별 성과를 계산할 데이터가 없습니다.")
    trs = "".join(
        "<tr><th>" + escape(r["name"]) + "</th>" + _cell(r["w1"]) + _cell(r["m1"]) + _cell(r["ytd"])
        + _cell(r["ytd_krw"]).replace("<td", '<td data-krw="1"', 1) + "</tr>"
        for r in rows
    )
    fx_txt = ("같은 기간 달러/원 " + format(fx, "+.1f") + "% 변동을 반영한 값") if fx is not None else "환율 데이터가 없어 계산하지 못함"
    return (
        '<div class="card tablewrap"><table class="perf"><thead><tr><th>자산</th><th>1주</th><th>1개월</th>'
        "<th>연초 대비</th><th>연초 대비<br><small>원화 기준</small></th></tr></thead><tbody>" + trs + "</tbody></table></div>"
        '<p class="note">달러 기준 가격 수익률(배당 제외). 원화 기준은 ' + escape(fx_txt) + "입니다.</p>"
    )


def render_risk(d):
    items = signals.risk(d)
    if not items:
        return empty("리스크 지표를 가져오지 못했습니다.")
    warn_n = sum(1 for r in items if r["level"] >= 2)
    head = ("지표 " + str(len(items)) + "개 중 경계 이상 " + str(warn_n) + "개") if warn_n else "모든 지표가 보통 이하 수준이에요"
    tiles = "".join(
        '<div class="risk l' + str(r["level"]) + '"><span class="name">' + escape(r["name"]) + "</span>"
        '<span class="rv">' + escape(r["value"]) + '</span><span class="badge">' + escape(r["label"]) + "</span>"
        '<span class="rule">' + escape(r["rule"]) + "</span></div>"
        for r in items
    )
    return ('<p class="knote">' + escape(head) + '</p><div class="riskgrid">' + tiles + "</div>"
            '<p class="note">관례적으로 쓰이는 기준선으로 단순 분류한 참고 지표입니다. 투자 판단의 근거로 단독 사용하지 마세요.</p>')


def render_yields(items):
    if not items:
        return empty("금리 데이터를 가져오지 못했습니다.")
    rows = []
    for it in items:
        c = sign(it["bp"])
        w = min(abs(it["bp"]) / 20 * 100, 100)
        rows.append(
            '<div class="yrow"><span class="t">' + escape(it["name"]) + "</span>"
            '<div class="bar ' + c + '" aria-hidden="true"><i style="width:' + format(w, ".1f") + '%"></i></div>'
            '<span class="v ' + c + '">' + format(it["bp"], "+d") + "bp</span>"
            '<span class="lvl">' + format(it["value"], ".2f") + "%</span></div>"
        )
    by = {y["name"]: y for y in items}
    extra = ""
    if "2년물" in by and "10년물" in by:
        spread = (by["10년물"]["value"] - by["2년물"]["value"]) * 100
        extra = " · 10년물−2년물 금리차 " + format(spread, "+.0f") + "bp"
    return ('<div class="card yields">' + "".join(rows) + '</div><p class="note">기준일 '
            + escape(items[0]["date"]) + " (FRED 일별 기준, 하루 늦게 반영될 수 있음)" + extra + "</p>")


def render_news(items):
    if not items:
        return empty("뉴스를 가져오지 못했습니다.")
    lis = []
    for it in items:
        when = ""
        if it.get("time"):
            try:
                when = datetime.fromisoformat(it["time"]).astimezone(KST).strftime("%m/%d %H:%M")
            except ValueError:
                when = ""
        lis.append(
            "<li>" + link(it["title"], it["link"]) + '<span class="meta">' + escape(it["source"])
            + (" · " + when + " KST" if when else "") + "</span></li>"
        )
    return '<ul class="feed">' + "".join(lis) + '</ul><p class="note">헤드라인과 링크만 모아 보여줍니다. 원문은 각 언론사에서 확인하세요.</p>'


def render_fed(groups):
    if not groups:
        return empty("연준 발표를 가져오지 못했습니다.")
    out = []
    for g in groups:
        lis = "".join(
            "<li>" + link(i["title"], i["link"]) + '<span class="meta">' + escape(i["date"]) + "</span></li>"
            for i in g["items"]
        )
        out.append("<h3>" + escape(g["group"]) + '</h3><ul class="feed">' + lis + "</ul>")
    return "".join(out)


def render_calendar(cal):
    if not cal or not cal.get("enabled"):
        return empty("경제지표 일정은 FRED API 키를 등록하면 표시됩니다(README 참고).")
    events = cal.get("events") or []
    if not events:
        return empty("앞으로 7일 안에 예정된 주요 지표 발표가 없습니다.")
    rows = []
    for e in events:
        stars = "★" * e["star"] + "☆" * (3 - e["star"])
        rows.append(
            '<li><span class="cd">' + kdate(e["date"]) + '</span><span class="cn">' + escape(e["name"])
            + '</span><span class="star s' + str(e["star"]) + '" title="중요도">' + stars + "</span></li>"
        )
    return '<ul class="cal">' + "".join(rows) + '</ul><p class="note">미국 현지 날짜 기준 · 출처 FRED 발표 일정</p>'


def render_headline(h):
    if not h:
        return ""
    meta = []
    if h.get("note"):
        meta.append(escape(h["note"]))
    if h.get("source"):
        meta.append(escape(h["source"]))
    return (
        '<div class="headline"><span class="htag">' + escape(h.get("tag", "")) + "</span>"
        '<p class="htext">' + link(h["text"], h.get("link", "")) + "</p>"
        + ('<span class="hmeta">' + " · ".join(meta) + "</span>" if meta else "")
        + "</div>"
    )


# ---------------------------------------------------------------- 페이지

def page(d, root, prev_date=None, next_date=None, is_latest=False, perf_symbols=None):
    """root: style.css 까지의 상대 경로 접두어 ('' 또는 '../')."""
    md = d.get("market_date", "")
    gen = d.get("generated_at", "")
    try:
        gen = datetime.fromisoformat(gen).astimezone(KST).strftime("%Y-%m-%d %H:%M") + " KST"
    except ValueError:
        pass
    arch = root + "archive/"
    nav = []
    nav.append('<a href="' + arch + prev_date + '.html">← ' + prev_date + "</a>" if prev_date else "<span></span>")
    nav.append('<a href="' + arch + 'index.html">지난 브리핑 모아보기</a>')
    if next_date:
        nav.append('<a href="' + arch + next_date + '.html">' + next_date + " →</a>")
    elif not is_latest:
        nav.append('<a href="' + root + 'index.html">최신 브리핑 →</a>')
    else:
        nav.append("<span></span>")

    summary = summary_lines(d)
    summary_html = (
        '<section class="glance"><h2>한눈에 보기</h2><ul>' + "".join("<li>" + s + "</li>" for s in summary) + "</ul></section>"
        if summary else ""
    )
    sections = [
        ("지수 마감", render_indices(d.get("indices"))),
        ("섹터별 등락", render_sectors(d.get("sectors"))),
        ("주요 종목", render_stocks(d.get("stocks"))),
        ("원자재 · 환율 · 변동성", render_macro(d.get("macro"))),
        ("국채 금리 변동", render_yields(d.get("yields"))),
        ("기간별 성과", render_perf(d, perf_symbols or [])),
        ("주요 뉴스", render_news(d.get("news"))),
        ("앞으로 7일 경제지표 일정", render_calendar(d.get("calendar"))),
        ("연준 발표", render_fed(d.get("fed"))),
        ("리스크 신호판", render_risk(d)),
    ]
    body = "".join("<section><h2>" + escape(t) + "</h2>" + h + "</section>" for t, h in sections)
    title = "미국장 모닝 브리핑 " + md
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>" + escape(title) + "</title>"
        '<link rel="stylesheet" href="' + root + 'style.css"></head><body><div class="wrap">'
        '<header><div class="label">US Market Morning Brief</div><h1>미국장 모닝 브리핑</h1>'
        '<div class="asof"><b>' + kdate(md) + "</b> 미국장 · 자동 갱신 " + escape(gen) + "</div>"
        '<nav class="pager">' + "".join(nav) + "</nav></header>"
        + render_headline(d.get("headline"))
        + summary_html + body
        + "<footer><p>정보 제공용이며 투자 조언이 아닙니다. 시세는 Yahoo Finance 차트 데이터(대체: FRED), 금리와 지표 일정은 FRED, "
        "하이일드 스프레드는 ICE BofA 지수(FRED), 연준 발표는 연준 공식 RSS, 뉴스는 각 언론사 RSS에서 가져옵니다. 데이터는 지연되거나 틀릴 수 있습니다.</p></footer>"
        "</div></body></html>"
    )


def archive_index(entries, root="../"):
    """entries: [(date, data), ...] 최신순."""
    rows = []
    for md, d in entries:
        idx = {i["name"]: i for i in d.get("indices") or []}
        cells = ""
        for name in ("S&P 500", "나스닥 종합", "다우존스"):
            i = idx.get(name)
            cells += '<span class="' + (sign(i["pct"]) if i else "flat") + '">' + (pct(i["pct"]) if i else "–") + "</span>"
        h = d.get("headline") or {}
        sub = '<span class="ah">' + escape(h["text"]) + "</span>" if h.get("text") else ""
        rows.append('<li><span class="ad"><a href="' + md + '.html">' + kdate(md) + "</a>" + sub + "</span>" + cells + "</li>")
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>지난 브리핑 · 미국장 모닝 브리핑</title>"
        '<link rel="stylesheet" href="' + root + 'style.css"></head><body><div class="wrap">'
        '<header><div class="label">Archive</div><h1>지난 브리핑</h1>'
        '<nav class="pager"><span></span><a href="' + root + 'index.html">최신 브리핑으로</a><span></span></nav></header>'
        '<section><ul class="archive"><li class="head"><span>미국장 날짜</span><span>S&amp;P 500</span><span>나스닥</span><span>다우</span></li>'
        + ("".join(rows) or "<li>아직 저장된 브리핑이 없습니다.</li>")
        + "</ul></section><footer><p>정보 제공용이며 투자 조언이 아닙니다.</p></footer></div></body></html>"
    )
