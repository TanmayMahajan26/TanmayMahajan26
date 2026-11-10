#!/usr/bin/env python3
"""Draws every animated SVG card used in README.md.

Usage:
  GITHUB_TOKEN=xxx python scripts/render.py   # fetch fresh data, then draw
  python scripts/render.py                    # draw from the cached data/github.json
  STATIC=1 python scripts/render.py           # draw final frames only (for screenshots)

All animation is CSS keyframes or SMIL inside each SVG, so it plays inside a plain
<img> tag on GitHub. Nothing loads from outside the file.
"""
import datetime as dt
import json
import os
import urllib.request
from collections import OrderedDict
from html import escape
from pathlib import Path

USER = "TanmayMahajan26"
ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
DATA = ROOT / "data" / "github.json"
STATIC = os.environ.get("STATIC") == "1"

SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"

C = {
    "panel": "#0f1629",
    "panel2": "#131c33",
    "line": "#223052",
    "text": "#e6ebf5",
    "mute": "#8a97b4",
    "dim": "#5b6785",
    "violet": "#a78bfa",
    "cyan": "#22d3ee",
    "amber": "#fbbf24",
    "rose": "#fb7185",
    "lime": "#a3e635",
}
HEAT = ["#17203a", "#0e4a5e", "#0b7490", "#14b8d4", "#7be7fa"]


# ---------------------------------------------------------------- data

QUERY = """query($login:String!){user(login:$login){
  contributionsCollection{contributionCalendar{totalContributions
    weeks{contributionDays{date contributionCount}}}}
  repositories(first:100,ownerAffiliations:OWNER,privacy:PUBLIC){
    nodes{name homepageUrl isFork stargazerCount}}}}"""


def load_data():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return json.loads(DATA.read_text(encoding="utf-8"))
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-cards"},
    )
    with urllib.request.urlopen(req) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise SystemExit(payload["errors"])
    data = payload["data"]["user"]
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data


def stats(data):
    cal = data["contributionsCollection"]["contributionCalendar"]
    weeks = [[(dt.date.fromisoformat(d["date"]), d["contributionCount"])
              for d in w["contributionDays"]] for w in cal["weeks"]]
    days = [d for w in weeks for d in w]

    longest = run = 0
    for _, n in days:
        run = run + 1 if n else 0
        longest = max(longest, run)

    # Current streak: a quiet today doesn't break it yet.
    current = 0
    tail = days[:-1] if days and days[-1][1] == 0 else days
    for _, n in reversed(tail):
        if not n:
            break
        current += 1

    busiest = max(days, key=lambda d: d[1])

    last = days[-1][0]
    months = OrderedDict()
    y, m = last.year, last.month
    for _ in range(12):
        months[(y, m)] = 0
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    months = OrderedDict(reversed(list(months.items())))
    for d, n in days:
        if (d.year, d.month) in months:
            months[(d.year, d.month)] += n

    repos = [r for r in data["repositories"]["nodes"] if not r["isFork"]]
    return {
        "weeks": weeks,
        "total": cal["totalContributions"],
        "longest": longest,
        "current": current,
        "busiest": busiest,
        "active": sum(1 for _, n in days if n),
        "months": months,
        "repos": len(repos),
        "live": sum(1 for r in repos if r["homepageUrl"]),
    }


# ---------------------------------------------------------------- svg helpers

BASE_CSS = (
    "text{font-family:%s}.m{font-family:%s}"
    ".up{animation:up .8s cubic-bezier(.2,.75,.25,1) backwards}"
    ".fade{animation:fade 1s ease-out backwards}"
    "@keyframes up{from{opacity:0;transform:translateY(12px)}}"
    "@keyframes fade{from{opacity:0}}"
    "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
) % (SANS, MONO)


def svg(w, h, body, label, css="", defs=""):
    static = "*{animation:none!important}" if STATIC else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{escape(label)}">'
        f"<title>{escape(label)}</title>"
        f"<style>{BASE_CSS}{css}{static}</style>"
        f"<defs>{defs}</defs>{body}</svg>"
    )


