#!/usr/bin/env python3
"""
Mana Videos Media website sync — pulls new Instagram reels/posts into the website.
Runs via cron; does NOT touch the Instagram publishing schedule.

Reads new content from:
  ~/workspace/manavideos_reel/run_*/  (reel runs: caption.txt, SOURCES.md, publish_result.txt)
  ~/workspace/manavideos_post/*/      (static posts: caption.txt, *_1080x1350.png, sources.txt)

Generates article pages, updates stories.html + index.html + sitemap.xml,
pushes to GitHub (Cloudflare Pages auto-deploys).

State: ~/workspace/manavideosmedia-website/.sync_state.json
"""
import json, os, re, sys, shutil, subprocess, base64, io, html as htmlmod, fcntl
from datetime import datetime
from pathlib import Path
from PIL import Image

SITE = Path.home() / "workspace" / "manavideosmedia-website"
REEL_DIR = Path.home() / "workspace" / "manavideos_reel"
POST_DIR = Path.home() / "workspace" / "manavideos_post"
STATE_FILE = SITE / ".sync_state.json"
ARTICLES_DIR = SITE / "articles"
esc = lambda t: htmlmod.escape(str(t), quote=True)

# Category keywords for auto-classification
CATEGORY_RULES = [
    ("visa", ["visa", "h-1b", "h1b", "uscis", "perm", "green card", "immigration", "deport"]),
    ("politics", ["election", "senate", "congress", "vote", "midterm", "khanna", "jayapal", "bill", "trump", "biden"]),
    ("nri", ["flight", "nri", "diaspora", "india-us", "direct", "hyderabad", "chennai"]),
    ("community", []),  # default
]
CATEGORY_LABELS = {
    "visa": "Visa & Immigration",
    "politics": "Politics",
    "nri": "NRI Hub",
    "community": "Community News",
}
TE_SUBS = {
    "visa": "వీసా & ఇమ్మిగ్రేషన్ వార్తలు",
    "politics": "రాజకీయ వార్తలు",
    "nri": "ఎన్నారై వార్తలు",
    "community": "కమ్యూనిటీ వార్తలు",
}

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"synced_reels": [], "synced_posts": []}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def classify(text):
    t = text.lower()
    for cat, keywords in CATEGORY_RULES:
        if any(re.search(r'(?<![a-z0-9])' + re.escape(k) + r'(?![a-z0-9])', t) for k in keywords):
            return cat
    return "community"

def slugify(text):
    s = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return s[:60]

def parse_reel_caption(caption):
    """Extract story bullets from a reel caption. Returns (title_date, stories)."""
    lines = caption.strip().split('\n')
    # First line is like "Friday Evening, Oct 16 — USA Telugu News Roundup 🇺🇸📰"
    header = lines[0] if lines else "USA Telugu News Roundup"
    stories = []
    for line in lines[1:]:
        line = line.strip()
        if not line or line.startswith('@') or line.startswith('#'):
            continue
        # Story bullets start with emoji
        if len(line) > 10:
            # Strip leading emoji
            clean = re.sub(r'^[^\w]+', '', line).strip()
            if clean:
                stories.append(clean)
    return header, stories

def get_reel_url(run_dir):
    """Find the published Instagram reel URL."""
    pr = run_dir / "publish_result.txt"
    if pr.exists():
        text = pr.read_text()
        m = re.search(r'https://www\.instagram\.com/reel/[\w-]+/?', text)
        if m:
            return m.group(0)
    return None

def get_post_url(post_dir):
    pr = post_dir / "publish_result.txt"
    if pr.exists():
        text = pr.read_text()
        m = re.search(r'https://www\.instagram\.com/p/[\w-]+/?', text)
        if m:
            return m.group(0)
    # Try memory log or caption for URL
    return None


