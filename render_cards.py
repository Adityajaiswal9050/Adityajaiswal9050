#!/usr/bin/env python3
"""Render GitHub profile SVG cards using verified GitHub contribution data.

One generator for all profile images. No external image URLs or JavaScript are
embedded in the SVGs. STATIC=1 produces final-frame, non-animated previews.

Data source: data/contributions.json, refreshed via --fetch using GitHub GraphQL.
To preserve privacy and integrity, a missing data file renders an explicit
"waiting for data" state rather than fabricated contributions.
"""
from __future__ import annotations

import argparse
import base64
import calendar
import json
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
USER = "Adityajaiswal9050"
DATA = ROOT / "data" / "contributions.json"
BG, BG2, CARD = "#050d1a", "#0a1628", "#0d1b33"
CYAN, PURPLE, GREEN = "#00d4ff", "#7c3aed", "#00e676"
TEXT, MUTED, BORDER = "#e2e8f0", "#94a3b8", "#1e3a5f"
STATIC = os.getenv("STATIC", "0").lower() in ("1", "true", "yes")

FEATURED = [
    ("moe-memory-lab", "MoE Memory Lab",
     "Cache-policy research: synthetic routing, replay and reproducible tests.",
     "Python / AI Systems", CYAN),
    ("DataSentinel-AI", "DataSentinel AI",
     "Agentic data-quality analysis using MCP tools, Claude and FastAPI.",
     "LLM Agents / MCP", PURPLE),
    ("LLM-Observability", "LLM Observability",
     "Metrics for LLM latency, token usage, costs and errors.",
     "FastAPI / Prometheus", GREEN),
    ("Multi-Agent-Medical-Assistant", "Multi-Agent Medical Assistant",
     "Medical AI workflow with multiple agents and retrieval.",
     "LangGraph / RAG", CYAN),
]


def graph_fetch() -> None:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required for --fetch (never print or save it).")
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=365)
    query = """query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        contributionsCollection(from:$from,to:$to) {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays { date contributionCount }
            }
          }
        }
      }
    }"""
    body = json.dumps({
        "query": query,
        "variables": {
            "login": USER,
            "from": start.strftime("%Y-%m-%dT00:00:00Z"),
            "to": today.strftime("%Y-%m-%dT23:59:59Z"),
        },
    }).encode("utf-8")
    req = Request("https://api.github.com/graphql", data=body, method="POST",
                  headers={"Authorization": f"Bearer {token}",
                           "Accept": "application/vnd.github+json",
                           "Content-Type": "application/json",
                           "User-Agent": "animated-profile-generator"})
    with urlopen(req, timeout=35) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise RuntimeError("GitHub GraphQL returned errors; refusing to replace good data.")
    user = (payload.get("data") or {}).get("user")
    if not user:
        raise RuntimeError("GitHub contribution user not found.")
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = sorted(
        ({"date": day["date"], "count": int(day["contributionCount"])}
         for week in cal["weeks"] for day in week["contributionDays"]),
        key=lambda row: row["date"],
    )
    if not days or any(row["count"] < 0 for row in days):
        raise RuntimeError("Invalid empty/negative contribution calendar.")
    if len({row["date"] for row in days}) != len(days):
        raise RuntimeError("Duplicate contribution dates.")
    out = {
        "schema": 1, "source": "GitHub GraphQL contributionCalendar",
        "username": USER, "status": "verified",
        "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_contributions": int(cal["totalContributions"]),
        "days": days,
    }
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    print(f"Fetched {len(days)} public calendar days for {USER}.")


def load_days() -> list[tuple[date, int]]:
    if not DATA.exists():
        return []
    obj = json.loads(DATA.read_text(encoding="utf-8"))
    if obj.get("status") != "verified" or obj.get("username") != USER:
        return []
    rows = [(date.fromisoformat(d["date"]), int(d["count"]))
            for d in obj.get("days", [])]
    if any(n < 0 for _, n in rows) or len(set(d for d, _ in rows)) != len(rows):
        raise ValueError("Malformed verified contribution JSON")
    return sorted(rows)


