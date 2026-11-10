#!/usr/bin/env python3
"""Draws every animated SVG card used in README.md.

Usage:
  GITHUB_TOKEN=xxx python scripts/render.py   # fetch fresh data, then draw
  python scripts/render.py                    # draw from the cached data/github.json
  STATIC=1 python scripts/render.py           # final frames only (for screenshots)

Design: paper cards, ink type, one blue. Fonts (Instrument Serif, Geist, Geist Mono,
all OFL) are subset per card and embedded, because an SVG inside <img> can't fetch
anything. Animation is CSS keyframes plus SMIL, which both play inside <img>.

Drop a square-ish photo at data/photo.jpg (or .png) to swap the TM monogram in the
hero for an ASCII portrait of you.
"""
import base64
import datetime as dt
import io
import json
import os
import urllib.request
from collections import OrderedDict, defaultdict
from html import escape
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

USER = "TanmayMahajan26"
ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
DATA = ROOT / "data" / "github.json"
FONT_DIR = ROOT / "fonts"
STATIC = os.environ.get("STATIC") == "1"

PAPER = "#f4f2ec"
EDGE = "#e2ded4"
INK = "#141414"
GREY = "#5f5d58"
FAINT = "#9d998f"
BLUE = "#2f4cf0"
RED = "#ee3a2c"
YELLOW = "#fcc61d"
HEAT = ["#e4e1d9", "#c5cffb", "#91a4f7", "#5872f2", "#2f4cf0"]

# key: (file, css family, weight, style, fallback stack)
FONTS = {
    "serif": ("serif-400.woff", "TSerif", 400, "normal", "Georgia,serif"),
    "serifi": ("serif-italic.woff", "TSerif", 400, "italic", "Georgia,serif"),
    "sans": ("geist-400.woff", "TSans", 400, "normal", "'Segoe UI',Helvetica,Arial,sans-serif"),
    "sans6": ("geist-600.woff", "TSans", 600, "normal", "'Segoe UI',Helvetica,Arial,sans-serif"),
    "mono": ("geistmono-400.woff", "TMono", 400, "normal", "Consolas,Menlo,monospace"),
}
_ttf = {}


def ttf(key):
    if key not in _ttf:
        _ttf[key] = TTFont(FONT_DIR / FONTS[key][0])
    return _ttf[key]


def measure(s, font, size, ls=0.0):
    f = ttf(font)
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    return sum(hmtx[cmap.get(ord(c), cmap[32])][0] for c in s) * size / upm + ls * len(s)


def wrap(s, font, size, max_w):
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if measure(trial, font, size) > max_w and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur] if cur else lines


def font_face(key, chars):
    file, fam, weight, style, _ = FONTS[key]
    opts = subset.Options()
    opts.flavor = "woff"
    opts.name_IDs = []
    opts.layout_features = ["kern", "liga"]
    f = TTFont(FONT_DIR / file)
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(sorted(chars)) + " ")
    sub.subset(f)
    f.flavor = "woff"
    buf = io.BytesIO()
    f.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return (f"@font-face{{font-family:{fam};font-weight:{weight};font-style:{style};"
            f"src:url(data:font/woff;base64,{b64}) format('woff')}}")


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
        "active": sum(1 for _, n in days if n),
        "days": len(days),
        "busiest": max(days, key=lambda d: d[1]),
        "months": months,
        "repos": len(repos),
        "live": sum(1 for r in repos if r["homepageUrl"]),
    }


# ---------------------------------------------------------------- card builder

BASE_CSS = (
    ".up{animation:up .9s cubic-bezier(.2,.75,.25,1) backwards}"
    ".fade{animation:fade 1.1s ease-out backwards}"
    "@keyframes up{from{opacity:0;transform:translateY(14px)}}"
    "@keyframes fade{from{opacity:0}}"
    "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
)