def panel(w, h, m=6):
    return (f'<rect x="{m}" y="{m}" width="{w - 2 * m}" height="{h - 2 * m}" rx="16" '
            f'fill="{C["panel"]}" stroke="{C["line"]}"/>')


def text(x, y, s, size=14, fill=None, weight=400, cls="", anchor="start", delay=None, extra=""):
    style = f' style="animation-delay:{delay:.2f}s"' if delay is not None else ""
    cl = f' class="{cls}"' if cls else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill or C["text"]}" '
            f'font-weight="{weight}" text-anchor="{anchor}"{cl}{style}{extra}>{escape(str(s))}</text>')


def width(s, size, mono=False):
    """Rough rendered width; good enough for layout of pills and wrapping."""
    return len(s) * size * (0.61 if mono else 0.56)


def wrap(s, size, max_w):
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if len(trial) * size * 0.52 > max_w and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur] if cur else lines


def pill(x, y, label, color, size=11.5, mono=True, delay=None):
    w = width(label, size, mono) + 22
    g = f'<g class="up" style="animation-delay:{delay:.2f}s">' if delay is not None else "<g>"
    return w, (
        f'{g}<rect x="{x}" y="{y}" width="{w:.1f}" height="{size + 13}" rx="{(size + 13) / 2}" '
        f'fill="{color}" fill-opacity=".12" stroke="{color}" stroke-opacity=".45"/>'
        f'<text x="{x + w / 2:.1f}" y="{y + size + 3.5:.1f}" font-size="{size}" fill="{color}" '
        f'text-anchor="middle"{" class=\"m\"" if mono else ""}>{escape(label)}</text></g>'
    )


def count_up(x, y, value, size, fill, fmt=str, begin=0.4, dur=1.4, frames=18, anchor="start"):
    """A number that ticks up from zero, using SMIL <set> frames."""
    attrs = f'x="{x}" y="{y}" font-size="{size}" font-weight="800" fill="{fill}" text-anchor="{anchor}"'
    if STATIC or value <= 0:
        return f"<text {attrs}>{escape(fmt(value))}</text>"
    out, step = [], dur / frames
    for i in range(frames + 1):
        t = i / frames
        v = value if i == frames else round(value * (1 - (1 - t) ** 3))
        fin = ' fill="freeze"' if i == frames else f' dur="{step:.3f}s"'
        out.append(f'<text {attrs} visibility="hidden">{escape(fmt(v))}'
                   f'<set attributeName="visibility" to="visible" begin="{begin + t * dur:.3f}s"{fin}/></text>')
    return "".join(out)


def write(name, content):
    CARDS.mkdir(exist_ok=True)
    (CARDS / name).write_text(content, encoding="utf-8")


# ---------------------------------------------------------------- cards