def font_woff() -> str:
    """Subset a redistribution-permitted locally installed DejaVu Sans font."""
    chosen = os.getenv("PROFILE_FONT_PATH")
    locations = ([Path(chosen)] if chosen else []) + [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/local/share/fonts/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/DejaVuSans.ttf"),
    ]
    font_path = next((p for p in locations if p.is_file()), None)
    exe = shutil.which("pyftsubset")
    if not exe:
        raise RuntimeError("Install fonttools: pip install -r requirements-profile.txt")
    if not font_path:
        raise RuntimeError("DejaVu Sans not found. Install fonts-dejavu-core or "
                           "set PROFILE_FONT_PATH to a redistribution-permitted TTF.")
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "subset.woff"
        cmd = [
            exe, str(font_path), f"--output-file={output}", "--flavor=woff",
            "--unicodes=U+0020-007E,U+00A0-00FF,U+2013-2014,U+2022,U+2192,U+2713",
            "--layout-features=*",
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return base64.b64encode(output.read_bytes()).decode("ascii")


def xml(value: object) -> str:
    return escape(str(value), quote=True)


def rect(x: int | float, y: int | float, w: int | float, h: int | float,
         fill: str, rx: int = 0, stroke: str = "none", extra: str = "") -> str:
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" {extra}/>')


def text(x: int, y: int, s: object, size: int = 22, color: str = TEXT,
         weight: int = 500, anchor: str = "start", extra: str = "") -> str:
    return (f'<text x="{x}" y="{y}" font-family="ProfileSans,sans-serif" '
            f'font-size="{size}" font-weight="{weight}" fill="{color}" '
            f'text-anchor="{anchor}" {extra}>{xml(s)}</text>')


def base(w: int, h: int, index: int, woff: str, title: str) -> tuple[str, str]:
    delay = index * 0.15
    font_css = (
        "@font-face{font-family:ProfileSans;src:url('data:font/woff;base64,"
        + woff + "') format('woff');font-weight:100 900;font-style:normal;}"
    )
    motion = "" if STATIC else f"""
        @keyframes rise {{from {{opacity:0;transform:translateY(19px)}}
                           to {{opacity:1;transform:translateY(0)}}}}
        @keyframes breathe {{50%{{opacity:.42}}}}
        .reveal {{animation:rise .85s cubic-bezier(.16,1,.3,1) both;
                  animation-delay:{delay:.2f}s}}
        .pulse {{animation:breathe 2.4s ease-in-out infinite}}
        @media (prefers-reduced-motion: reduce) {{
          .reveal,.pulse {{animation:none!important;opacity:1!important;
                           transform:none!important}}
          .smil-motion {{display:none!important}}
        }}
    """
    if STATIC:
        motion += ".reveal{opacity:1}.smil-motion{display:none}"
    beginning = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
                 f'viewBox="0 0 {w} {h}" role="img" aria-label="{xml(title)}">'
                 f'<title>{xml(title)}</title>'
                 f'<defs><linearGradient id="brand" x1="0" y1="0" x2="1" y2="1">'
                 f'<stop stop-color="{CYAN}"/><stop offset="1" stop-color="{PURPLE}"/>'
                 '</linearGradient></defs>'
                 '<style>' + font_css + motion + '</style>'
                 + rect(0, 0, w, h, BG, 24)
                 + rect(1, 1, w - 2, h - 2, "none", 24, BORDER)
                 + rect(35, 35, 6, 40, "url(#brand)", 3)
                 + '<g class="reveal">')
    return beginning, "</g></svg>"


def caption(s: str, x: int = 60, y: int = 61) -> str:
    return text(x, y, s.upper(), 15, CYAN, 700, extra='letter-spacing="2"')