class Card:
    def __init__(self, w, h, label):
        self.w, self.h, self.label = w, h, label
        self.parts, self.defs, self.css = [], [], []
        self.used = defaultdict(set)

    def add(self, *raw):
        self.parts.extend(raw)

    def text_el(self, x, y, s, font="sans", size=14, fill=INK, anchor="start", cls="", delay=None, ls=0, extra="", spans=None):
        """spans: list of (text, font, fill) pieces drawn inline after `s`."""
        _, fam, weight, style, fb = FONTS[font]
        self.used[font].update(s)
        attrs = (f'x="{x}" y="{y}" font-family="{fam},{fb}" font-weight="{weight}" font-style="{style}" '
                 f'font-size="{size}" fill="{fill}" text-anchor="{anchor}"')
        if ls:
            attrs += f' letter-spacing="{ls}"'
        if cls:
            attrs += f' class="{cls}"'
        if delay is not None:
            attrs += f' style="animation-delay:{delay:.2f}s"'
        inner = escape(s)
        for t, f2, fill2 in spans or []:
            _, fam2, w2, st2, fb2 = FONTS[f2]
            self.used[f2].update(t)
            inner += (f'<tspan font-family="{fam2},{fb2}" font-weight="{w2}" font-style="{st2}" '
                      f'fill="{fill2}">{escape(t)}</tspan>')
        return f"<text {attrs}{extra}>{inner}</text>"

    def text(self, *a, **k):
        self.add(self.text_el(*a, **k))

    def count_up(self, x, y, value, font, size, fill, fmt=str, begin=0.4, dur=1.4, frames=18):
        """A number that ticks up from zero, via SMIL <set> frames."""
        self.used[font].update("0123456789," + fmt(value))
        if STATIC or value <= 0:
            self.text(x, y, fmt(value), font, size, fill)
            return
        step = dur / frames
        for i in range(frames + 1):
            t = i / frames
            v = value if i == frames else round(value * (1 - (1 - t) ** 3))
            timing = ' fill="freeze"' if i == frames else f' dur="{step:.3f}s"'
            el = self.text_el(x, y, fmt(v), font, size, fill,
                              extra=' visibility="hidden"')
            self.add(el.replace("</text>", f'<set attributeName="visibility" to="visible" '
                                           f'begin="{begin + t * dur:.3f}s"{timing}/></text>'))

    def paper(self, fill=PAPER, m=5, stroke=EDGE):
        self.add(f'<rect x="{m}" y="{m}" width="{self.w - 2 * m}" height="{self.h - 2 * m}" rx="14" '
                 f'fill="{fill}"' + (f' stroke="{stroke}"' if stroke else "") + "/>")

    def render(self):
        faces = "".join(font_face(k, v) for k, v in self.used.items() if v)
        static = "*{animation:none!important}" if STATIC else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{escape(self.label)}">'
                f"<title>{escape(self.label)}</title>"
                f"<style>{faces}{BASE_CSS}{''.join(self.css)}{static}</style>"
                f"<defs>{''.join(self.defs)}</defs>{''.join(self.parts)}</svg>")

    def save(self, name):
        CARDS.mkdir(exist_ok=True)
        (CARDS / name).write_text(self.render(), encoding="utf-8")


def arrow(x, y, color, size=10, up=False):
    """A small arrow drawn as a path (the fonts have no arrow glyphs)."""
    s = size
    if up:  # north-east arrow
        return (f'<path d="M{x} {y + s}L{x + s} {y}M{x + 3} {y}H{x + s}V{y + s - 3}" fill="none" '
                f'stroke="{color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>')
    return (f'<path d="M{x} {y + s / 2}H{x + s}M{x + s - 4} {y + s / 2 - 4}L{x + s} {y + s / 2}L{x + s - 4} {y + s / 2 + 4}" '
            f'fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>')