def hero():
    W, H = 840, 250
    defs = (
        f'<pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">'
        f'<path d="M24 0H0V24" fill="none" stroke="{C["line"]}" stroke-opacity=".5"/></pattern>'
        f'<radialGradient id="glow" cx="78%" cy="35%" r="45%">'
        f'<stop offset="0" stop-color="{C["violet"]}" stop-opacity=".22"/>'
        f'<stop offset="1" stop-color="{C["violet"]}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="-420" y1="0" x2="0" y2="0">'
        f'<stop offset="0" stop-color="{C["text"]}"/><stop offset=".42" stop-color="{C["text"]}"/>'
        f'<stop offset=".5" stop-color="{C["cyan"]}"/><stop offset=".56" stop-color="{C["violet"]}"/>'
        f'<stop offset=".66" stop-color="{C["text"]}"/><stop offset="1" stop-color="{C["text"]}"/>'
        + ("" if STATIC else
           '<animate attributeName="x1" values="-420;520;520" keyTimes="0;.55;1" dur="6s" begin="1s" repeatCount="indefinite"/>'
           '<animate attributeName="x2" values="0;940;940" keyTimes="0;.55;1" dur="6s" begin="1s" repeatCount="indefinite"/>')
        + '</linearGradient>'
        f'<mask id="fadeL"><rect width="{W}" height="{H}" fill="url(#mg)"/></mask>'
        f'<linearGradient id="mg"><stop offset=".45" stop-color="#000"/><stop offset=".75" stop-color="#fff"/></linearGradient>'
        f'<clipPath id="pc"><rect x="6" y="6" width="{W - 12}" height="{H - 12}" rx="16"/></clipPath>'
    )
    body = [panel(W, H),
            f'<g clip-path="url(#pc)"><rect width="{W}" height="{H}" fill="url(#grid)" mask="url(#fadeL)"/>'
            f'<rect width="{W}" height="{H}" fill="url(#glow)"/></g>']

    body.append(text(40, 62, "~/tanmay $ whoami", 14, C["cyan"], cls="m up", delay=0.1))
    body.append(f'<text x="38" y="118" font-size="50" font-weight="800" fill="url(#shine)" '
                f'letter-spacing="-1" class="up" style="animation-delay:.25s">Tanmay Mahajan</text>')

    # Typed tagline. textLength pins the width so the cursor lines up on every OS font.
    tag = "AI + full-stack engineer · hackathon builder"
    cw, size = 10.0, 16.5
    tw = len(tag) * cw
    if STATIC:
        body.append(f'<text x="40" y="156" font-size="{size}" fill="{C["mute"]}" class="m" '
                    f'textLength="{tw}" lengthAdjust="spacingAndGlyphs">{escape(tag)}</text>')
        body.append(f'<rect x="{40 + tw + 4}" y="142" width="9" height="18" fill="{C["violet"]}"/>')
    else:
        steps = ";".join(f"{i * cw:.1f}" for i in range(len(tag) + 1))
        kt = ";".join(f"{i / len(tag):.4f}" for i in range(len(tag) + 1))
        anim = f'values="{steps}" keyTimes="{kt}" calcMode="discrete" dur="2.4s" begin="0.9s" fill="freeze"'
        body.append(f'<clipPath id="type"><rect x="40" y="130" width="0" height="40">'
                    f'<animate attributeName="width" {anim}/></rect></clipPath>')
        body.append(f'<text x="40" y="156" font-size="{size}" fill="{C["mute"]}" class="m" clip-path="url(#type)" '
                    f'textLength="{tw}" lengthAdjust="spacingAndGlyphs">{escape(tag)}</text>')
        body.append(f'<rect x="44" y="142" width="9" height="18" fill="{C["violet"]}">'
                    f'<animate attributeName="x" values="{";".join(f"{44 + i * cw:.1f}" for i in range(len(tag) + 1))}" '
                    f'keyTimes="{kt}" calcMode="discrete" dur="2.4s" begin="0.9s" fill="freeze"/>'
                    f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" dur="1s" repeatCount="indefinite"/></rect>')

    body.append(text(40, 188, "B.E. Computer Engineering @ Fr. CRCE  ·  Mumbai, India", 14, C["dim"], cls="up", delay=0.5))

    x = 40
    for label, color, d in [("1st place · CODEISSANCE 2026", C["amber"], 1.2),
                            ("4× hackathon finalist", C["rose"], 1.35),
                            ("Exec. Producer · TEDxCRCE", C["lime"], 1.5)]:
        w, p = pill(x, 202, label, color, 11, delay=d)
        body.append(p)
        x += w + 9

    # A little neural net on the right. Pulses travel along its edges.
    layers = [[(668, 80), (668, 128), (668, 176)],
              [(730, 64), (730, 106), (730, 150), (730, 192)],
              [(792, 100), (792, 156)]]
    edges = [(a, b) for l in range(2) for a in layers[l] for b in layers[l + 1]]
    g = ['<g class="fade" style="animation-delay:.6s">']
    for (x1, y1), (x2, y2) in edges:
        g.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{C["violet"]}" stroke-opacity=".28" stroke-width="1.2"/>')
    if not STATIC:
        for i, ((x1, y1), (x2, y2)) in enumerate(edges):
            if i % 3:
                continue
            col = [C["cyan"], C["violet"], C["lime"]][i % 3 if i % 2 else (i // 3) % 3]
            g.append(f'<circle r="2.6" fill="{col}" opacity="0">'
                     f'<animateMotion path="M{x1} {y1}L{x2} {y2}" dur="1.6s" begin="{1.2 + i * .23:.2f}s" repeatCount="indefinite"/>'
                     f'<animate attributeName="opacity" values="0;1;1;0" dur="1.6s" begin="{1.2 + i * .23:.2f}s" repeatCount="indefinite"/></circle>')
    for li, layer in enumerate(layers):
        col = [C["cyan"], C["violet"], C["lime"]][li]
        for ni, (cx, cy) in enumerate(layer):
            pulse = "" if STATIC else (
                f'<animate attributeName="r" values="7;9;7" dur="2.4s" begin="{ni * .4 + li * .3:.1f}s" repeatCount="indefinite"/>')
            g.append(f'<circle cx="{cx}" cy="{cy}" r="7" fill="{C["panel2"]}" stroke="{col}" stroke-width="2">{pulse}</circle>'
                     f'<circle cx="{cx}" cy="{cy}" r="2.5" fill="{col}"/>')
    g.append("</g>")
    body.append("".join(g))

    write("hero.svg", svg(W, H, "".join(body),
                          "Tanmay Mahajan. AI and full-stack engineer, hackathon builder. Computer Engineering at Fr. CRCE, Mumbai.",
                          defs=defs))


def heatmap(s):
    W, H = 840, 206
    weeks = s["weeks"]
    x0, y0, step, cell = 46, 62, 14.3, 11
    peak = max((n for w in weeks for _, n in w), default=0) or 1

    def level(n):
        if n == 0:
            return 0
        return min(4, 1 + int(3.999 * (n - 1) / max(peak - 1, 1)))

    css = (".c{transform-box:fill-box;transform-origin:center;animation:pop .45s cubic-bezier(.3,1.6,.5,1) backwards}"
           "@keyframes pop{from{opacity:0;transform:scale(.2)}}")
    body = [panel(W, H),
            text(32, 38, "contributions · last 12 months", 13, C["mute"], cls="m fade"),
            f'<text x="808" y="38" font-size="13" fill="{C["mute"]}" text-anchor="end" class="m fade">'
            f'<tspan fill="{C["cyan"]}" font-weight="700">{s["total"]}</tspan> in the last year</text>']

    seen = set()
    for wi, week in enumerate(weeks):
        first = week[0][0]
        key = (first.year, first.month)
        if key not in seen and first.day <= 7 and wi < len(weeks) - 2:
            seen.add(key)
            body.append(text(x0 + wi * step, y0 - 8, first.strftime("%b"), 10.5, C["dim"], cls="m"))
        for d, n in week:
            row = (d.weekday() + 1) % 7  # Sunday on top, like GitHub
            delay = 0.15 + wi * 0.016 + row * 0.02
            body.append(f'<rect class="c" style="animation-delay:{delay:.2f}s" x="{x0 + wi * step:.1f}" '
                        f'y="{y0 + row * step:.1f}" width="{cell}" height="{cell}" rx="2.5" fill="{HEAT[level(n)]}">'
                        f'<title>{n} on {d:%b %d}</title></rect>')
    for row, lbl in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        body.append(text(x0 - 8, y0 + row * step + 9, lbl, 10, C["dim"], cls="m", anchor="end"))

    lx = 808 - 5 * 15 - 34
    body.append(text(lx - 6, 184, "less", 10.5, C["dim"], cls="m", anchor="end"))
    for i, col in enumerate(HEAT):
        body.append(f'<rect x="{lx + i * 15}" y="175" width="11" height="11" rx="2.5" fill="{col}"/>')
    body.append(text(lx + 5 * 15 + 2, 184, "more", 10.5, C["dim"], cls="m"))
    body.append(text(32, 184, "refreshed daily by a GitHub Action", 10.5, C["dim"], cls="m"))

    write("heatmap.svg", svg(W, H, "".join(body), f"Contribution graph: {s['total']} contributions in the last year", css))


def activity(s):
    W, H = 840, 290
    css = (".bar{transform-box:fill-box;transform-origin:bottom;animation:grow 1s cubic-bezier(.2,.8,.2,1) backwards}"
           "@keyframes grow{from{transform:scaleY(0)}}")
    defs = (f'<linearGradient id="bg" x1="0" y1="1" x2="0" y2="0">'
            f'<stop offset="0" stop-color="{C["violet"]}"/><stop offset="1" stop-color="{C["cyan"]}"/></linearGradient>')
    body = [panel(W, H),
            text(32, 40, "streaks & stats", 13, C["mute"], cls="m fade"),
            f'<line x1="300" y1="32" x2="300" y2="258" stroke="{C["line"]}"/>',
            text(330, 40, "commits by month", 13, C["mute"], cls="m fade")]

    bd, bn = s["busiest"]
    tiles = [(32, 112, s["total"], "contributions", "past 12 months", C["cyan"]),
             (170, 112, s["longest"], "longest streak", "days in a row", C["violet"]),
             (32, 216, s["active"], "active days", "days with commits", C["lime"]),
             (170, 216, bn, "busiest day", f"{bd:%b %d, %Y}", C["amber"])]
    for i, (x, y, v, lbl, sub, col) in enumerate(tiles):
        body.append(f'<g class="up" style="animation-delay:{0.15 + i * 0.12:.2f}s">')
        body.append(count_up(x, y, v, 38, col, begin=0.35 + i * 0.12))
        body.append(text(x, y + 22, lbl, 13, C["text"], 600))
        body.append(text(x, y + 40, sub, 11.5, C["dim"], cls="m"))
        body.append("</g>")

    months = list(s["months"].items())
    peak = max(v for _, v in months) or 1
    bx0, base, maxh = 336, 236, 160
    slot = (808 - bx0) / len(months)
    for i, ((y, m), v) in enumerate(months):
        h = max(3, maxh * v / peak) if v else 3
        x = bx0 + i * slot + (slot - 24) / 2
        fill = "url(#bg)" if v else C["line"]
        delay = 0.3 + i * 0.07
        body.append(f'<rect class="bar" style="animation-delay:{delay:.2f}s" x="{x:.1f}" y="{base - h:.1f}" '
                    f'width="24" height="{h:.1f}" rx="5" fill="{fill}"/>')
        if v:
            body.append(text(f"{x + 12:.1f}", f"{base - h - 8:.1f}", v, 11, C["text"], 600, cls="m up",
                             anchor="middle", delay=delay + 0.6))
        body.append(text(f"{x + 12:.1f}", base + 20, dt.date(y, m, 1).strftime("%b"), 10.5, C["dim"],
                         cls="m", anchor="middle"))

    write("activity.svg", svg(W, H, "".join(body),
                              f"{s['total']} contributions this year, longest streak {s['longest']} days, {s['active']} active days",
                              css, defs))


def tile(name, kicker, color, value, big, line1, line2, cta, motif, label):
    W, H = 280, 236
    body = [panel(W, H),
            f'<rect x="6" y="6" width="{W - 12}" height="4" rx="2" fill="{color}"/>',
            f'<circle cx="31" cy="38" r="4" fill="{color}"/>',
            text(42, 42, kicker, 12, color, 700, cls="m", extra=' letter-spacing="2"'),
            motif]
    if value is not None:
        body.append(count_up(26, 112, value, 54, C["text"], begin=0.5))
    else:
        body.append(text(26, 112, big, 54, C["text"], 800, cls="up", delay=0.3))
    for i, ln in enumerate([line1, line2]):
        body.append(text(26, 144 + i * 20, ln, 13, C["mute"] if i else C["text"], 600 if not i else 400,
                         cls="up", delay=0.6 + i * 0.1))
    body.append(text(26, 206, cta, 12, color, cls="m up", delay=0.9))
    write(name, svg(W, H, "".join(body), label))


def tiles(s):
    S = not STATIC
    blocks = "".join(
        f'<rect class="up" style="animation-delay:{0.4 + i * 0.18:.2f}s" x="{x}" y="{y}" width="16" height="16" rx="3" '
        f'fill="{C["cyan"]}" fill-opacity="{o}"/>'
        for i, (x, y, o) in enumerate([(206, 52, .35), (226, 52, .6), (246, 52, .9), (226, 32, .5), (246, 32, .75)]))
    tile("build.svg", "BUILD", C["cyan"], s["repos"], None,
         "public repositories", f"{s['live']} shipped with live demos", "→ browse repos", blocks,
         f"BUILD: {s['repos']} public repositories, {s['live']} with live demos")

    star = ("M0 -18L5 -6L18 -5L8 3L11 16L0 9L-11 16L-8 3L-18 -5L-5 -6Z")
    spin = ('<animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="14s" additive="sum" repeatCount="indefinite"/>' if S else "")
    trophy = (f'<g transform="translate(236 46)"><g>{spin}<path d="{star}" fill="{C["amber"]}" fill-opacity=".18" '
              f'stroke="{C["amber"]}" stroke-width="1.5" stroke-linejoin="round"/></g>'
              f'<circle r="3" fill="{C["amber"]}"/></g>')
    tile("win.svg", "WIN", C["amber"], 4, None,
         "hackathon finals", "1st place · CODEISSANCE 2026", "→ the winning build", trophy,
         "WIN: 4 hackathon finals, including 1st place at CODEISSANCE 2026")

    rings = "".join(
        f'<circle cx="236" cy="46" r="12" fill="none" stroke="{C["lime"]}" stroke-width="1.5" opacity="0">'
        f'<animate attributeName="r" values="12;30" dur="2.4s" begin="{i * 0.8}s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values=".8;0" dur="2.4s" begin="{i * 0.8}s" repeatCount="indefinite"/></circle>'
        for i in range(3)) if S else ""
    play = (f'{rings}<circle cx="236" cy="46" r="14" fill="{C["lime"]}" fill-opacity=".15" stroke="{C["lime"]}" stroke-width="1.5"/>'
            f'<path d="M231 39L243 46L231 53Z" fill="{C["lime"]}"/>')
    tile("create.svg", "CREATE", C["lime"], None, "TEDx",
         "Executive Producer, TEDxCRCE", "stage · AV · livestream · video", "→ say hi on LinkedIn", play,
         "CREATE: Executive Producer at TEDxCRCE")


def title(name, label, sub):
    W, H = 840, 70
    css = (".ln{stroke-dasharray:600;animation:draw 1.4s ease-out backwards}"
           "@keyframes draw{from{stroke-dashoffset:600}}")
    tw = width(label, 20) + 52
    body = [text(10, 44, "//", 20, C["violet"], 700, cls="m"),
            text(42, 44, label, 20, C["text"], 700, cls="up"),
            f'<line class="ln" x1="{tw + 20:.0f}" y1="38" x2="{830 - width(sub, 12, True) - 16:.0f}" y2="38" '
            f'stroke="{C["line"]}" stroke-width="1.5"/>',
            text(830, 42, sub, 12, C["dim"], cls="m fade", anchor="end")]
    write(name, svg(W, H, "".join(body), label, css))


REPOS = [
    ("repo-nexus360.svg", "Nexus360", "1st place", C["amber"],
     "Customer 360 for finance: a 7-stage matching pipeline that unifies records across equity, funds, insurance and loans.",
     ["FastAPI", "React", "Postgres"]),
    ("repo-synapse.svg", "SYNAPSE", "newest", C["cyan"],
     "A compiler for AI agent workflows: builds an execution graph, applies proven optimizations, learns from live traces.",
     ["LLMs", "compilers", "evals"]),
    ("repo-zenthera.svg", "Zenthera", "92.4% acc", C["lime"],
     "Predicts antibiotic resistance straight from bacterial genomes with k-mer features, trained on 148K+ records.",
     ["ML", "Flask", "MERN"]),
    ("repo-flux.svg", "Flux Forecast", "ISRO", C["violet"],
     "Forecasts hazardous electron flux at geostationary orbit 30 to 45 minutes ahead, with uncertainty bounds.",
     ["PyTorch", "FastAPI", "Timescale"]),
    ("repo-justicegrid.svg", "JusticeGrid", "finalist", C["rose"],
     "Legal intelligence for India's undertrial crisis. Surfaces bail-eligible cases and predicts adjournments.",
     ["Next.js", "FastAPI", "Gemini"]),
    ("repo-ecosentinel.svg", "EcoSentinel", "geo", C["cyan"],
     "Coastal monitoring across 8 zones: live telemetry, time-series forecasts and what-if risk simulations.",
     ["FastAPI", "GIS", "dashboards"]),
]


def repo_card(i, fname, name, badge, color, desc, tags):
    W, H = 280, 200
    d = 0.1 + (i % 3) * 0.15 + (i // 3) * 0.1
    bw = width(badge, 10.5, True) + 18
    body = [panel(W, H),
            f'<g class="up" style="animation-delay:{d:.2f}s">',
            f'<path d="M26 30h10a3 3 0 0 1 3 3v14a3 3 0 0 1-3 3H26a3 3 0 0 1-3-3V33a3 3 0 0 1 3-3z" fill="none" stroke="{color}" stroke-width="1.6"/>'
            f'<path d="M27 36h8M27 41h8M27 46h5" stroke="{color}" stroke-width="1.4"/>',
            text(50, 46, name, 17, C["text"], 700),
            f'<rect x="{254 - bw:.1f}" y="31" width="{bw:.1f}" height="20" rx="10" fill="{color}" fill-opacity=".14"/>',
            text(f"{254 - bw / 2:.1f}", 45, badge, 10.5, color, 600, cls="m", anchor="middle")]
    for j, ln in enumerate(wrap(desc, 12.5, 232)[:4]):
        body.append(text(26, 78 + j * 19, ln, 12.5, C["mute"]))
    x = 26
    for t in tags:
        w = width(t, 10.5, True) + 16
        body.append(f'<rect x="{x}" y="158" width="{w:.1f}" height="20" rx="5" fill="{C["panel2"]}" stroke="{C["line"]}"/>'
                    + text(f"{x + w / 2:.1f}", 172, t, 10.5, C["text"], cls="m", anchor="middle"))
        x += w + 6
    body.append("</g>")
    write(fname, svg(W, H, "".join(body), f"{name}: {desc}"))


TOOLS = [("Python", "#3572A5"), ("JavaScript", "#f1e05a"), ("TypeScript", "#3178c6"), ("Java", "#b07219"),
         ("C++", "#f34b7d"), ("React", "#61dafb"), ("Next.js", "#e6ebf5"), ("Node.js", "#5fa04e"),
         ("Express", "#8a97b4"), ("FastAPI", "#009688"), ("PyTorch", "#ee4c2c"), ("scikit-learn", "#f7931e"),
         ("MongoDB", "#47a248"), ("PostgreSQL", "#4169e1"), ("Docker", "#2496ed"), ("Android", "#3ddc84"),
         ("Tailwind", "#38bdf8"), ("Git", "#f05032")]


def toolbox():
    W = 840
    rows, row, x = [], [], 0
    for name, col in TOOLS:
        w = width(name, 12.5) + 36
        if x + w > W - 64 and row:
            rows.append(row)
            row, x = [], 0
        row.append((name, col, w))
        x += w + 10
    rows.append(row)
    H = 30 + len(rows) * 42 + 18
    body = [panel(W, H)]
    k = 0
    for r, items in enumerate(rows):
        total = sum(w for _, _, w in items) + 10 * (len(items) - 1)
        x = (W - total) / 2
        y = 30 + r * 42
        for name, col, w in items:
            body.append(f'<g class="up" style="animation-delay:{0.1 + k * 0.05:.2f}s">'
                        f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="30" rx="15" fill="{C["panel2"]}" stroke="{C["line"]}"/>'
                        f'<circle cx="{x + 16:.1f}" cy="{y + 15}" r="4.5" fill="{col}"/>'
                        + text(f"{x + 27:.1f}", y + 20, name, 12.5, C["text"]) + "</g>")
            x += w + 10
            k += 1
    write("toolbox.svg", svg(W, H, "".join(body), "Toolbox: " + ", ".join(n for n, _ in TOOLS)))


def main():
    s = stats(load_data())
    hero()
    heatmap(s)
    activity(s)
    tiles(s)
    title("title-builds.svg", "featured builds", "hackathons & side projects")
    title("title-toolbox.svg", "toolbox", "what I reach for")
    for i, r in enumerate(REPOS):
        repo_card(i, *r)
    toolbox()
    print(f"drew cards: {s['total']} contributions, {s['repos']} repos, streak {s['current']}/{s['longest']}")


if __name__ == "__main__":
    main()