def hero(woff: str) -> str:
    a, b = base(1200, 345, 0, woff, "Aditya Jaiswal AI systems engineering profile")
    items = [caption("AI systems / ML engineering / open-source"),
             text(60, 165, "Aditya Jaiswal", 69, TEXT, 800),
             text(63, 213, "Building AI systems — from LLM agents to inference research.", 25, MUTED),
             rect(62, 245, 210, 42, BG2, 12, BORDER),
             text(82, 272, "Python · LLMs · MLOps", 17, CYAN, 700),
             rect(980, 72, 138, 138, "url(#brand)", 69),
             text(1049, 160, "AJ", 54, BG, 800, "middle")]
    portrait = ROOT / "assets" / "portrait.png"
    if portrait.is_file():
        png = base64.b64encode(portrait.read_bytes()).decode("ascii")
        items[-2:] = [
            '<defs><clipPath id="portraitclip"><circle cx="1049" cy="141" r="70"/></clipPath></defs>',
            f'<image x="979" y="71" width="140" height="140" preserveAspectRatio="xMidYMid slice" '
            f'href="data:image/png;base64,{png}" clip-path="url(#portraitclip)"/>'
        ]
    if not STATIC:
        items.append(
            f'<circle class="smil-motion" cx="1111" cy="224" r="8" fill="{GREEN}">'
            '<animate attributeName="opacity" values="1;.3;1" dur="2.5s" '
            'repeatCount="indefinite"/></circle>')
    items += [rect(60, 310, 1080, 2, BORDER)]
    return a + "".join(items) + b


def tile(woff: str, title: str, subtitle: str, badge: str,
         tint: str, idx: int) -> str:
    a, b = base(385, 195, idx, woff, title)
    content = (rect(28, 82, 5, 69, tint, 3)
               + text(47, 112, title, 29, TEXT, 800)
               + text(47, 146, subtitle, 17, MUTED)
               + text(47, 175, badge, 12, tint, 700))
    return a + content + b


def repo_card(woff: str, repo: tuple, idx: int) -> str:
    slug, name, description, tech, accent = repo
    a, b = base(1200, 200, idx, woff, f"Featured repository: {name}")
    content = (caption(f"Featured project 0{idx-5}", y=57)
               + text(58, 119, name, 42, TEXT, 800)
               + text(60, 157, description, 19, MUTED)
               + text(1130, 107, "↗", 34, accent, 800, "middle")
               + text(1126, 166, tech, 15, accent, 700, "end"))
    return a + content + b


def monthly_stats(woff: str, days: list[tuple[date, int]]) -> str:
    a, b = base(1200, 415, 4, woff, "Monthly GitHub contributions and streak statistics")
    s = caption("GitHub activity / rolling 12 calendar months")
    if not days:
        s += text(75, 230, "Awaiting verified contribution data from GitHub Actions",
                  26, MUTED)
        return a + s + b
    counts = {day: n for day, n in days}
    today = datetime.now(timezone.utc).date()
    months = []
    for i in range(11, -1, -1):
        year, month = today.year, today.month - i
        while month <= 0:
            month += 12
            year -= 1
        months.append((year, month))
    monthly = defaultdict(int)
    for day, n in days:
        monthly[(day.year, day.month)] += n
    vals = [monthly[month] for month in months]
    upper = max(vals) or 1
    active_days = sum(n > 0 for d, n in days if d <= today)
    busiest = max(days, key=lambda d: d[1])
    cursor = today if counts.get(today, 0) else today - timedelta(days=1)
    streak = 0
    while counts.get(cursor, 0) > 0:
        streak += 1
        cursor -= timedelta(days=1)
    s += text(70, 132, str(sum(n for _, n in days)), 55, TEXT, 800)
    s += text(72, 162, "contributions in fetched window", 16, MUTED)
    stats = [("CURRENT STREAK", f"{streak} days"),
             ("ACTIVE DAYS", str(active_days)),
             ("BUSIEST DAY", f"{busiest[0]:%d %b %Y} · {busiest[1]}")]
    for i, (label, value) in enumerate(stats):
        x = 470 + i * 230
        s += text(x, 93, label, 13, CYAN, 700)
        s += text(x, 125, value, 22 if i < 2 else 17, TEXT, 700)
    ybase = 339
    for i, (ym, n) in enumerate(zip(months, vals)):
        x = 75 + i * 87
        bh = round(132 * n / upper)
        s += rect(x, ybase - bh, 47, bh, "url(#brand)", 6)
        s += text(x + 23, ybase - bh - 9, str(n), 13, TEXT, 700, "middle")
        s += text(x + 23, 365, calendar.month_abbr[ym[1]], 14, MUTED, 500, "middle")
    s += text(74, 396, "Counts reflect GitHub's public contribution calendar; the first/last month may be partial.",
              13, MUTED)
    return a + s + b