def crop_post_graphic(graphic_path):
    """
    Crop the photo section from a 1080x1350 post graphic.
    Returns base64 JPEG of the cropped image (photos + English labels, no Telugu text, watermark included).
    Pattern approved by user 2026-10-17: simple crop from the post, like the sample.
    """
    try:
        img = Image.open(graphic_path)
        w, h = img.size
        # Photo section is generally in the middle: crop y=35% to y=70%
        # This captures photos + English name labels, excludes header and Telugu text at bottom
        # Also excludes body text below the labels
        y1 = int(h * 0.35)
        y2 = int(h * 0.70)
        # Leave side margins
        x1 = int(w * 0.04)
        x2 = int(w * 0.96)
        cropped = img.crop((x1, y1, x2, y2))
        # Resize if too large
        if cropped.width > 900:
            ratio = 900 / cropped.width
            cropped = cropped.resize((900, int(cropped.height * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        cropped.save(buf, format='JPEG', quality=80, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"Crop failed for {graphic_path}: {e}")
        return None

def article_template(slug, headline, te_sub, date_str, read_min, category, body_paras, extra_html="", image_html=""):
    cat_label = CATEGORY_LABELS[category]
    import json as _js
    headline_json = _js.dumps(headline)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{headline} — Mana Videos Media</title>
  <meta name="description" content="{headline}">
  <link rel="canonical" href="https://manavideosmedia.com/articles/{slug}.html">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{headline}">
  <meta property="og:url" content="https://manavideosmedia.com/articles/{slug}.html">
  <meta property="og:site_name" content="Mana Videos Media">
  <meta property="og:image" content="https://manavideosmedia.com/og-image.png">
  <meta property="article:published_time" content="{date_str}">
  <script type="application/ld+json">
  {{"@context":"https://schema.org","@type":"NewsArticle","headline":{headline_json},"datePublished":"{date_str}","author":{{"@type":"Organization","name":"Mana Videos Media"}}}}
  </script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Telugu:wght@400;600;700;800&family=Noto+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../styles.css">
  <script defer src="https://cloud.umami.is/script.js" data-website-id="057a8fb0-a6cb-489c-868d-18291b14028d"></script>
</head>
<body>
<!-- AUTO-GENERATED by website sync. Source: Instagram @manavideos_media -->

<div class="topbar">
  <div class="container">
    <span class="date">{date_str}</span>
    <span class="social">
      <a href="https://www.instagram.com/manavideos_media" target="_blank" rel="noopener">Instagram</a>
      <a href="../contact.html">Contact</a>
    </span>
  </div>
</div>

<header class="brandbar">
  <div class="container">
    <div class="logo"><span class="brand-logo-img"></span>MANA VIDEOS <span class="gold">MEDIA</span></div>
    <div class="tagline">USA Telugu News, Every Morning &amp; Evening &nbsp;•&nbsp; <span class="te">అమెరికా తెలుగు వార్తలు</span></div>
  </div>
</header>

<nav class="mainnav" aria-label="Main navigation">
  <div class="container">
    <ul class="navlinks">
      <li><a href="../index.html">Home</a></li>
      <li><a href="../stories.html">Stories</a></li>
      <li><a href="../channels.html">Channels</a></li>
      <li><a href="../about.html">About</a></li>
      <li><a href="../contact.html">Contact</a></li>
    </ul>
  </div>
</nav>

<main>
  <article class="article-page">
    <div class="container">
      <a href="../stories.html" class="back-link">← Back to Stories</a>
      <span class="pill">{cat_label}</span>
      <h1>{headline}</h1>
      {image_html}
      <div class="te-sub">{te_sub}</div>
      <div class="meta"><span>{date_str}</span><span class="sep">•</span><span>{read_min} min read</span><span class="sep">•</span><span>By Mana Videos Media</span></div>
      <div class="article-body">
{body_paras}
{extra_html}
      </div>
      <div class="share">
        <div class="share-buttons">
          <span class="share-label">Share this story:</span>
          <a href="#" class="share-btn whatsapp" data-share="whatsapp" aria-label="Share on WhatsApp">WhatsApp</a>
          <a href="#" class="share-btn x" data-share="x" aria-label="Share on X">X</a>
          <a href="#" class="share-btn facebook" data-share="facebook" aria-label="Share on Facebook">Facebook</a>
          <button class="share-btn copy" data-share="copy" aria-label="Copy link">Copy Link</button>
        </div>
        <p>Follow <a href="https://www.instagram.com/manavideos_media" target="_blank" rel="noopener">@manavideos_media</a> on Instagram for daily Telugu news roundups.</p>
      </div>
      <p><a href="../stories.html">&larr; More stories</a></p>
    </div>
  </article>
</main>

<footer>
  <div class="container">
    <div class="foot-grid">
      <div class="foot-brand">
        <div class="logo">MANA VIDEOS <span class="gold">MEDIA</span></div>
        <p>Helping our people grow every day with the knowledge we give — genuine, honest day-to-day info for the Telugu diaspora.</p>
      </div>
      <div class="foot-links">
        <a href="../stories.html">Stories</a>
        <a href="../channels.html">Channels</a>
        <a href="../about.html">About</a>
        <a href="../contact.html">Contact</a>
      </div>
    </div>
    <div class="foot-bottom">&copy; 2026 Mana Videos Media. All rights reserved.</div>
  </div>
</footer>
<script>
(function () {{
  var buttons = document.querySelectorAll('.share-btn');
  var url = encodeURIComponent(window.location.href);
  var title = encodeURIComponent(document.title);
  buttons.forEach(function (btn) {{
    btn.addEventListener('click', function (e) {{
      e.preventDefault();
      var type = btn.getAttribute('data-share');
      if (type === 'whatsapp') {{
        window.open('https://wa.me/?text=' + title + '%20' + url, '_blank');
      }} else if (type === 'x') {{
        window.open('https://twitter.com/intent/tweet?text=' + title + '&url=' + url, '_blank');
      }} else if (type === 'facebook') {{
        window.open('https://www.facebook.com/sharer/sharer.php?u=' + url, '_blank');
      }} else if (type === 'copy') {{
        navigator.clipboard.writeText(window.location.href).then(function () {{
          btn.textContent = 'Copied!';
          setTimeout(function () {{ btn.textContent = 'Copy Link'; }}, 2000);
        }});
      }}
    }});
  }});
}})();
</script>
<script>
(function () {{
  var teDays = ['ఆదివారం','సోమవారం','మంగళవారం','బుధవారం','గురువారం','శుక్రవారం','శనివారం'];
  var now = new Date();
  var opts = {{ weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }};
  var dateStr = now.toLocaleDateString('en-US', opts) + ' | ' + teDays[now.getDay()];
  document.querySelectorAll('.topbar .date').forEach(function (el) {{
    el.textContent = dateStr;
  }});
}})();
</script>
</body>
</html>
"""

def sync_reels(state):
    """Find new reel runs and create roundup articles."""
    new_articles = []
    for run_dir in sorted(REEL_DIR.glob("run_*")):
        run_id = run_dir.name
        if run_id in state["synced_reels"]:
            continue
        caption_file = run_dir / "caption.txt"
        if not caption_file.exists():
            continue
        caption = caption_file.read_text()
        header, stories = parse_reel_caption(caption)
        if not stories:
            continue
        reel_url = get_reel_url(run_dir)
        # Date from run_id like run_20261016_pm
        m = re.search(r'run_(\d{4})(\d{2})(\d{2})_(am|pm)', run_id)
        if m:
            date_str = f"{m.group(2)}/{m.group(3)}/{m.group(1)}"
            slug_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        else:
            date_str = datetime.now().strftime("%m/%d/%Y")
            slug_date = datetime.now().strftime("%Y-%m-%d")
        ampm = "morning" if "_am" in run_id else "evening"
        slug = f"roundup-{slug_date}-{ampm}"
        headline = f"USA Telugu News Roundup — {date_str} ({ampm.title()})"
        te_sub = "అమెరికా తెలుగు న్యూస్ రౌండప్"

        # Body: intro + story list + reel embed
        paras = f"<p>{header}</p>\n"
        for s in stories:
            paras += f"<p><strong>•</strong> {esc(s)}</p>\n"
        extra = ""
        if reel_url:
            extra = f'<blockquote class="instagram-media" data-instgrm-permalink="{reel_url}" data-instgrm-version="14"></blockquote>\n<script async src="https://www.instagram.com/embed.js"></script>'

        html = article_template(slug, esc(headline), te_sub, date_str, 3, "community", paras, extra)
        (ARTICLES_DIR / f"{slug}.html").write_text(html)
        new_articles.append({
            "slug": slug, "headline": headline, "te_sub": te_sub,
            "date": date_str, "read_min": 3, "category": "community",
            "excerpt": esc(f"{len(stories)} stories: " + "; ".join(stories[:2]) + ("..." if len(stories) > 2 else "")),
        })
        state["synced_reels"].append(run_id)
        print(f"Reel article: {slug}")
    return new_articles

def sync_posts(state):
    """Find new static post runs and create articles."""
    new_articles = []
    for post_dir in sorted(POST_DIR.glob("20*")):
        post_id = post_dir.name
        if post_id in state["synced_posts"]:
            continue
        caption_file = post_dir / "caption.txt"
        if not caption_file.exists():
            continue
        caption = caption_file.read_text().strip()
        if not caption:
            continue
        # Headline = first line of caption
        headline = caption.split('\n')[0][:120]
        headline = re.sub(r'[^\w\s\-–—.,!?\'"()]', '', headline).strip()
        if not headline:
            continue
        slug = slugify(headline) or f"post-{post_id}"
        # Avoid overwriting an existing article with the same headline
        if (ARTICLES_DIR / f"{slug}.html").exists():
            slug = f"{slug}-{post_id}"
        category = classify(caption)
        te_sub = TE_SUBS[category]
        # Body from caption paragraphs
        paras = ""
        for p in caption.split('\n\n'):
            p = p.strip()
            if p and not p.startswith('#') and not p.startswith('@'):
                paras += f"<p>{p}</p>\n"
        # Find graphic
        graphic = None
        cropped_b64 = None
        image_html = ""
        for img in post_dir.glob("*1080x1350.png"):
            # Crop the photo section (simple crop, no Telugu text, watermark included)
            # Pattern: user-approved 2026-10-17 — same image in card and article
            cropped_b64 = crop_post_graphic(img)
            if cropped_b64:
                image_html = f'<div class="article-image"><img src="data:image/jpeg;base64,{cropped_b64}" alt="{headline[:50]}" style="width:100%;height:auto;border-radius:8px"></div>'
            else:
                image_html = ""
            break
        else:
            image_html = ""
        post_url = get_post_url(post_dir)
        extra = ""
        if post_url:
            extra += f'\n<p><a href="{post_url}" target="_blank" rel="noopener">View on Instagram</a></p>'

        html = article_template(slug, esc(headline), te_sub, post_id, 2, category, paras, extra, image_html)
        (ARTICLES_DIR / f"{slug}.html").write_text(html)
        # Store cropped image for card thumbnail (same image in card and article)
        thumb_b64 = ""
        if cropped_b64:
            try:
                thumb_img = Image.open(io.BytesIO(base64.b64decode(cropped_b64)))
                thumb_img.thumbnail((250, 140))
                tbuf = io.BytesIO()
                thumb_img.save(tbuf, format='JPEG', quality=50, optimize=True)
                thumb_b64 = base64.b64encode(tbuf.getvalue()).decode()
            except:
                pass
        new_articles.append({
            "slug": slug, "headline": headline, "te_sub": te_sub,
            "date": post_id, "read_min": 2, "category": category,
            "excerpt": esc(caption.split('\n')[1][:150]) if '\n' in caption else esc(headline[:100]),
            "thumb_b64": thumb_b64,
        })
        state["synced_posts"].append(post_id)
        print(f"Post article: {slug}")
    return new_articles

def update_ticker():
    """Update ticker headlines on all main pages with latest 8 article headlines."""
    import glob, re
    # Get latest 8 articles by reading stories.html cards
    sp = SITE / "stories.html"
    html = sp.read_text()
    # Extract headlines from cards (first 8)
    headlines = re.findall(r'<h3><a[^>]*>([^<]+)</a></h3>', html)[:8]
    if not headlines:
        return
    # Build ticker content (duplicated for seamless loop)
    ticker_text = " • ".join(headlines)
    ticker_html = f"{ticker_text} &nbsp;•&nbsp; {ticker_text}"
    
    for page in ["index.html", "stories.html", "archive.html", "channels.html", "about.html", "contact.html"]:
        pp = SITE / page
        if not pp.exists():
            continue
        phtml = pp.read_text()
        # Replace ticker content
        new_phtml = re.sub(
            r'(<div class="ticker-content">).*?(</div>)',
            lambda m: m.group(1) + ticker_html + m.group(2),
            phtml,
            count=1,
            flags=re.DOTALL
        )
        if new_phtml != phtml:
            pp.write_text(new_phtml)
    print(f"Updated ticker with {len(headlines)} headlines")


def update_reels():
    """Update homepage Latest Reels with 3 most recent published reels."""
    import re
    reels = []
    for run_dir in REEL_DIR.glob("run_*"):
        url = get_reel_url(run_dir)
        if not url:
            continue
        # Extract date from run_id like run_20261017_am
        m = re.search(r'run_(\d{8})_(am|pm)', run_dir.name)
        if m:
            date_key = m.group(1) + ("1" if m.group(2) == "am" else "2")
            reels.append((date_key, url))
    # Sort newest first, take 3
    reels.sort(reverse=True)
    latest = [url for _, url in reels[:3]]
    if len(latest) < 3:
        return
    # Update index.html
    ip = SITE / "index.html"
    html = ip.read_text()
    # Build new reels HTML
    reels_html = ""
    for url in latest:
        # Ensure trailing slash
        if not url.endswith("/"):
            url += "/"
        reels_html += f"""          <div class="reel-embed">
            <blockquote class="instagram-media" data-instgrm-permalink="{url}" data-instgrm-version="14"></blockquote>
          </div>
"""
    # Replace the reels-static content
    new_html = re.sub(
        r'(<div class="reels-static">\n).*?(\n        </div>)',
        lambda m: m.group(1) + reels_html.rstrip("\n") + m.group(2),
        html,
        count=1,
        flags=re.DOTALL
    )
    if new_html != html:
        ip.write_text(new_html)
        print(f"Updated homepage reels: {len(latest)} latest")


def update_homepage_stories():
    """Update homepage Latest Stories with 6 most recent articles."""
    import re
    sp = SITE / "stories.html"
    html = sp.read_text()
    # Extract first 6 cards from stories.html
    cards = re.findall(r'<article class="card"[^>]*>.*?</article>', html, re.DOTALL)[:6]
    if len(cards) < 6:
        return
    # Update index.html - replace cards in Latest Stories grid
    ip = SITE / "index.html"
    ihtml = ip.read_text()
    # Find the Latest Stories grid (the one after <h2>Latest Stories</h2>)
    # Pattern: <h2>Latest Stories</h2> ... <div class="grid"> ... </div>
    pattern = r'(<h2>Latest Stories</h2>.*?<div class="grid">\n)(.*?)(\n        </div>)'
    m = re.search(pattern, ihtml, re.DOTALL)
    if not m:
        return
    new_cards = "\n".join(["        " + c for c in cards])
    new_ihtml = ihtml[:m.start(2)] + new_cards + ihtml[m.end(2):]
    if new_ihtml != ihtml:
        ip.write_text(new_ihtml)
        print(f"Updated homepage Latest Stories: {len(cards)} articles")


def update_listings(new_articles):
    """Prepend new cards to stories.html and update sitemap."""
    if not new_articles:
        return
    # Update stories.html — insert after <div class="grid" id="story-grid">
    sp = SITE / "stories.html"
    html = sp.read_text()
    cards = ""
    for a in new_articles:
        # Skip if this article card already exists (retry safety)
        if f"articles/{a['slug']}.html" in html:
            continue
        cat_label = CATEGORY_LABELS[a["category"]]
        # Same image in card and article (user requirement 2026-10-17)
        thumb_html = f'<img src="data:image/jpeg;base64,{a["thumb_b64"]}" alt="" style="width:100%;height:100%;object-fit:cover">' if a.get("thumb_b64") else cat_label.upper()
        cards += f"""        <article class="card" data-category="{a['category']}">
          <div class="thumb">{thumb_html}</div>
          <div class="body">
            <span class="pill">{cat_label}</span>
            <h3><a href="articles/{a['slug']}.html">{esc(a['headline'])}</a></h3>
            <div class="te-sub">{a['te_sub']}</div>
            <p class="excerpt">{esc(a['excerpt'])}</p>
            <div class="meta"><span>{a['date']}</span><span>{a['read_min']} min read</span></div>
          </div>
        </article>
"""
    html = html.replace('<div class="grid" id="story-grid">',
                        '<div class="grid" id="story-grid">\n' + cards, 1)
    sp.write_text(html)

    # Update sitemap.xml
    smp = SITE / "sitemap.xml"
    sm = smp.read_text()
    today = datetime.now().strftime("%Y-%m-%d")
    urls = ""
    for a in new_articles:
        urls += f"""  <url>
    <loc>https://manavideosmedia.com/articles/{a['slug']}.html</loc>
    <lastmod>{today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
"""
    sm = sm.replace('</urlset>', urls + '</urlset>')
    smp.write_text(sm)
    print(f"Updated listings with {len(new_articles)} new articles")
    update_ticker()
    update_reels()
    update_homepage_stories()


def rebuild_rss():
    """Rebuild rss.xml from all articles in the articles folder."""
    import glob as globmod
    from xml.sax.saxutils import escape as xesc
    items = []
    for fp in sorted((ARTICLES_DIR).glob("*.html"), reverse=True):
        content = fp.read_text()
        h = re.search(r'<h1>([^<]+)</h1>', content)
        if not h:
            continue
        title = re.sub(r'<[^>]+>', '', h.group(1))
        # Try YYYY-MM-DD first, then MM/DD/YYYY
        date_str = None
        m = re.search(r'<span>(2026-[0-9-]+)</span>', content)
        if m:
            date_str = m.group(1)
        else:
            m2 = re.search(r'<span>([0-9]{2})/([0-9]{2})/(2026)</span>', content)
            if m2:
                date_str = f"{m2.group(3)}-{m2.group(1)}-{m2.group(2)}"
        if not date_str:
            continue
        try:
            from datetime import datetime as dt
            pubdate = dt.strptime(date_str, '%Y-%m-%d').strftime('%a, %d %b %Y 00:00:00 +0000')
        except:
            pubdate = date_str
        items.append((date_str, title, fp.stem))
    items.sort(reverse=True)
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>Mana Videos Media</title>
  <link>https://manavideosmedia.com/</link>
  <description>USA Telugu News, Every Morning &amp; Evening</description>
  <language>en</language>
  <atom:link href="https://manavideosmedia.com/rss.xml" rel="self" type="application/rss+xml" />
"""
    for date_str, title, stem in items[:50]:
        try:
            from datetime import datetime as dt
            pubdate = dt.strptime(date_str, '%Y-%m-%d').strftime('%a, %d %b %Y 00:00:00 +0000')
        except:
            pubdate = date_str
        rss += f"""  <item>
    <title>{xesc(title)}</title>
    <link>https://manavideosmedia.com/articles/{stem}.html</link>
    <guid isPermaLink="true">https://manavideosmedia.com/articles/{stem}.html</guid>
    <pubDate>{pubdate}</pubDate>
  </item>
"""
    rss += "</channel>\n</rss>\n"
    (SITE / "rss.xml").write_text(rss)
    print(f"RSS rebuilt: {len(items)} articles")

def push_to_github(new_articles=None):
    """Push only changed files to GitHub."""
    files = []
    if new_articles:
        for a in new_articles:
            fp = ARTICLES_DIR / f"{a['slug']}.html"
            if fp.exists():
                files.append({"path": f"articles/{fp.name}", "content": fp.read_text()})
    for f in ["stories.html", "sitemap.xml", "rss.xml"]:
        fp = SITE / f
        if fp.exists():
            files.append({"path": f, "content": fp.read_text()})

    # Separate text and binary
    text_files = [f for f in files if not f.get("_binary")]
    # NOTE (2026-10-17): `github call-tool --arguments-json` passes the whole
    # payload as one argv string; on this VM the stack limit (ulimit -s 8192)
    # makes ARG_MAX tiny, so full-page payloads die with "Argument list too
    # long". `github push-files` reads file contents through privsep instead.
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".paths", delete=False) as pf:
        pf.write("\0".join(f["path"] for f in text_files) + "\0")
        paths_file = pf.name
    result = subprocess.run(
        ["/opt/hatch/bin/github", "push-files",
         "--owner", "smotupally", "--repo", "manavideosmedia-website",
         "--branch", "main",
         "--message", f"Website sync: {len(text_files)} new articles",
         "--source-dir", str(SITE),
         "--paths-file", paths_file],
        capture_output=True, text=True, timeout=600)
    print("Push result:", result.stdout[:200])
    if result.returncode != 0:
        print("Push stderr:", result.stderr[:500])
    return result.returncode == 0

def main():
    # Prevent overlapping cron runs
    lock_file = open(SITE / ".sync.lock", "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("SYNC: another run in progress, exiting")
        return
    ARTICLES_DIR.mkdir(exist_ok=True)
    state = load_state()
    new = []
    new += sync_reels(state)
    new += sync_posts(state)
    if new:
        update_listings(new)
        rebuild_rss()
        # Push from the site dir (sync.py writes directly to SITE)
        if push_to_github(new):
            save_state(state)
            print(f"SYNC COMPLETE: {len(new)} new articles")
        else:
            print("SYNC: push failed, state NOT saved (will retry next run)")
    else:
        print("SYNC: nothing new")

if __name__ == "__main__":
    main()
