#!/usr/bin/env python3
"""Build the story listings from stories.json.

    python3 tools/build_stories.py          # rewrite pages
    python3 tools/build_stories.py --check  # exit 1 if any page is out of date

Writes:
  index.html           BUILD regions: jsonld, nav, mobnav, home, footer-stories
  sitemap.xml          BUILD region: generated

index.html is the whole catalogue: the Latest Story, filter chips, every
category and sub (Coming Soon cards for empty ones) and On the Horizon. The
filter script in index.html shows/hides them from the URL hash
(#treks, #treks/western-ghats). adventures.html, treks.html and
mountaineering.html are hand-written redirect stubs into index.html.

A BUILD region is everything between
    <!-- BUILD:key ... -->   and   <!-- /BUILD:key -->
Only those regions are touched; the rest of each page stays hand-written.
Standard library only — there is deliberately no build step on the server.
"""
import json
import re
import sys
from datetime import date
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
THEMES = {"snow", "green", "sky", "kuari", "ember"}
SIZES = "auto, (max-width: 480px) 88vw, (max-width: 1023px) 88vw, 434px"
FEATURED_SIZES = "(max-width: 768px) 88vw, 55vw"


def e(s):
    return escape(str(s), quote=True)


# ── data ─────────────────────────────────────────────────────────────────────

def load():
    data = json.loads((ROOT / "stories.json").read_text(encoding="utf-8"))
    cats = {c["id"]: c for c in data["categories"]}
    errors = []
    for i, s in enumerate(data["stories"]):
        where = f"stories[{i}] ({s.get('href', '?')})"
        c = cats.get(s.get("category"))
        if not c:
            errors.append(f"{where}: unknown category {s.get('category')!r}")
        elif c.get("subs") and s.get("sub") not in {x["id"] for x in c["subs"]}:
            errors.append(f"{where}: unknown sub {s.get('sub')!r} for {c['id']}")
        if s.get("theme") not in THEMES:
            errors.append(f"{where}: theme must be one of {sorted(THEMES)}")
        if not re.fullmatch(r"\d{4}-\d{2}", s.get("date", "")):
            errors.append(f"{where}: date must be YYYY-MM")
        if not (ROOT / s["href"]).is_file():
            errors.append(f"{where}: page {s['href']} does not exist")
        img = s.get("image", {})
        paths = [img.get("src", "")] + [p.split()[0] for p in img.get("srcset", "").split(",") if p.strip()]
        for p in paths:
            if not (ROOT / p).is_file():
                errors.append(f"{where}: image {p} does not exist")
    if sum(1 for s in data["stories"] if s.get("latest")) > 1:
        errors.append('only one story may be marked "latest": true')
    if errors:
        sys.exit("stories.json has problems:\n  " + "\n  ".join(errors))

    # Newest first; ties keep file order (sort is stable). A story marked
    # "latest": true is pinned ahead of the rest whatever its date.
    data["stories"].sort(key=lambda s: (bool(s.get("latest")), s["date"]), reverse=True)
    for c in data["categories"]:
        c["stories"] = [s for s in data["stories"] if s["category"] == c["id"]]
        for sub in c.get("subs", []):
            sub["stories"] = [s for s in c["stories"] if s.get("sub") == sub["id"]]
    return data


def plural(n):
    return f"{n} {'Story' if n == 1 else 'Stories'}"


def month(d):
    y, m = d.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


# ── fragments ────────────────────────────────────────────────────────────────

def card(s, ind, featured=False):
    img = s["image"]
    fb = s["fallback"]
    attrs = []
    if img.get("srcset"):
        attrs.append(f'srcset="{e(img["srcset"])}" sizes="{FEATURED_SIZES if featured else SIZES}"')
    attrs.append(f'src="{e(img["src"])}" alt="{e(img["alt"])}"')
    # No markup inside the handler: the placeholder is drawn by CSS (site.css, .img-failed).
    attrs.append("onerror=\"this.parentElement.classList.add('img-failed');this.remove()\"")
    attrs.append('loading="eager" fetchpriority="high"' if featured else 'loading="lazy"')
    attrs.append('decoding="async"')
    if img.get("position"):
        attrs.append(f'style="object-position:{e(img["position"])};"')
    meta = [f"📅 {month(s['date'])}", f"🏔 {s['altitude']}"]
    if s.get("days"):
        meta.append(f"⏱ {s['days']} Days")
    meta.append(s["tag"])
    cls = f"card card-featured theme-{s['theme']}" if featured else f"card theme-{s['theme']}"
    desc = s.get("featured_desc", s["desc"]) if featured else s["desc"]
    status = "Latest" if featured else s["status"]
    i = ind
    return "\n".join([
        f'{i}<a href="{e(s["href"])}" class="{cls}">',
        f'{i}  <div class="card-img" data-emoji="{e(fb["emoji"])}" data-fallback="{e(fb["label"])}">',
        f'{i}    <img {" ".join(attrs)} />',
        f'{i}    <span class="badge">{e(s["badge"])}</span>',
        f'{i}  </div>',
        f'{i}  <div class="card-body">',
        f'{i}    <div class="card-meta">',
        *[f'{i}      <span class="meta-item">{e(m)}</span>' for m in meta],
        f'{i}    </div>',
        f'{i}    <h3 class="card-title">{e(s["title"])}</h3>',
        f'{i}    <p class="card-desc">{e(desc)}</p>',
        f'{i}    <div class="card-cta">',
        f'{i}      <span class="cta-link">Read Story <span class="arrow">→</span></span>',
        f'{i}      <span class="status-tag">{e(status)}</span>',
        f'{i}    </div>',
        f'{i}  </div>',
        f'{i}</a>',
    ])


