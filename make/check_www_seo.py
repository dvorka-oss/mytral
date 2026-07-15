#!/usr/bin/env python3
"""
Validate the built www.mytral.fitness site before deploying (make www-check).

Exits non-zero if any error is found, so it can gate a release. Checks:
  - every indexable HTML page has title, meta description, canonical, og:title,
    og:image and a viewport tag
  - no unresolved {{PLACEHOLDER}} template markers leaked into the output
  - every internal href/src resolves to a file that exists (dead-link detection),
    honouring the .htaccess clean-URL rule (/docs/x -> docs/x.html)
  - 404.html uses absolute asset paths (relative paths break at deep URLs)
  - sitemap.xml is well-formed and every <loc> maps to an existing file
  - robots.txt advertises the sitemap
  - og-image.png exists and is a landscape card (~1200x630)
  - favicon.ico exists
"""

import re
import sys
from pathlib import Path

import defusedxml.ElementTree as ElementTree
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
WWW = REPO_ROOT / "webs" / "www.mytral.fitness"
SITE_BASE = "https://mytral.fitness"

# required meta on every indexable page: label -> detection regex
REQUIRED_META = {
    "<title>": r"<title>[^<]+</title>",
    "meta description": r'<meta\s+name="description"\s+content="[^"]+"',
    "canonical": r'<link\s+rel="canonical"',
    "og:title": r'<meta\s+property="og:title"',
    "og:image": r'<meta\s+property="og:image"',
    "viewport": r'name="viewport"',
}

LINK_RE = re.compile(r'(?:href|src)="([^"]+)"', re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}")

errors: list[str] = []
warnings: list[str] = []


def has(html: str, pattern: str) -> bool:
    return re.search(pattern, html, re.IGNORECASE) is not None


def resolve_link(page: Path, url: str) -> Path | None:
    """Map an internal href/src to the file it should serve, or None to skip."""
    if url.startswith(("http://", "https://", "mailto:", "tel:", "#", "data:")):
        return None
    clean = url.split("#")[0].split("?")[0]
    if not clean:
        return None
    if clean.startswith("/"):
        target = WWW / clean.lstrip("/")
    else:
        target = (page.parent / clean).resolve()
    if clean.endswith("/"):
        target = target / "index.html"
    return target


def check_page(page: Path) -> None:
    html = page.read_text(encoding="utf-8")
    rel = page.relative_to(WWW)

    # noindex pages (e.g. 404) skip SEO meta but still get link/placeholder checks
    indexable = 'name="robots" content="noindex"' not in html
    if indexable:
        for label, pattern in REQUIRED_META.items():
            if not has(html, pattern):
                errors.append(f"{rel}: missing {label}")
        match = re.search(
            r'<meta\s+name="description"\s+content="([^"]*)"', html, re.IGNORECASE
        )
        if match and len(match.group(1)) > 160:
            warnings.append(
                f"{rel}: meta description {len(match.group(1))} chars (>160)"
            )

    for marker in sorted(set(PLACEHOLDER_RE.findall(html))):
        errors.append(f"{rel}: unresolved template placeholder {marker}")

    for url in sorted(set(LINK_RE.findall(html))):
        target = resolve_link(page, url)
        if target is None:
            continue
        # accept clean URLs served as .html by the .htaccess rewrite
        if not target.exists() and not target.with_suffix(".html").exists():
            errors.append(f"{rel}: dead link -> {url}")


def check_404() -> None:
    page = WWW / "404.html"
    if not page.exists():
        errors.append("404.html missing")
        return
    for bad in re.findall(r'(?:href|src)="(\.{1,2}/[^"]*)"', page.read_text()):
        errors.append(
            f"404.html: relative path '{bad}' breaks at deep URLs; use /absolute"
        )


def check_sitemap() -> None:
    sitemap = WWW / "sitemap.xml"
    if not sitemap.exists():
        errors.append("sitemap.xml missing")
        return
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [
        e.text.strip()
        for e in ElementTree.parse(sitemap).getroot().findall(".//s:loc", ns)
    ]
    if not locs:
        errors.append("sitemap.xml has no <loc> entries")
    for loc in locs:
        rel = loc.replace(SITE_BASE, "").lstrip("/")
        # a bare "/" or a trailing-slash URL is a directory served by index.html
        target = (
            WWW / rel / "index.html" if rel == "" or rel.endswith("/") else WWW / rel
        )
        if not target.exists():
            errors.append(f"sitemap.xml: {loc} -> missing {target.relative_to(WWW)}")


def check_assets() -> None:
    og_image = WWW / "og-image.png"
    if not og_image.exists():
        errors.append("og-image.png missing (run: make www-seo-assets)")
    else:
        width, height = Image.open(og_image).size
        if width <= height:
            errors.append(
                f"og-image.png is {width}x{height}; social cards need landscape"
            )
        elif not (1000 <= width <= 1300 and 500 <= height <= 700):
            warnings.append(f"og-image.png is {width}x{height}; recommended 1200x630")

    if not (WWW / "favicon.ico").exists():
        errors.append("favicon.ico missing (run: make www-seo-assets)")

    robots = WWW / "robots.txt"
    if not robots.exists() or "Sitemap:" not in robots.read_text():
        errors.append("robots.txt missing or has no Sitemap: directive")


def main() -> None:
    pages = sorted(WWW.glob("*.html")) + sorted((WWW / "docs").glob("*.html"))
    for page in pages:
        check_page(page)
    check_404()
    check_sitemap()
    check_assets()

    for message in warnings:
        print(f"WARN  {message}")
    for message in errors:
        print(f"ERROR {message}")
    print(
        f"\n{len(pages)} pages checked - {len(errors)} errors, {len(warnings)} warnings"
    )
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