def kicker(card, x, y, label, color=GREY, square=None, delay=0.05):
    if square:
        card.add(f'<rect x="{x}" y="{y - 8}" width="7" height="7" fill="{square}" class="fade" '
                 f'style="animation-delay:{delay:.2f}s"/>')
        x += 15
    card.text(x, y, label, "mono", 11, color, ls=1.5, cls="fade", delay=delay)


# ---------------------------------------------------------------- portrait

def portrait_rows(cols, rows, cell_w, cell_h):
    """ASCII art rows: a photo from data/photo.* if present, else a TM monogram."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

    W, H = int(cols * cell_w * 4), int(rows * cell_h * 4)
    photo = next((p for p in (ROOT / "data").glob("photo.*")), None)
    if photo:
        img = ImageOps.fit(ImageOps.grayscale(Image.open(photo)), (W, H), centering=(0.5, 0.35))
        img = ImageOps.autocontrast(img, cutoff=2)
    else:
        img = Image.new("L", (W, H), 255)
        d = ImageDraw.Draw(img)
        tmp = io.BytesIO()
        ft2 = TTFont(FONT_DIR / FONTS["serifi"][0])
        ft2.flavor = None
        ft2.save(tmp)
        tmp.seek(0)
        font = ImageFont.truetype(tmp, int(H * 0.72))
        box = d.textbbox((0, 0), "TM", font=font)
        tx = (W - (box[2] - box[0])) / 2 - box[0]
        ty = (H - (box[3] - box[1])) / 2 - box[1]
        d.text((tx, ty), "TM", fill=0, font=font)
        img = img.filter(ImageFilter.GaussianBlur(W / 160))
    small = img.resize((cols, rows), Image.LANCZOS)
    ramp = " .,:;-~=+*o#%@" if photo else "  ..::--==++**##"
    out = []
    for r in range(rows):
        line = ""
        for c in range(cols):
            v = 1 - small.getpixel((c, r)) / 255
            line += ramp[min(len(ramp) - 1, int(v ** 0.9 * len(ramp)))]
        out.append(line)
    return out


# ---------------------------------------------------------------- cards

def hero():
    c = Card(840, 400, "Tanmay Mahajan. I build AI products at hackathons, ship them live, and produce the TEDx stage at my college.")
    c.paper()
    kicker(c, 44, 58, "COMPUTER ENGINEERING  ·  FR. CRCE, MUMBAI", square=BLUE)

    c.text(38, 168, "Tanmay", "serif", 100, INK, cls="up", delay=0.15, ls=-1.5)
    c.defs.append(
        f'<linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="-300" y1="0" x2="0" y2="0">'
        f'<stop offset="0" stop-color="{BLUE}"/><stop offset=".45" stop-color="{BLUE}"/>'
        f'<stop offset=".55" stop-color="#a9b6ff"/><stop offset=".65" stop-color="{BLUE}"/>'
        f'<stop offset="1" stop-color="{BLUE}"/>'
        + ("" if STATIC else
           '<animate attributeName="x1" values="-300;520;520" keyTimes="0;.45;1" dur="7s" begin="1.4s" repeatCount="indefinite"/>'
           '<animate attributeName="x2" values="0;820;820" keyTimes="0;.45;1" dur="7s" begin="1.4s" repeatCount="indefinite"/>')
        + "</linearGradient>")
    c.text(62, 268, "Mahajan", "serifi", 100, "url(#shine)", cls="up", delay=0.3, ls=-1.5)

    for i, ln in enumerate(["I build AI products at hackathons, ship them live,",
                            "and produce the TEDx stage at my college."]):
        c.text(44, 318 + i * 23, ln, "sans", 16.5, "#2c2c2a", cls="up", delay=0.5 + i * 0.08)
    link = "tanmay-portfolio-fsd.vercel.app"
    c.text(44, 372, link, "mono", 12, INK, cls="fade", delay=0.8)
    lw = measure(link, "mono", 12)
    c.add(f'<g class="fade" style="animation-delay:.8s">{arrow(44 + lw + 9, 362, BLUE, 8, up=True)}</g>')

    # ASCII portrait on the right, revealed row by row like a scan.
    cols, rows, size, lh = 58, 42, 8.6, 7.4
    cw = measure("M", "mono", size)
    lines = portrait_rows(cols, rows, cw, lh)
    x0, y0 = 800 - cols * cw, 200 - rows * lh / 2 + lh
    c.css.append(".scan{animation:scan .5s ease-out backwards}@keyframes scan{from{opacity:0}}")
    for r, ln in enumerate(lines):
        if not ln.strip():
            continue
        c.text(f"{x0:.1f}", f"{y0 + r * lh:.1f}", ln, "mono", size, "#5a5852", cls="scan",
               delay=0.4 + r * 0.035, extra=' xml:space="preserve"')
    c.save("hero.svg")


def heatmap(s):
    c = Card(840, 236, f"Contribution graph in blue: {s['total']} contributions in the last year")
    c.paper()
    c.text(42, 70, "Every commit, ", "serif", 36, INK, cls="up", spans=[("in blue", "serifi", BLUE)])
    c.text(798, 64, "REFRESHED DAILY", "mono", 10.5, GREY, anchor="end", ls=1.5, cls="fade")

    weeks = s["weeks"]
    x0, y0, step, cell = 42, 96, 756 / len(weeks), 11.6
    peak = max((n for w in weeks for _, n in w), default=0) or 1

    def level(n):
        return 0 if n == 0 else min(4, 1 + int(3.999 * (n - 1) / max(peak - 1, 1)))

    c.css.append(".c{transform-box:fill-box;transform-origin:center;"
                 "animation:pop .5s cubic-bezier(.3,1.5,.5,1) backwards}"
                 "@keyframes pop{from{opacity:0;transform:scale(.2)}}")
    seen = set()
    for wi, week in enumerate(weeks):
        first = week[0][0]
        if first.day <= 7 and (first.year, first.month) not in seen and 0 < wi and x0 + wi * step < 798 - 26 - 5 * 15 - 60:
            seen.add((first.year, first.month))
            c.text(f"{x0 + wi * step:.1f}", 218, first.strftime("%b"), "mono", 10.5, FAINT)
        for d, n in week:
            row = (d.weekday() + 1) % 7
            c.add(f'<rect class="c" style="animation-delay:{0.15 + wi * 0.017 + row * 0.025:.2f}s" '
                  f'x="{x0 + wi * step:.1f}" y="{y0 + row * step:.1f}" width="{cell}" height="{cell}" rx="3" '
                  f'fill="{HEAT[level(n)]}"><title>{n} on {d:%b %d}</title></rect>')
    lx = 798 - 26 - 5 * 15
    c.text(lx - 6, 218, "less", "mono", 10.5, FAINT, anchor="end")
    for i, col in enumerate(HEAT):
        c.add(f'<rect x="{lx + i * 15}" y="209" width="11" height="11" rx="2.5" fill="{col}"/>')
    c.text(798, 218, "more", "mono", 10.5, FAINT, anchor="end")
    c.save("heatmap.svg")


def activity(s):
    c = Card(840, 330, f"{s['total']} contributions in the last 12 months")
    c.paper()
    kicker(c, 42, 58, "THE LAST 12 MONTHS ON GITHUB")
    total = s["total"]
    fmt = lambda v: f"{v:,}"
    c.count_up(40, 118, total, "serif", 60, INK, fmt=fmt, begin=0.3)
    c.text(f"{40 + measure(fmt(total), 'serif', 60) + 14:.1f}", 118, "contributions", "serifi", 60, INK,
           cls="fade", delay=0.5, ls=-0.5)

    # Monthly bars: ink, the best month in blue, the month in progress greyed.
    months = list(s["months"].items())
    peak_v = max(v for _, v in months) or 1
    peak_i = max(range(len(months)), key=lambda i: months[i][1])
    bx0, bx1, base, maxh = 42, 548, 272, 112
    slot = (bx1 - bx0) / len(months)
    bw = slot - 11
    c.css.append(".bar{transform-box:fill-box;transform-origin:bottom;"
                 "animation:grow 1.1s cubic-bezier(.2,.8,.2,1) backwards}@keyframes grow{from{transform:scaleY(0)}}")
    for i, ((y, m), v) in enumerate(months):
        h = max(4, maxh * v / peak_v)
        x = bx0 + i * slot
        col = BLUE if i == peak_i else ("#d6d2c8" if i == len(months) - 1 else INK)
        d = 0.35 + i * 0.06
        c.add(f'<rect class="bar" style="animation-delay:{d:.2f}s" x="{x:.1f}" y="{base - h:.1f}" '
              f'width="{bw:.1f}" height="{h:.1f}" rx="2" fill="{col}"/>')
        if i == peak_i:
            c.text(f"{x + bw / 2:.1f}", f"{base - h - 9:.1f}", fmt(v), "mono", 10.5, BLUE, anchor="middle",
                   cls="fade", delay=d + 0.8)
        c.text(f"{x + bw / 2:.1f}", base + 22, dt.date(y, m, 1).strftime("%b"), "mono", 10.5, GREY,
               anchor="middle")

    # Right column of stats with hairlines between.
    bd, bn = s["busiest"]
    rx = 600
    items = [
        (s["longest"], "days" if s["longest"] != 1 else "day", None, "longest streak, in a row"),
        (s["active"], None, f"/ {s['days']}", "days with a commit"),
        (bn, None, None, f"on the busiest day, {bd:%b %d}"),
    ]
    for i, (v, unit, rest, sub) in enumerate(items):
        y = 96 + i * 82
        d = 0.5 + i * 0.15
        c.count_up(rx, y, v, "serif", 40, INK, begin=d)
        vw = measure(str(v), "serif", 40)
        if unit:
            c.text(f"{rx + vw + 9:.1f}", y, unit, "serifi", 40, INK, cls="fade", delay=d + 1)
        if rest:
            c.text(f"{rx + vw + 6:.1f}", y, rest, "serif", 40, FAINT, cls="fade", delay=d + 1)
        c.text(rx + 2, y + 22, sub, "sans", 12.5, GREY, cls="fade", delay=d)
        if i < 2:
            c.add(f'<line x1="{rx}" y1="{y + 40}" x2="798" y2="{y + 40}" stroke="{EDGE}" stroke-width="1.2"/>')
    c.save("activity.svg")


def tile(name, kicker_label, bg, fg, big, body, label, value=None, suffix="", sheen_delay=0.0):
    c = Card(280, 200, label)
    c.paper(bg, stroke=None)
    c.defs.append(f'<clipPath id="tc"><rect x="5" y="5" width="270" height="190" rx="14"/></clipPath>'
                  f'<linearGradient id="sh" x1="0" y1="0" x2="1" y2="0">'
                  f'<stop offset="0" stop-color="#fff" stop-opacity="0"/>'
                  f'<stop offset=".5" stop-color="#fff" stop-opacity=".28"/>'
                  f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    if not STATIC:
        c.add(f'<g clip-path="url(#tc)"><rect x="-140" y="-40" width="110" height="300" fill="url(#sh)" '
              f'transform="skewX(-20)"><animate attributeName="x" values="-140;420;420" keyTimes="0;.3;1" '
              f'dur="8s" begin="{1.5 + sheen_delay}s" repeatCount="indefinite"/></rect></g>')
    c.text(24, 44, kicker_label, "mono", 11, fg, ls=1.5)
    c.add(arrow(244, 34, fg, 11))
    if value is not None:
        c.count_up(22, 110, value, "serifi", 46, fg, fmt=lambda v: f"{v}{suffix}", begin=0.5)
    else:
        c.text(22, 110, big, "serifi", 46, fg, cls="up", delay=0.3, ls=-0.5)
    for i, ln in enumerate(wrap(body, "sans6", 13, 226)[:3]):
        c.text(24, 142 + i * 18, ln, "sans6", 13, fg, cls="up", delay=0.55 + i * 0.07)
    c.save(name)


def tiles(s):
    tile("build.svg", "BUILD", BLUE, "#ffffff", None,
         f"From AI compilers to genome ML. {s['live']} of them are live on the web.",
         f"BUILD: {s['repos']} public repos, {s['live']} live", value=s["repos"], suffix=" repos")
    tile("win.svg", "WIN", RED, "#ffffff", "1st place",
         "CODEISSANCE 2026, plus finals at IIT Hyderabad, SPIT Airavat and IIT Madras.",
         "WIN: 1st place at CODEISSANCE 2026, plus three hackathon finals", sheen_delay=0.4)
    tile("create.svg", "CREATE", YELLOW, INK, "TEDxCRCE",
         "Executive Producer. I run the stage, AV, cameras and livestream.",
         "CREATE: Executive Producer at TEDxCRCE", sheen_delay=0.8)


def title(name, plain, italic, dark):
    fg = "#f0f3f6" if dark else INK
    it = "#8fa2ff" if dark else BLUE
    c = Card(840, 78, plain + italic)
    c.text(8, 56, plain, "serif", 40, fg, cls="up", spans=[(italic, "serifi", it)])
    c.save(name)


REPOS = [
    ("repo-nexus360.svg", "Nexus360", BLUE,
     "Customer 360 for finance. A 7-stage pipeline merges one person's records across every system.",
     "Python  ·  1st place"),
    ("repo-synapse.svg", "SYNAPSE", RED,
     "A compiler for AI agent workflows that optimizes them from real production traces.",
     "Python  ·  newest"),
    ("repo-zenthera.svg", "Zenthera", YELLOW,
     "Predicts antibiotic resistance straight from a bacterial genome, at 92.4% accuracy.",
     "ML  ·  paper"),
    ("repo-flux.svg", "flux-forecast", BLUE,
     "Warns satellites about electron storms 30 to 45 minutes ahead. Built for ISRO.",
     "PyTorch  ·  ISRO"),
    ("repo-justicegrid.svg", "JusticeGrid", RED,
     "Finds undertrial prisoners who already qualify for bail, so lawyers see them first.",
     "Next.js  ·  finalist"),
    ("repo-ecosentinel.svg", "EcoSentinel", YELLOW,
     "Watches 8 coastal zones with live telemetry, forecasts and what-if risk runs.",
     "FastAPI  ·  live"),
]


def repo_card(i, fname, name, color, desc, foot):
    c = Card(280, 176, f"{name}: {desc}")
    c.paper()
    d = 0.1 + (i % 3) * 0.12
    c.add(f'<g class="up" style="animation-delay:{d:.2f}s">')
    c.add(f'<rect x="24" y="35" width="8" height="8" fill="{color}"/>')
    c.text(40, 44, name, "sans6", 17, INK)
    for j, ln in enumerate(wrap(desc, "sans", 13, 228)[:3]):
        c.text(24, 76 + j * 19, ln, "sans", 13, "#45443f")
    c.text(24, 150, foot, "mono", 11, FAINT)
    c.add("</g>")
    c.save(fname)


def main():
    s = stats(load_data())
    hero()
    heatmap(s)
    activity(s)
    tiles(s)
    title("title-light.svg", "What I'm ", "building", dark=False)
    title("title-dark.svg", "What I'm ", "building", dark=True)
    for i, r in enumerate(REPOS):
        repo_card(i, *r)
    print(f"drew cards: {s['total']} contributions, {s['repos']} repos, longest streak {s['longest']}")


if __name__ == "__main__":
    main()