def grid(woff: str, days: list[tuple[date, int]]) -> str:
    a, b = base(1200, 285, 10, woff, "Brand-color GitHub contribution heatmap")
    s = caption("Contribution calendar / GitHub verified data")
    if not days:
        s += text(80, 160, "Daily contributions will appear after the first data refresh.", 24, MUTED)
        return a + s + b
    first, last = days[0][0], days[-1][0]
    start = first - timedelta(days=(first.weekday() + 1) % 7)
    end = last + timedelta(days=(5 - last.weekday()) % 7)
    weeks = ((end - start).days // 7) + 1
    # Fit up to 54 weeks in 1050px.
    step = min(19, 1034 / max(weeks, 1))
    boxsize = step - 3
    bydate = dict(days)
    shades = ["#102238", "#12445c", "#007c9b", CYAN, PURPLE]
    for day, count in days:
        col = (day - start).days // 7
        row = (day.weekday() + 1) % 7  # Sunday first
        intensity = 0 if count == 0 else 1 if count == 1 else 2 if count < 4 else 3 if count < 8 else 4
        x = 82 + col * step
        y = 95 + row * 19
        s += rect(round(x, 2), y, round(boxsize, 2), 16, shades[intensity], 3)
    for row, label in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        s += text(31, 108 + row * 19, label, 12, MUTED)
    s += text(82, 255, f"Window: {first:%d %b %Y} — {last:%d %b %Y}", 13, MUTED)
    for i, shade in enumerate(shades):
        s += rect(1005 + i * 25, 240, 16, 16, shade, 3)
    s += text(990, 253, "less", 12, MUTED, 500, "end")
    s += text(1144, 253, "more", 12, MUTED, 500)
    return a + s + b


def render(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    woff = font_woff()
    days = load_days()
    built = {
        "hero.svg": hero(woff),
        "tile-projects.svg": tile(woff, "PROJECTS", "Explore my engineering work",
                                  "VIEW REPOSITORIES  ↗", CYAN, 1),
        "tile-research.svg": tile(woff, "RESEARCH", "Machine learning & AI systems",
                                  "PAPERS AND EXPERIMENTS  ↗", PURPLE, 2),
        "tile-connect.svg": tile(woff, "CONNECT", "Let's build useful AI systems",
                                 "WEBSITE / LINKEDIN  ↗", GREEN, 3),
        "contributions-monthly.svg": monthly_stats(woff, days),
        "contribution-grid.svg": grid(woff, days),
    }
    for i, item in enumerate(FEATURED, start=6):
        built[f"repo-{item[0].lower()}.svg"] = repo_card(woff, item, i)
    for name, data in built.items():
        (output / name).write_text(data + "\n", encoding="utf-8")
    print(f"Rendered {len(built)} SVG cards to {output}; "
          f"contribution rows: {len(days)}; STATIC={STATIC}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true",
                        help="Refresh data/contributions.json from GitHub GraphQL first")
    parser.add_argument("--out", default="cards",
                        help="Output folder relative to repo root (default cards)")
    args = parser.parse_args()
    if args.fetch:
        graph_fetch()
    target = Path(args.out)
    if not target.is_absolute():
        target = ROOT / target
    render(target)
