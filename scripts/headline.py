"""오늘의 핵심 이슈 한 줄 고르기.

AI 없이 규칙으로 점수를 매깁니다.
- 키워드(실적, 상장, 연준, 물가·고용, 관세, 인수합병 등) 가산점
- 헤드라인에 나온 종목이 실제로 크게 움직였으면 등락률만큼 가산점
- 여러 언론사가 같은 회사·주제를 다뤘으면 가산점
- 칼럼·재테크 질문형 기사는 감점
직접 입력한 문장(HEADLINE 환경변수)이 있으면 그것을 우선합니다.
"""
import re

# (태그, 가중치, 정규식)
TOPICS = [
    ("상장", 4, r"\bIPOs?\b|initial public offering|goes public|go public|public debut|listing"),
    ("실적", 3, r"earnings|quarterly results|revenue|guidance|profit|beats? estimates|misses? estimates|forecast"),
    ("연준", 4, r"\bFed\b|Federal Reserve|FOMC|Powell|rate cuts?|rate hikes?|interest rates?"),
    ("물가·고용", 3, r"\bCPI\b|\bPCE\b|inflation|jobs report|payrolls|unemployment|jobless"),
    ("관세·정책", 2, r"tariffs?|trade war|sanctions?|export controls?|White House|Congress|shutdown"),
    ("인수합병", 2, r"acquir\w*|merger|takeover|buyout|\bdeal\b"),
    ("AI", 1, r"\bAI\b|artificial intelligence|data center|chips?"),
]
MOVE = r"record|plunge|plummet|soar|surge|tumble|sink|rally|sell-?off|crash|jump|slump|rout"
NOISE = r"\?|^how |should you|opinion|\bI\b|\bmy\b|retire|my wife|my husband|personal finance|quiz|podcast"

STOP = {"the", "and", "for", "with", "from", "that", "this", "after", "over", "into", "stock", "stocks",
        "market", "markets", "says", "said", "will", "than", "what", "more", "shares", "amid"}


def _words(title):
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z&.'-]{3,}", title)} - STOP


def pick(news, stocks, config_stocks, manual=""):
    manual = " ".join((manual or "").split())
    if manual:
        return {"text": manual[:160], "tag": "편집", "link": "", "source": "", "note": "", "manual": True}
    if not news:
        return None

    alias = {}
    for cs in config_stocks:
        for a in cs.get("aliases", []) + [cs["symbol"]]:
            alias[a.lower()] = cs["symbol"]
    moves = {s["symbol"]: s for s in stocks or []}
    bags = [_words(n["title"]) for n in news]

    best, best_score = None, 0.0
    for i, n in enumerate(news):
        t = n["title"]
        score, tag = 0.0, ""
        for name, w, pat in TOPICS:
            if re.search(pat, t, re.I):
                score += w
                tag = tag or name
        if re.search(MOVE, t, re.I):
            score += 1
        if re.search(NOISE, t, re.I):
            score -= 4
        hit = None
        for a, sym in alias.items():
            if re.search(r"\b" + re.escape(a) + r"\b", t, re.I if len(a) > 4 else 0):
                hit = moves.get(sym) or hit
        if hit:
            score += 1 + min(abs(hit["pct"]), 8)
        overlap = sum(1 for j, b in enumerate(bags) if j != i and len(bags[i] & b) >= 2)
        score += min(overlap, 3) * 1.5
        if score > best_score:
            note = ""
            if hit:
                note = hit["name"] + " " + format(hit["pct"], "+.2f") + "%"
            best, best_score = {"text": t, "tag": tag or "시장", "link": n.get("link", ""),
                                "source": n.get("source", ""), "note": note, "manual": False}, score
    return best if best_score >= 3 else None


def fallback(indices):
    """뉴스로 고르지 못했을 때: 가장 크게 움직인 지수로 한 줄."""
    if not indices:
        return None
    top = max(indices, key=lambda i: abs(i["pct"]))
    verb = "상승" if top["pct"] > 0 else "하락"
    if abs(top["pct"]) >= 1.5:
        verb = "급등" if top["pct"] > 0 else "급락"
    return {"text": top["name"] + " " + format(top["pct"], "+.2f") + "% " + verb + "으로 마감",
            "tag": "시장", "link": "", "source": "", "note": "", "manual": False}
