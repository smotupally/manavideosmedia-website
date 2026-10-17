# Overnight Enhancements Plan — manavideosmedia.com
Date: 2026-10-17
Branch: `overnight/enhancements-2026-10-17`

## Codebase Overview
- Static HTML/CSS/vanilla JS site, no build step, deployed via Cloudflare Pages from GitHub
- 6 main pages: index, stories, archive, channels, about, contact (+ 69 article pages)
- styles.css: 622 lines, ~42KB
- Images: WebP in `images/` (~2MB total after overnight optimization)
- Ticker: JS-driven scroll via setInterval
- Reels: static 3-column grid (carousel removed per user request)

## Backlog (prioritized)

### 1. Bugs
- [ ] Check all internal links resolve (no 404s)
- [ ] Check all image `src` attributes resolve
- [ ] Verify no console errors on any page
- [ ] Verify ticker JS doesn't error when element missing

### 2. Responsive Design
- [ ] 375px (mobile): nav scroll, ticker, reels grid, cards
- [ ] 768px (tablet): verify layouts don't break
- [ ] 1280px (desktop): verify max-width containers
- [ ] Check `stories.html` card grid at all breakpoints

### 3. Accessibility (axe-core)
- [ ] All images have alt text
- [ ] Color contrast meets WCAG AA
- [ ] Focus states visible on links/buttons
- [ ] Semantic HTML (header/nav/main/footer)
- [ ] ARIA labels on icon-only buttons
- [ ] Keyboard navigation works

### 4. Performance
- [ ] All images lazy-load (loading="lazy" below fold)
- [ ] Remove unused CSS
- [ ] Preconnect/preload critical resources
- [ ] Check font loading strategy

### 5. SEO
- [ ] All pages have unique title + meta description
- [ ] Open Graph tags on all pages
- [ ] sitemap.xml complete and valid
- [ ] robots.txt correct
- [ ] Structured data (JSON-LD) on articles

### 6. CSS Cleanup
- [ ] Consolidate duplicate rules
- [ ] Use CSS variables consistently
- [ ] Consistent spacing scale

### 7. UX Polish
- [ ] Smooth scrolling for anchor links
- [ ] Hover/focus transitions
- [ ] Sticky nav on scroll
- [ ] Back-to-top button (already exists? verify)

### 8. Features
- [ ] Contact form validation (client-side)
- [ ] FAQ accordion (if FAQ content exists)
- [ ] Cookie banner (privacy compliance)
- [ ] Back-to-top button (if missing)

### 9. CI/CD
- [ ] Playwright test suite in `tests/`
- [ ] GitHub Actions workflow `.github/workflows/test.yml`

## Notes
- Never commit to main; all work on `overnight/enhancements-2026-10-17`
- One focused change per commit
- Test at 375px / 768px / 1280px after each change
- Every ~10 commits: run full test suite
