#!/usr/bin/env python3
"""
Playwright test suite for manavideosmedia.com
Run: python3 -m pytest tests/ -v
Requires: pip install playwright pytest && playwright install chromium
"""
import pytest
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8080"

@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()

@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    pg = ctx.new_page()
    yield pg
    ctx.close()

@pytest.fixture
def mobile_page(browser):
    ctx = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True)
    pg = ctx.new_page()
    yield pg
    ctx.close()

class TestPages:
    @pytest.mark.parametrize("path", ["", "stories.html", "archive.html",
                                       "channels.html", "about.html", "contact.html"])
    def test_page_loads(self, page, path):
        r = page.goto(f"{BASE}/{path}")
        assert r.status == 200
        assert len(page.content()) > 1000

    def test_navigation(self, page):
        page.goto(f"{BASE}/")
        for name in ["Stories", "Archive", "Channels", "About", "Contact"]:
            assert page.get_by_role("link", name=name).first.count() > 0

    def test_no_404(self, page):
        r = page.goto(f"{BASE}/does-not-exist-123.html")
        assert r.status == 404

class TestHomepage:
    def test_ticker_visible(self, page):
        page.goto(f"{BASE}/")
        assert page.locator("#news-ticker").is_visible()
        content = page.locator("#news-ticker .ticker-content").text_content()
        assert content and len(content.strip()) > 50

    def test_reels_present(self, page):
        page.goto(f"{BASE}/")
        assert page.locator(".reel-embed").count() == 3

    def test_no_js_errors(self, page):
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{BASE}/")
        page.wait_for_timeout(2000)
        assert len(errors) == 0, f"JS errors: {errors}"

class TestStories:
    def test_cards_have_alt(self, page):
        page.goto(f"{BASE}/stories.html")
        imgs = page.locator("article.card img").all()
        assert len(imgs) > 0
        for img in imgs[:10]:
            assert img.get_attribute("alt"), "Image missing alt text"

    def test_cards_lazy_load(self, page):
        page.goto(f"{BASE}/stories.html")
        imgs = page.locator("article.card img").all()
        for img in imgs[:10]:
            assert img.get_attribute("loading") == "lazy"

class TestSEO:
    def test_rss_valid(self, page):
        r = page.request.get(f"{BASE}/rss.xml")
        assert r.status == 200
        assert "<rss" in r.text()
        assert r.text().count("<item>") > 10

    def test_sitemap_valid(self, page):
        r = page.request.get(f"{BASE}/sitemap.xml")
        assert r.status == 200
        assert "<urlset" in r.text()

    def test_og_tags(self, page):
        page.goto(f"{BASE}/")
        html = page.content()
        assert 'property="og:title"' in html
        assert 'property="og:image"' in html

class TestMobile:
    def test_homepage(self, mobile_page):
        r = mobile_page.goto(f"{BASE}/")
        assert r.status == 200
        assert mobile_page.locator("#news-ticker").is_visible()

    def test_no_overflow(self, mobile_page):
        mobile_page.goto(f"{BASE}/")
        overflow = mobile_page.evaluate(
            "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        assert not overflow, "Horizontal overflow on mobile"

    def test_reels_stack(self, mobile_page):
        mobile_page.goto(f"{BASE}/")
        assert mobile_page.locator(".reel-embed").count() == 3