def soon(text, ind):
    return "\n".join([
        f'{ind}<div class="card-upcoming">',
        f'{ind}  <span class="up-label">Coming Soon</span>',
        f'{ind}  <p class="up-title">{e(text["title"])}</p>',
        f'{ind}  <p class="up-note">{e(text["note"])}</p>',
        f'{ind}</div>',
    ])


def grid(stories, empty_text, ind):
    body = "\n\n".join(card(s, ind + "  ") for s in stories) if stories else soon(empty_text, ind + "  ")
    return f'{ind}<div class="grid">\n{body}\n{ind}</div>'


def sub_head(sub, ind):
    """Sub title, plus an optional link beside it (stories.json: sub.link)."""
    title = f'{ind}<h4 class="sub-title">{e(sub["label"])}</h4>'
    if not sub.get("link"):
        return [title]
    return [f'{ind}<div class="sub-head">', "  " + title,
            f'{ind}  <a class="sub-link" href="{e(sub["link"]["href"])}">{e(sub["link"]["label"])}</a>',
            f'{ind}</div>']


def category_section(c, ind):
    out = [
        f'{ind}<section class="cat" id="{c["id"]}" data-cat="{c["id"]}" data-label="{e(c["label"])}">',
        f'{ind}  <header class="cat-head">',
        f'{ind}    <h3 class="cat-title">{e(c["label"])}</h3>',
        f'{ind}    <p class="cat-desc">{e(c["desc"])}</p>',
        f'{ind}  </header>',
    ]
    if c.get("subs"):
        for sub in c["subs"]:
            out += [
                "",
                f'{ind}  <div class="sub" data-sub="{sub["id"]}" data-label="{e(sub["label"])}">',
                *sub_head(sub, ind + "    "),
                grid(sub["stories"], sub.get("soon", {"title": "More soon…", "note": ""}), ind + "    "),
                f'{ind}  </div>',
            ]
    else:
        out.append(grid(c["stories"], c.get("soon", {"title": "More soon…", "note": ""}), ind + "  "))
    out.append(f"{ind}</section>")
    return "\n".join(out)


def chips(data, current):
    """Top-level filter chips. The script in index.html intercepts data-filter
    and filters in place; the hrefs are the no-JS fallback."""
    ind = "        "
    total = len(data["stories"])
    out = [f'{ind}<a class="chip" href="#explore" data-filter="all" aria-current="{str(current == "all").lower()}">All <span class="n">{total}</span></a>']
    for c in data["categories"]:
        n = len(c["stories"])
        cls = "chip is-empty" if n == 0 else "chip"
        out.append(f'{ind}<a class="{cls}" href="#{c["id"]}" data-filter="{c["id"]}" aria-current="{str(current == c["id"]).lower()}">{e(c["label"])} <span class="n">{n}</span></a>')
    return "\n".join(out)


def jsonld(data, stories, name, url):
    items = [{"@type": "ListItem", "position": i + 1, "url": f"{data['site']}/{s['href']}", "name": s["name"]}
             for i, s in enumerate(stories)]
    doc = {"@context": "https://schema.org", "@type": "ItemList", "name": name, "url": url, "itemListElement": items}
    return '  <script type="application/ld+json">\n' + json.dumps(doc, ensure_ascii=False, indent=2).replace("</", "<\\/") \
        .replace("\n", "\n  ") + "\n  </script>"


# ── regions ──────────────────────────────────────────────────────────────────

def r_jsonld(data):
    return jsonld(data, data["stories"], "The Journeys", f"{data['site']}/")


def nav_cats(data):
    """Nav shows only categories that have stories; empty ones live under On the Horizon."""
    return [c for c in data["categories"] if c["stories"]]


def r_nav(data):
    ind = "    "
    out = [f'{ind}<li><a href="#explore" data-filter="all">Stories</a></li>']
    out += [f'{ind}<li><a href="#{x["id"]}" data-filter="{x["id"]}">{e(x["label"])}</a></li>' for x in nav_cats(data)]
    return "\n".join(out)


def r_mobnav(data):
    ind = "  "
    out = [f'{ind}<a href="#explore" data-filter="all" onclick="toggleMenu()">Stories</a>']
    out += [f'{ind}<a href="#{x["id"]}" data-filter="{x["id"]}" onclick="toggleMenu()">{e(x["label"])}</a>' for x in nav_cats(data)]
    return "\n".join(out)


