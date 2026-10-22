#!/usr/bin/env python3
"""
End-to-End QA Test Suite for manavideosmedia.com
Tests: HTML validity, CSS syntax, mobile responsiveness, content sync, links, images
Usage: python3 qa_test.py [--live] [--verbose]
"""
import re
import os
import sys
from pathlib import Path
from html.parser import HTMLParser

SITE = Path(__file__).parent
VERBOSE = "--verbose" in sys.argv
LIVE = "--live" in sys.argv

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def ok(self, name):
        self.passed += 1
        if VERBOSE: print(f"  ✓ {name}")
    
    def fail(self, name, detail=""):
        self.failed += 1
        self.errors.append(f"{name}: {detail}")
        print(f"  ✗ {name}")
        if detail: print(f"    → {detail}")

result = TestResult()

class TagValidator(HTMLParser):
    """Validates HTML tag balance"""
    VOID = {'br','hr','img','input','meta','link','area','base','col','embed','source','track','wbr'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []
    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append((tag, self.getpos()))
    def handle_endtag(self, tag):
        if tag in self.VOID: return
        if not self.stack:
            self.errors.append(f"Closing </{tag}> with no open tag at {self.getpos()}")
            return
        # Find matching open tag
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                # Pop everything up to and including match
                unclosed = self.stack[i+1:]
                for t, pos in unclosed:
                    self.errors.append(f"Unclosed <{t}> opened at {pos}, closed by </{tag}> at {self.getpos()}")
                self.stack = self.stack[:i]
                return
        self.errors.append(f"Closing </{tag}> with no matching open at {self.getpos()}")

def test_html_validity():
    """Test 1: All HTML files have balanced tags"""
    print("\n[1] HTML Tag Balance")
    files = list(SITE.glob("*.html")) + list((SITE/"articles").glob("*.html"))
    for f in files:
        v = TagValidator()
        try:
            v.feed(f.read_text())
            # Check for unclosed tags remaining
            for tag, pos in v.stack:
                # Ignore html/body which might be closed implicitly
                if tag not in ('html', 'body'):
                    v.errors.append(f"Unclosed <{tag}> opened at {pos}")
            if v.errors:
                result.fail(f.name, "; ".join(v.errors[:3]))
            else:
                result.ok(f.name)
        except Exception as e:
            result.fail(f.name, str(e))

def test_css_syntax():
    """Test 2: All <style> blocks have balanced braces"""
    print("\n[2] CSS Brace Balance in <style> blocks")
    files = list(SITE.glob("*.html")) + list((SITE/"articles").glob("*.html"))
    for f in files:
        html = f.read_text()
        blocks = re.findall(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)
        bad = []
        for i, css in enumerate(blocks):
            # Remove comments
            css_clean = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
            opens = css_clean.count('{')
            closes = css_clean.count('}')
            if opens != closes:
                bad.append(f"block {i}: {opens} open vs {closes} close")
        if bad:
            result.fail(f.name, "; ".join(bad))
        elif blocks:
            result.ok(f"{f.name} ({len(blocks)} blocks)")

def test_content_sync():
    """Test 3: All articles in sync across disk/stories/archive"""
    print("\n[3] Content Sync (disk ↔ stories.html ↔ archive.html)")
    articles = set(f.name for f in (SITE/"articles").glob("*.html"))
    
    stories_html = (SITE/"stories.html").read_text()
    story_links = set(re.findall(r'articles/([a-z0-9\-\.]+\.html)', stories_html))
    
    archive_html = (SITE/"archive.html").read_text()
    archive_links = set(re.findall(r'articles/([a-z0-9\-\.]+\.html)', archive_html))
    
    if articles == story_links:
        result.ok(f"stories.html: {len(articles)} articles")
    else:
        missing = articles - story_links
        extra = story_links - articles
        result.fail("stories.html sync", f"missing={len(missing)}, broken={len(extra)}")
    
    if articles == archive_links:
        result.ok(f"archive.html: {len(articles)} articles")
    else:
        missing = articles - archive_links
        result.fail("archive.html sync", f"missing={len(missing)}: {sorted(missing)[:3]}")

def test_homepage_latest():
    """Test 4: Homepage Latest Stories matches stories.html order"""
    print("\n[4] Homepage Latest Stories")
    stories_html = (SITE/"stories.html").read_text()
    story_order = []
    for m in re.finditer(r'articles/([a-z0-9\-\.]+\.html)', stories_html):
        if m.group(1) not in story_order:
            story_order.append(m.group(1))
    
    index_html = (SITE/"index.html").read_text()
    # Find Latest Stories section
    ls_start = index_html.find("Latest Stories")
    if ls_start < 0:
        result.fail("Homepage", "Latest Stories section not found")
        return
    ls_section = index_html[ls_start:ls_start+8000]
    homepage_links = re.findall(r'articles/([a-z0-9\-\.]+\.html)', ls_section)
    
    # Top 3 from stories should be in homepage Latest Stories
    for slug in story_order[:3]:
        if slug in homepage_links:
            result.ok(f"Homepage has {slug[:40]}")
        else:
            result.fail("Homepage Latest Stories", f"missing {slug}")

def test_no_broken_thumbnails():
    """Test 5: No broken image URLs in card thumbnails"""
    print("\n[5] Card Thumbnails (no broken images)")
    for page in ["index.html", "stories.html"]:
        html = (SITE/page).read_text()
        # Find img tags in thumbs pointing to non-existent URLs
        imgs = re.findall(r'<div class="thumb"><img src="([^"]+)"', html)
        broken = [u for u in imgs if 'og-image.png' in u or u.startswith('http') and 'manavideosmedia.com' in u]
        if broken:
            result.fail(page, f"{len(broken)} broken thumbnail URLs")
        else:
            result.ok(f"{page}: no broken thumbnails ({len(imgs)} imgs)")

def test_mobile_css():
    """Test 6: Mobile responsive CSS present and valid"""
    print("\n[6] Mobile Responsive CSS")
    # Check article reel sidebar mobile fix
    sample = (SITE/"articles"/"roundup-2026-10-19-morning.html").read_text()
    if '@media (max-width: 768px)' in sample and 'article-with-reel' in sample:
        result.ok("Article reel sidebar has mobile CSS")
    else:
        result.fail("Article mobile CSS", "missing @media for article-with-reel")
    
    # Check nav dropdown mobile fix (2026-10-22 mechanism: the tap script in the
    # page toggles .mobile-open; styles.css carries the @media .mobile-open overlay
    # rule; the old always-visible in-flow block must be gone from the page)
    index_html = (SITE/"index.html").read_text()
    styles_css = (SITE/"styles.css").read_text()
    if ('.dropdown.mobile-open' in styles_css and 'mobile-open' in index_html
            and 'position: static !important' not in index_html):
        result.ok("Nav dropdown has mobile CSS")
    else:
        result.fail("Nav mobile CSS", "mobile-open rule/script missing, or old static block still present")

def test_reel_embeds():
    """Test 7: Roundup articles have Instagram reel embeds"""
    print("\n[7] Reel Embeds in Roundup Articles")
    roundups = [f for f in (SITE/"articles").glob("roundup-*.html")]
    checked = 0
    for f in roundups[-5:]:  # Check 5 most recent
        html = f.read_text()
        has_embed = 'instagram-media' in html or 'instgrm' in html
        has_url = 'instagram.com/reel/' in html
        if has_embed and has_url:
            result.ok(f.name[:50])
        else:
            result.fail(f.name[:50], f"embed={has_embed}, url={has_url}")
        checked += 1

def test_no_duplicate_articles():
    """Test 8: No duplicate article content"""
    print("\n[8] No Duplicate Articles")
    seen_titles = {}
    dups = []
    for f in (SITE/"articles").glob("*.html"):
        html = f.read_text()
        m = re.search(r'<title>([^<]+)</title>', html)
        title = m.group(1).split('|')[0].strip() if m else f.name
        if title in seen_titles:
            dups.append(f"{f.name} dup of {seen_titles[title]}")
        else:
            seen_titles[title] = f.name
    if dups:
        result.fail("Duplicates", "; ".join(dups[:3]))
    else:
        result.ok(f"No duplicates in {len(seen_titles)} articles")

def main():
    print("=" * 60)
    print("MANAVIDEOSMEDIA.COM — END-TO-END QA TEST SUITE")
    print("=" * 60)
    
    test_html_validity()
    test_css_syntax()
    test_content_sync()
    test_homepage_latest()
    test_no_broken_thumbnails()
    test_mobile_css()
    test_reel_embeds()
    test_no_duplicate_articles()
    
    print("\n" + "=" * 60)
    print(f"RESULTS: {result.passed} passed, {result.failed} failed")
    print("=" * 60)
    if result.failed:
        print("\nFAILURES:")
        for e in result.errors:
            print(f"  • {e}")
        sys.exit(1)
    else:
        print("\nALL TESTS PASSED ✓")

if __name__ == "__main__":
    main()
