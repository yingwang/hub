#!/usr/bin/env python3
"""Build a single-page dashboard ("hub") that aggregates Ying's GitHub Pages sites.

The three daily-updating sites (paper-reads, news-reads, trade) render as "live"
cards with a short summary of their latest content, fetched at build time. The
remaining books/guides render as plain link cards grouped by category.

Output: docs/index.html (served by GitHub Pages).
Stdlib only. Optionally reads GITHUB_TOKEN / GH_TOKEN to avoid API rate limits.
"""

import base64
import datetime
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request

GH_API = "https://api.github.com"
OWNER = "yingwang"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "docs", "index.html")


# ----------------------------------------------------------------------------
# Fetch helpers
# ----------------------------------------------------------------------------
def _open(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    req.add_header("User-Agent", "yingwang-hub-builder")
    return urllib.request.urlopen(req, timeout=25)


def gh(path):
    """GitHub contents API (used for repos whose main branch holds the latest)."""
    headers = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    try:
        with _open(GH_API + path, headers) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print(f"  ! GH {path} -> HTTP {e.code}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"  ! GH {path} -> {e}", file=sys.stderr)
    return None


def fetch_json(url):
    """Fetch a JSON file directly from a deployed Pages URL (always fresh)."""
    try:
        with _open(url) as r:
            return json.load(r)
    except Exception as e:  # noqa: BLE001
        print(f"  ! url {url} -> {e}", file=sys.stderr)
        return None


def get_file_text(repo, path):
    d = gh(f"/repos/{OWNER}/{repo}/contents/{path}")
    if not d or "content" not in d:
        return None
    return base64.b64decode(d["content"]).decode("utf-8", "replace")


def list_dir(repo, path):
    d = gh(f"/repos/{OWNER}/{repo}/contents/{path}")
    return [x["name"] for x in d] if isinstance(d, list) else []


def first_heading(text):
    if not text:
        return None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return None


def section_body(text, header):
    """Return the first non-empty paragraph under a '## <header>' section."""
    if not text:
        return None
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if l.strip().lstrip("#").strip() == header:
            for j in range(i + 1, len(lines)):
                s = lines[j].strip()
                if s and not s.startswith("#"):
                    return s
    return None


# ----------------------------------------------------------------------------
# Daily-site fetchers
# ----------------------------------------------------------------------------
def latest_paper():
    files = [f for f in list_dir("paper-reads", "docs/papers")
             if re.match(r"\d{4}-\d{2}-\d{2}-.*\.md$", f)]
    if not files:
        return None
    files.sort(reverse=True)
    latest = files[0]
    txt = get_file_text("paper-reads", f"docs/papers/{latest}")
    title = first_heading(txt) or latest[11:-3]
    # Title is usually "<名字>：<副标题>". Use the short name as the heading and the
    # 一句话 (or the subtitle) as the body, stripping any leading repeat of the name.
    name = re.split(r"[：:]", title, 1)[0].strip()
    summary = section_body(txt, "一句话")
    if not summary and re.search(r"[：:]", title):
        summary = re.split(r"[：:]", title, 1)[1].strip()
    if summary and summary.startswith(name):
        summary = summary[len(name):].lstrip("：:，, 　")
    lines = [name] + ([summary] if summary else [])
    links = []
    m = re.search(r"arxiv\.org/abs/([0-9]{4}\.[0-9]{4,5})", txt or "")
    if m:
        links.append(("arXiv ↗", f"https://arxiv.org/abs/{m.group(1)}"))
    return {"date": latest[:10], "lines": lines, "links": links}


def latest_news():
    files = [f for f in list_dir("news-reads", "docs/news")
             if re.match(r"\d{4}-\d{2}-\d{2}\.md$", f)]
    if not files:
        return None
    files.sort(reverse=True)
    latest = files[0]
    date = latest[:10]
    txt = get_file_text("news-reads", f"docs/news/{latest}")
    sections = []
    if txt:
        for l in txt.splitlines():
            m = re.match(r"^\*\*(.+?)\*\*$", l.strip())
            if m:
                sections.append(m.group(1))
    summary = " · ".join(sections[:5]) if sections else f"{date} 早间 brief"
    return {"date": date, "lines": [summary]}


def _live_return(trades):
    """Replicate the trade site's renderActualPerformance: return % over the
    Alpaca paper-trading portfolio_history, using the live account equity as the
    final point. This matches the headline number shown on the trade dashboard."""
    hist = [h for h in (trades.get("portfolio_history") or []) if h.get("equity") is not None]
    if len(hist) < 2:
        return None, None
    acct = trades.get("account") or {}
    start = hist[0]["equity"]
    end = acct.get("equity") or hist[-1]["equity"]
    if not start:
        return None, end
    return (end / start - 1) * 100.0, end


def latest_trade():
    base = "https://yingwang.github.io/trade"
    pf = fetch_json(f"{base}/data/portfolio.json") or {}
    strategies = []
    for name, sub in (("多因子", ""), ("LGBM", "/lgbm")):
        tr = fetch_json(f"{base}{sub}/data/trades.json")
        if not tr:
            continue
        ret, equity = _live_return(tr)
        strategies.append({"name": name, "ret": ret, "equity": equity})
    return {
        "date": (pf.get("updated_at") or "")[:10],
        "strategies": strategies,
        "foot": "Alpaca paper trading 实盘业绩",
    }


DAILY = [
    {
        "slug": "paper-reads",
        "title": "每日论文精读",
        "blurb": "huggingface daily 榜首论文的中文四段精读",
        "url": "https://yingwang.github.io/paper-reads/",
        "fetch": latest_paper,
    },
    {
        "slug": "news-reads",
        "title": "每日新闻 brief",
        "blurb": "过去 24 小时全球新闻的结构化中文摘要",
        "url": "https://yingwang.github.io/news-reads/",
        "fetch": latest_news,
    },
    {
        "slug": "trade",
        "title": "量化策略面板",
        "blurb": "多因子与 LGBM 两套策略的实盘业绩 (Alpaca)",
        "url": "https://yingwang.github.io/trade/",
        "fetch": latest_trade,
    },
]

GROUPS = [
    ("AI / 技术", [
        ("LLM 训练工程师指南", "https://yingwang.github.io/llm-tutorial/"),
        ("Thinking in LLM", "https://yingwang.github.io/thinking-in-llm/"),
        ("图像增强:原理到工程", "https://yingwang.github.io/image-enhancement-guide/"),
        ("具身智能的工程判断", "https://yingwang.github.io/robotics-llm-book/"),
    ]),
    ("投资", [
        ("投资书", "https://yingwang.github.io/investing-book/"),
    ]),
    ("旅行", [
        ("中国高铁游指南", "https://yingwang.github.io/china-train-book/"),
    ]),
    ("文化 / 生活", [
        ("瓷:中国第一个工业", "https://yingwang.github.io/china-porcelain-book/"),
        ("摄影技法书", "https://yingwang.github.io/photography-book/"),
        ("阅读指南 · 100 本", "https://yingwang.github.io/reading-guide/"),
        ("家常菜谱", "https://yingwang.github.io/recipes/"),
    ]),
    ("博客 / 其他", [
        ("个人博客", "https://yingwang.github.io/blog/"),
        ("Hugging Face", "https://huggingface.co/xingqiwang"),
    ]),
]


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------
def esc(s):
    return html.escape(str(s), quote=True)


def _fmt_pct(v):
    if v is None:
        return "—", ""
    cls = "pos" if v >= 0 else "neg"
    return f"{v:+.1f}%", cls


def render_trade_body(data):
    rows = []
    for s in data.get("strategies", []):
        pct, cls = _fmt_pct(s.get("ret"))
        meta = f"权益 ${s['equity']:,.0f}" if s.get("equity") else "实盘"
        rows.append(
            f'<div class="perf-row"><span class="s-name">{esc(s["name"])}</span>'
            f'<span class="s-ret {cls}">{esc(pct)}</span>'
            f'<span class="s-meta">{esc(meta)}</span></div>'
        )
    body = "".join(rows) or '<p class="latest muted">数据暂不可用</p>'
    if data.get("foot"):
        body += f'<p class="perf-foot">{esc(data["foot"])}</p>'
    return body


def render_daily_card(site):
    try:
        data = site["fetch"]()
    except Exception as e:  # noqa: BLE001
        print(f"  ! fetch {site['slug']} -> {e}", file=sys.stderr)
        data = None

    date = esc(data["date"]) if data and data.get("date") else "—"
    if data and data.get("strategies") is not None:
        body = render_trade_body(data)
    elif data and data.get("lines"):
        parts = []
        for i, x in enumerate(data["lines"]):
            cls = "latest" if i == 0 else "latest sub"
            parts.append(f'<p class="{cls}">{esc(x)}</p>')
        body = "".join(parts)
    else:
        body = '<p class="latest muted">最新内容暂不可用</p>'

    inner = f"""<div class="card-top">
          <span class="title">{esc(site['title'])}</span>
          <span class="date">{date}</span>
        </div>
        <p class="blurb">{esc(site['blurb'])}</p>
        {body}"""

    links = (data or {}).get("links") or []
    if not links:
        # Whole card is one link to the site.
        return f'      <a class="card daily" href="{esc(site["url"])}">\n        {inner}\n      </a>'
    # Card has secondary links (e.g. arXiv): main area links to the site, plus
    # separate sibling links below (cannot nest <a> inside <a>).
    ext = "".join(
        f'<a class="ext" href="{esc(u)}">{esc(t)}</a>' for t, u in links
    )
    return f"""      <div class="card daily">
        <a class="card-main" href="{esc(site['url'])}">
        {inner}
        </a>
        <div class="card-ext">{ext}</div>
      </div>"""


def render_link_card(name, url):
    return f'        <a class="card link" href="{esc(url)}"><span class="title">{esc(name)}</span></a>'


def render_group(name, items):
    cards = "\n".join(render_link_card(n, u) for n, u in items)
    return f"""      <section class="group">
        <h2>{esc(name)}</h2>
        <div class="grid">
{cards}
        </div>
      </section>"""


def build():
    print("Building hub …")
    daily_cards = "\n".join(render_daily_card(s) for s in DAILY)
    group_blocks = "\n".join(render_group(n, items) for n, items in GROUPS)
    built = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    page = TEMPLATE.format(daily_cards=daily_cards, groups=group_blocks, built=built)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Wrote {OUT} ({len(page)} bytes)")


TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Hub · Ying</title>
<style>
:root {{
  --bg: #f6f7f9; --fg: #1c2024; --muted: #6b7280; --card: #ffffff;
  --line: #e6e8eb; --accent: #0d9488; --shadow: 0 1px 2px rgba(0,0,0,.05), 0 4px 14px rgba(0,0,0,.04);
  --pos: #16a34a; --neg: #dc2626;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #0e1116; --fg: #e6e8eb; --muted: #9aa3ad; --card: #171b21;
    --line: #262c34; --accent: #2dd4bf; --shadow: none; --pos: #4ade80; --neg: #f87171;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
        "Hiragino Sans GB", "Microsoft YaHei", system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}}
.wrap {{ max-width: 920px; margin: 0 auto; padding: 40px 20px 64px; }}
header h1 {{ margin: 0; font-size: 26px; letter-spacing: .3px; }}
header p {{ margin: 6px 0 0; color: var(--muted); font-size: 14px; }}
h2 {{ font-size: 14px; color: var(--muted); font-weight: 600; margin: 30px 0 12px; letter-spacing: .4px; }}
.daily-grid {{ display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); margin-top: 12px; }}
.grid {{ display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); }}
.card {{
  display: block; text-decoration: none; color: inherit; background: var(--card);
  border: 1px solid var(--line); border-radius: 14px; box-shadow: var(--shadow);
  transition: transform .12s ease, border-color .12s ease;
}}
.card:hover {{ transform: translateY(-2px); border-color: var(--accent); }}
.card.daily {{ padding: 18px 18px 16px; }}
.card.daily .card-main {{ display: block; text-decoration: none; color: inherit; }}
.card.daily .card-ext {{ margin-top: 12px; }}
.card.daily .ext {{
  display: inline-block; text-decoration: none; font-size: 12px; font-weight: 600;
  color: var(--accent); border: 1px solid var(--line); border-radius: 8px; padding: 3px 10px;
}}
.card.daily .ext:hover {{ border-color: var(--accent); }}
.card.daily .card-top {{ display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }}
.card.daily .title {{ font-size: 17px; font-weight: 650; }}
.card.daily .date {{ font-size: 12px; color: var(--accent); font-variant-numeric: tabular-nums; white-space: nowrap; }}
.card.daily .blurb {{ margin: 6px 0 12px; font-size: 13px; color: var(--muted); }}
.card.daily .latest {{ margin: 4px 0 0; font-size: 14px; font-weight: 650; line-height: 1.45; }}
.card.daily .latest.sub {{ margin-top: 6px; font-size: 13px; font-weight: 400; color: var(--muted); }}
.card.daily .latest.muted {{ font-weight: 400; color: var(--muted); }}
.perf-row {{ display: flex; align-items: baseline; gap: 8px; margin-top: 6px; }}
.perf-row .s-name {{ font-size: 14px; font-weight: 600; min-width: 52px; }}
.perf-row .s-ret {{ font-size: 17px; font-weight: 700; font-variant-numeric: tabular-nums; }}
.perf-row .s-meta {{ font-size: 12px; color: var(--muted); }}
.perf-foot {{ margin: 10px 0 0; font-size: 12px; color: var(--muted); }}
.pos {{ color: var(--pos); }}
.neg {{ color: var(--neg); }}
.card.link {{ padding: 14px 15px; }}
.card.link .title {{ font-size: 14px; font-weight: 550; }}
footer {{ margin-top: 36px; color: var(--muted); font-size: 13px; }}
footer a {{ color: var(--accent); text-decoration: none; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Hub</h1>
    <p>每天更新的几个站点,以及书与教程的入口</p>
  </header>

  <h2>每日更新</h2>
  <div class="daily-grid">
{daily_cards}
  </div>

{groups}

  <footer>
    构建于 {built} · <a href="https://yingwang.github.io/">个人主页</a> · <a href="https://github.com/yingwang">GitHub</a>
  </footer>
</div>
</body>
</html>
"""


if __name__ == "__main__":
    build()