def r_home(data):
    """The catalogue: header + count, filter chips, the Latest Story, every
    category/sub (Coming Soon cards where empty) and On the Horizon."""
    ind = "  "
    out = [
        f'{ind}<div class="treks-header">',
        f'{ind}  <div>',
        f'{ind}    <p class="treks-label">All Adventures</p>',
        f'{ind}    <h2 class="treks-title">The <em>Journeys</em></h2>',
        f'{ind}  </div>',
        f'{ind}  <span class="treks-count" id="storyCount">{plural(len(data["stories"]))}</span>',
        f'{ind}</div>',
        "",
        f'{ind}<nav class="filter-bar" aria-label="Filter adventures">',
        f'{ind}  <div class="chips" id="catChips">',
        chips(data, "all"),
        f'{ind}  </div>',
        f'{ind}  <div class="chips chips-sub" id="subChips" hidden></div>',
        f'{ind}</nav>',
    ]
    if data["stories"]:
        out += [
            "",
            f'{ind}<!-- Latest Story: the story marked "latest" in stories.json, else the newest by date. Not counted in totals. -->',
            f'{ind}<section class="featured" id="featured" aria-label="Latest story">',
            f'{ind}  <h3 class="sub-title">Latest Story</h3>',
            card(data["stories"][0], ind + "  ", featured=True),
            f'{ind}</section>',
        ]
    for c in data["categories"]:
        out += ["", category_section(c, ind)]
    upcoming = []
    for c in data["categories"]:
        if not c["stories"]:
            upcoming.append((c["id"], c["label"]))
        else:
            upcoming += [(f"{c['id']}/{s['id']}", s["label"]) for s in c.get("subs", []) if not s["stories"]]
    out += [
        "",
        f'{ind}<div class="horizon" id="horizon"{"" if upcoming else " hidden"}>',
        f'{ind}  <h3 class="sub-title">On the Horizon</h3>',
        f'{ind}  <div class="chips">',
        *[f'{ind}    <a class="chip" href="#{fl}" data-filter="{fl}">{e(l)}</a>' for fl, l in upcoming],
        f'{ind}  </div>',
        f'{ind}</div>',
    ]
    return "\n".join(out)


def r_footer(data, ind):
    return "\n".join([
        f'{ind}<div class="ft-col">',
        f'{ind}  <h4>Stories</h4>',
        f'{ind}  <ul>',
        *[f'{ind}    <li><a href="{e(s["href"])}">{e(s["name"])}</a></li>' for s in data["stories"]],
        f'{ind}    <li><a href="#explore" data-filter="all">All stories ↑</a></li>',
        f'{ind}  </ul>',
        f'{ind}</div>',
    ])


def r_sitemap(data):
    out = []
    pages = [(s["href"], "yearly", "0.80") for s in data["stories"]]
    for href, freq, prio in pages:
        mod = date.fromtimestamp((ROOT / href).stat().st_mtime).isoformat() if (ROOT / href).exists() else date.today().isoformat()
        out += ["  <url>", f"    <loc>{data['site']}/{href}</loc>", f"    <lastmod>{mod}</lastmod>",
                f"    <changefreq>{freq}</changefreq>", f"    <priority>{prio}</priority>", "  </url>"]
    return "\n".join(out)


# ── plumbing ─────────────────────────────────────────────────────────────────

def fill(text, key, body, fname):
    pat = re.compile(r"(<!-- BUILD:%s\b[^>]*-->\n)(.*?)([ \t]*<!-- /BUILD:%s -->)" % (re.escape(key), re.escape(key)), re.S)
    hits = pat.findall(text)
    if len(hits) != 1:
        sys.exit(f"{fname}: expected exactly one BUILD:{key} region, found {len(hits)}")
    return pat.sub(lambda m: m.group(1) + body + "\n" + m.group(3), text)


def build(data):
    idx = (ROOT / "index.html").read_text(encoding="utf-8")
    for key, body in (("jsonld", r_jsonld(data)), ("nav", r_nav(data)), ("mobnav", r_mobnav(data)),
                      ("home", r_home(data)), ("footer-stories", r_footer(data, "  "))):
        idx = fill(idx, key, body, "index.html")
    sm = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    return {"index.html": idx, "sitemap.xml": fill(sm, "generated", r_sitemap(data), "sitemap.xml")}


def main():
    check = "--check" in sys.argv
    data = load()
    stale = []
    for name, text in build(data).items():
        path = ROOT / name
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old == text:
            continue
        stale.append(name)
        if not check:
            path.write_text(text, encoding="utf-8")
    verb = "out of date" if check else "updated"
    print(f"{verb}: {', '.join(stale)}" if stale else "all pages up to date")
    sys.exit(1 if check and stale else 0)


if __name__ == "__main__":
    main()
