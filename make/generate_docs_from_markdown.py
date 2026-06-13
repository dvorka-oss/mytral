#!/usr/bin/env python3
"""
Generate MyTraL HTML documentation from Markdown sources.

This script reads Markdown files from docs/ directory and generates
styled HTML pages using Tabler CSS framework.
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import markdown


# Configuration
GITHUB_BASE_EDIT = "https://github.com/dvorka-oss/my-training-log/edit/main/docs/"
GITHUB_BASE_VIEW = "https://github.com/dvorka-oss/my-training-log/blob/main/docs/"
MINDFORGER_LINK = "https://www.mindforger.com"


@dataclass
class NavItem:
    """Navigation menu item."""
    title: str
    source: Optional[str] = None
    is_separator: bool = False
    children: list = field(default_factory=list)


@dataclass
class NavSection:
    """Top-level navigation section."""
    title: str
    source: Optional[str] = None
    items: list[NavItem] = field(default_factory=list)


def parse_sitemap(sitemap_path: Path) -> list[NavSection]:
    """
    Parse _SITEMAP.md to extract navigation structure.

    Format:
    - ## Section Title (top-level menu)
    - ### Item Title (submenu item)
    - * [source](filename.md) (source file for item)
    - ### --- (separator)

    Args:
        sitemap_path: Path to _SITEMAP.md

    Returns:
        List of NavSection objects
    """
    if not sitemap_path.exists():
        print(f"Warning: Sitemap not found: {sitemap_path}")
        return []

    with open(sitemap_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    sections = []
    current_section = None
    current_source = None

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # Parse ## Section Title
        match = re.match(r'^##\s+(.+)$', line)
        if match:
            section_title = match.group(1).strip()
            current_section = NavSection(title=section_title)
            sections.append(current_section)
            current_source = None
            i += 1
            continue

        # Parse ### Item Title or ### ---
        match = re.match(r'^###\s+(.+)$', line)
        if match and current_section:
            item_title = match.group(1).strip()

            # Check if separator
            if item_title == '---':
                current_section.items.append(NavItem(title='---', is_separator=True))
            else:
                current_section.items.append(NavItem(title=item_title))
            current_source = None
            i += 1
            continue

        # Parse * [source](filename.md)
        match = re.match(r'^\*\s*\[source\]\(([^)]+)\)', line)
        if match:
            source_file = match.group(1).strip()

            # Check if this is section-level source (after ##)
            if current_section and not current_section.items:
                current_section.source = source_file
            # Otherwise it's for the last item
            elif current_section and current_section.items:
                current_section.items[-1].source = source_file
            i += 1
            continue

        i += 1

    return sections


def md_filename_to_html(md_filename: str) -> str:
    """Convert Markdown filename to HTML filename."""
    return md_filename.replace('.md', '.html').lower()


def generate_navbar_html(sections: list[NavSection], active_page: str = "") -> str:
    """
    Generate navbar HTML from sitemap sections.

    Args:
        sections: List of NavSection objects
        active_page: Current page filename for highlighting

    Returns:
        Navbar HTML string
    """
    # Build dropdown menu items
    dropdowns = []

    for section in sections:
        # Build items for this section
        items_html = []
        for item in section.items:
            if item.is_separator:
                items_html.append('<div class="dropdown-divider"></div>')
            elif item.source:
                href = md_filename_to_html(item.source)
                active_class = " active" if active_page == href else ""
                items_html.append(
                    f'<a class="dropdown-item{active_class}" href="{href}">{item.title}</a>'
                )
            else:
                # Item without source - just text
                items_html.append(f'<a class="dropdown-item">{item.title}</a>')

        items_html_str = '\n'.join(items_html)

        # Determine icon based on section type
        if 'technical' in section.title.lower():
            icon_svg = '''<svg  xmlns="http://www.w3.org/2000/svg"  width="24"  height="24"  viewBox="0 0 24 24"  fill="none"  stroke="currentColor"  stroke-width="2"  stroke-linecap="round"  stroke-linejoin="round"  class="icon icon-tabler icons-tabler-outline icon-tabler-code"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M7 8l-4 4l4 4" /><path d="M17 8l4 4l-4 4" /><path d="M14 4l-4 16" /></svg>'''
        else:
            icon_svg = '''<svg  xmlns="http://www.w3.org/2000/svg"  width="24"  height="24"  viewBox="0 0 24 24"  fill="none"  stroke="currentColor"  stroke-width="2"  stroke-linecap="round"  stroke-linejoin="round"  class="icon icon-tabler icons-tabler-outline icon-tabler-book"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M3 19a9 9 0 0 1 9 0a9 9 0 0 1 9 0" /><path d="M3 6a9 9 0 0 1 9 0a9 9 0 0 1 9 0" /><path d="M3 6l0 13" /><path d="M12 6l0 13" /><path d="M21 6l0 13" /></svg>'''

        dropdown_html = f'''<li class="nav-item dropdown">
                        <a
                          class="nav-link dropdown-toggle"
                          href="#navbar-base"
                          data-bs-toggle="dropdown"
                          data-bs-auto-close="outside"
                          role="button"
                          aria-expanded="false"
                        >
                          <span class="nav-link-icon d-md-none d-lg-inline-block">
                            {icon_svg}
                          </span>
                          <span class="nav-link-title"> {section.title } </span>
                        </a>
                        <div class="dropdown-menu">
                          <div class="dropdown-menu-columns">
                            <div class="dropdown-menu-column">
                              {items_html_str}
                            </div>
                          </div>
                        </div>
                      </li>'''

        dropdowns.append(dropdown_html)

    dropdowns_str = '\n\n                      '.join(dropdowns)

    return f'''<div class="sticky-top">
        <header class="navbar navbar-expand-md sticky-top d-print-none">
          <div class="container-xl">
            <!-- BEGIN NAVBAR TOGGLER -->
            <button
              class="navbar-toggler"
              type="button"
              data-bs-toggle="collapse"
              data-bs-target="#navbar-menu"
              aria-controls="navbar-menu"
              aria-expanded="false"
              aria-label="Toggle navigation"
            >
              <span class="navbar-toggler-icon"></span>
            </button>
            <!-- END NAVBAR TOGGLER -->
            <!-- BEGIN NAVBAR LOGO -->
            <div class="navbar-brand navbar-brand-autodark d-none-navbar-horizontal pe-0 pe-md-3" style="gap: 0px;">
              <img src="/static/images/mytral-logo-transparent-bg.png" alt="MyTraL" style="width: 25px; height: 25px; margin-right: 5px;">
                MyTra<span style="color: #aaa;">ining</span>L<span style="color: #aaa;">og</span>
            </div>
            <!-- END NAVBAR LOGO -->
            <div class="navbar-nav flex-row order-md-last">
              <div class="d-none d-md-flex">

                <div class="nav-item">
                  <a href="?theme=dark" class="nav-link px-0 hide-theme-dark" title="Enable dark mode" data-bs-toggle="tooltip" data-bs-placement="bottom">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="24"
                      height="24"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      class="icon icon-1"
                    >
                      <path d="M12 3c.132 0 .263 0 .393 0a7.5 7.5 0 0 0 7.92 12.446a9 9 0 1 1 -8.313 -12.454z" />
                    </svg>
                  </a>
                  <a href="?theme=light" class="nav-link px-0 hide-theme-light" title="Enable light mode" data-bs-toggle="tooltip" data-bs-placement="bottom">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="24"
                      height="24"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      class="icon icon-1"
                    >
                      <path d="M12 12m-4 0a4 4 0 1 0 8 0a4 4 0 1 0 -8 0" />
                      <path d="M3 12h1m8 -9v1m8 8h1m-9 8v1m-6.4 -15.4l.7 .7m12.1 -.7l-.7 .7m0 11.4l.7 .7m-12.1 -.7l-.7 .7" />
                    </svg>
                  </a>
                </div>
              </div>
            </div>
          </div>
        </header>
        <header class="navbar-expand-md">
          <div class="collapse navbar-collapse" id="navbar-menu">
            <div class="navbar">
              <div class="container-xl">
                <div class="row flex-column flex-md-row flex-fill align-items-center">
                  <div class="col">
                    <!-- BEGIN NAVBAR MENU -->
                    <ul class="navbar-nav">
                      {dropdowns_str}
                    </ul>
                    <!-- END NAVBAR MENU -->
                  </div>
                  <div class="col col-md-auto">
                    <ul class="navbar-nav">
                      <li class="nav-item">
                        <a class="nav-link" href="/home">
                          <span class="nav-link-icon d-md-none d-lg-inline-block">
                            <svg
                              xmlns="http://www.w3.org/2000/svg"
                              width="24"
                              height="24"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              stroke-width="2"
                              stroke-linecap="round"
                              stroke-linejoin="round"
                              class="icon icon-1"
                            >
                              <path d="M5 12l-2 0l9 -9l9 9l-2 0" />
                              <path d="M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-7" />
                              <path d="M9 21v-6a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2v6" />
                            </svg>
                          </span>
                          <span class="nav-link-title"> MyTraL </span>
                        </a>
                      </li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </header>
      </div>'''


def extract_headings(html_content: str) -> list[tuple[int, str, str]]:
    """
    Extract headings from HTML for TOC generation.

    Args:
        html_content: HTML string

    Returns:
        List of (level, text, id) tuples
    """
    headings = []

    # Match h2, h3 tags including those with child elements (e.g. links)
    pattern = r'<h([23])([^>]*)>(.*?)</h\1>'
    matches = re.finditer(pattern, html_content)

    for match in matches:
        level = int(match.group(1))
        attrs = match.group(2)
        content = match.group(3).strip()

        # prefer id from tag attributes (set by markdown toc extension)
        id_match = re.search(r'id="([^"]+)"', attrs)
        if id_match:
            heading_id = id_match.group(1)
        else:
            # fallback: generate id from stripped text
            heading_id = re.sub(r'<[^>]+>', '', content)
            heading_id = heading_id.lower().replace(' ', '-').replace("'", "")
            heading_id = heading_id.replace('"', '')
            heading_id = re.sub(r'[^a-z0-9-]', '', heading_id)

        # strip HTML tags for TOC display text
        text = re.sub(r'<[^>]+>', '', content)

        headings.append((level, text, heading_id))

    return headings


def generate_toc_html(headings: list[tuple[int, str, str]]) -> str:
    """
    Generate TOC sidebar HTML from headings.

    Args:
        headings: List of (level, text, id) tuples

    Returns:
        HTML string for TOC sidebar
    """
    if not headings:
        return ""

    toc_items = []
    for level, text, heading_id in headings:
        indent_class = " ms-3" if level == 3 else ""
        toc_items.append(
            f'<a href="#{heading_id}" class="nav-link{indent_class}">{text}</a>'
        )

    toc_html = '\n'.join(toc_items)

    return f'''<div class="mt-6 py-6 sticky-top">
    <h3 class="mt-9">Table of Contents</h3>
    <div class="nav nav-vertical" id="toc">
        {toc_html}
    </div>
</div>'''


def get_html_template() -> str:
    """
    Get the base HTML template for documentation pages.

    Returns:
        HTML template string
    """
    return '''<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <meta http-equiv="X-UA-Compatible" content="ie=edge" />
    <title>{{TITLE}} - MyTraL Documentation</title>
    <meta name="msapplication-TileColor" content="#066fd1" />
    <meta name="theme-color" content="#066fd1" />
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="mobile-web-app-capable" content="yes" />
    <meta name="HandheldFriendly" content="True" />
    <meta name="MobileOptimized" content="320" />
    <link rel="icon" href="/static/favicon.ico" type="image/x-icon" />
    <link rel="shortcut icon" href="/static/favicon.ico" type="image/x-icon" />
    <meta
      name="description"
      content="Transform your training data into actionable insights. Track, analyze, and optimize your athletic performance with MyTraL."
    />

    <!-- BEGIN GLOBAL MANDATORY STYLES -->
    <link href="/static/tabler-dist/css/tabler.min.css" rel="stylesheet" />
    <!-- END GLOBAL MANDATORY STYLES -->
    <!-- BEGIN PLUGINS STYLES -->
    <link href="/static/tabler-dist/css/tabler-flags.min.css" rel="stylesheet"/>
    <link href="/static/tabler-dist/css/tabler-socials.min.css" rel="stylesheet"/>
    <link href="/static/tabler-dist/css/tabler-payments.min.css" rel="stylesheet"/>
    <link href="/static/tabler-dist/css/tabler-vendors.min.css" rel="stylesheet"/>
    <link href="/static/tabler-dist/css/tabler-marketing.min.css" rel="stylesheet"/>
    <link href="/static/tabler-dist/css/tabler-themes.min.css" rel="stylesheet"/>
    <!-- END PLUGINS STYLES -->
    <style>
      @import url("https://rsms.me/inter/inter.css");
      .carousel-inner img {
        height: 300px;
        object-fit: contain;
        background-color: #f8f9fa;
      }
    </style>

  </head>
  <body>
    <!-- BEGIN GLOBAL THEME SCRIPT -->
    <script src="/static/tabler-dist/js/tabler-theme.min.js"></script>
    <!-- END GLOBAL THEME SCRIPT -->
    <div class="page">
      <!-- BEGIN NAVBAR  -->
      {{NAVBAR}}
      <!-- END NAVBAR  -->
      <div class="page-wrapper">

      <!-- BEGIN MYTRAL PAGE CONTENT -->

        {{PAGE_HEADER}}

        <div class="page-body">
            <div class="container-xl">
                <div class="row">
                    <!-- BEGIN MAIN CONTENT -->
                    <div class="col-12 col-xxl-10">
                        {{CONTENT}}
                        </div></div>
                    </div>
                    <!-- END MAIN CONTENT -->

                    <!-- BEGIN TABLE OF CONTENTS SIDEBAR -->
                    <div class="col-2 d-none d-xxl-block">
                        {{TOC}}
                    </div>
                    <!-- END TABLE OF CONTENTS SIDEBAR -->
                </div>
            </div>
        </div>

        <!-- END MYTRAL PAGE CONTENT -->

        <!--  BEGIN FOOTER  -->
        {{FOOTER}}
        <!--  END FOOTER  -->
      </div>
    </div>
    <!-- BEGIN GLOBAL MANDATORY SCRIPTS -->
    <script src="/static/tabler-dist/js/tabler.min.js" defer></script>
    <!-- END GLOBAL MANDATORY SCRIPTS -->
</body>
</html>
'''


def get_page_header_html(pretitle: str, title: str) -> str:
    """
    Get the page header HTML component.

    Args:
        pretitle: Page pretitle (section name)
        title: Page title

    Returns:
        Page header HTML string
    """
    return f'''<div class="page-header d-print-none" aria-label="Page header">
            <div class="container-xl">
                <div class="row g-2 align-items-center">
                    <div class="col">
                        <div class="page-pretitle">{pretitle}</div>
                        <h2 class="page-title">{title}</h2>
                    </div>
                </div>
            </div>
        </div>'''


def get_footer_html(md_filename: str) -> str:
    """
    Get the footer HTML component with GitHub links.

    Args:
        md_filename: Markdown filename for GitHub links

    Returns:
        Footer HTML string
    """
    edit_url = f"{GITHUB_BASE_EDIT}{md_filename}"
    view_url = f"{GITHUB_BASE_VIEW}{md_filename}"

    return f'''<footer class="footer footer-transparent d-print-none">
          <div class="container-xl">
            <div class="row text-center align-items-center flex-row-reverse">
              <div class="col-lg-auto ms-lg-auto">
                <ul class="list-inline list-inline-dots mb-0">
                  <li class="list-inline-item"><a href="./license.html" class="link-secondary">License</a></li>
                  <li class="list-inline-item"><a href="{edit_url}" class="link-secondary" target="_blank">Edit on GitHub</a></li>
                  <li class="list-inline-item"><a href="{view_url}" class="link-secondary" target="_blank">Source</a></li>
                </ul>
              </div>
              <div class="col-12 col-lg-auto mt-3 mt-lg-0">
                <ul class="list-inline list-inline-dots mb-0">
                  <li class="list-inline-item">
                    Copyright &copy; 2026 MyTraL
                  </li>
                  <li class="list-inline-item">
                    Your personal training log for deeper insights and smarter progress.
                  </li>
                  <li class="list-inline-item">
                    Doc made with <a href="{MINDFORGER_LINK}" target="_blank">MindForger</a>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </footer>'''


def convert_md_to_html(md_path: Path, doc_dir: Path) -> tuple[str, str, str]:
    """
    Convert Markdown file to HTML content.

    Args:
        md_path: Path to Markdown file
        doc_dir: Documentation directory (for image paths)

    Returns:
        Tuple of (title, pretitle, html_content)
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract frontmatter (first line as title, second as pretitle if starts with >)
    lines = content.split('\n')
    title = lines[0].lstrip('#').strip() if lines else md_path.stem
    pretitle = ""
    content_start = 0

    if len(lines) > 1 and lines[1].startswith('>'):
        pretitle = lines[1].lstrip('>').strip()
        content_start = 2
    elif len(lines) > 2 and lines[2].startswith('---'):
        content_start = 3

    # Get markdown content
    md_content = '\n'.join(lines[content_start:])

    # Convert to HTML
    md = markdown.Markdown(extensions=['extra', 'toc', 'codehilite', 'meta'])
    html_content = md.convert(md_content)

    # Clean up: remove "Table of Contents" section if present (we generate our own)
    # Remove h2/h3 heading with "Table of Contents" and following paragraph
    html_content = re.sub(
        r'<h[23][^>]*>Table of Contents</h[23]>\s*<p>.*?</p>',
        '',
        html_content,
        flags=re.DOTALL | re.IGNORECASE
    )
    # Also remove any standalone "Table of Contents" text
    html_content = re.sub(
        r'<p>\s*Table of Contents\s+.*?</p>',
        '',
        html_content,
        flags=re.DOTALL | re.IGNORECASE
    )

    return title, pretitle, html_content


def get_pretitle_for_page(md_filename: str, sections: list[NavSection]) -> str:
    """
    Determine the pretitle for a page based on which section it belongs to.

    Args:
        md_filename: Markdown filename
        sections: Parsed sitemap sections

    Returns:
        Pretitle string
    """
    for section in sections:
        for item in section.items:
            if item.source == md_filename:
                return section.title

    return "MyTraL Documentation"


_PAGE_SECTION_PREFIX="""<div id="overview" class="card mb-3"><div class="card-body">"""
_PAGE_SECTION_SUFFIX="""</div></div>"""

def generate_html_page(
    md_path: Path,
    doc_dir: Path,
    output_dir: Path,
    sections: list[NavSection],
    dry_run: bool = False
) -> bool:
    """
    Generate HTML page from Markdown source.

    Args:
        md_path: Path to Markdown file
        doc_dir: Documentation source directory
        output_dir: Output directory for HTML
        sections: Parsed sitemap sections for navigation
        dry_run: If True, don't write file

    Returns:
        True if successful
    """
    print(f"Generating: {md_path.name}")

    # Convert Markdown to HTML
    title, pretitle, html_content = convert_md_to_html(md_path, doc_dir)

    # Get pretitle from sitemap if not set
    if not pretitle:
        pretitle = get_pretitle_for_page(md_path.name, sections)

    # Copy associated images (same prefix as .md file)
    doc_prefix = md_path.stem
    image_pattern = f"{doc_prefix}.*"
    images_copied = 0
    for img_path in doc_dir.glob(image_pattern):
        if img_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']:
            if not dry_run:
                import shutil
                shutil.copy2(img_path, output_dir / img_path.name)
            images_copied += 1

    # Extract headings for TOC
    headings = extract_headings(html_content)
    toc_html = generate_toc_html(headings)

    # Determine output filename
    html_filename = md_filename_to_html(md_path.name)

    # Special handling for INDEX.md
    if md_path.name == 'INDEX.md':
        pretitle = 'MyTraL Documentation'
        title = 'Manifesto'

    # Get template components - generate navbar dynamically
    navbar = generate_navbar_html(sections, html_filename)
    page_header = get_page_header_html(pretitle, title)
    footer = get_footer_html(md_path.name)

    # CONTENT preprocessing: heading garbage / Tabler cards / ...
    if html_content:
        html_content_lines = html_content.splitlines()

        if True and len(html_content_lines) > 10:
            html_content_lines = html_content_lines[1:]
            html_content_lines[0] = _PAGE_SECTION_PREFIX + html_content_lines[0]

            for e, l in enumerate(html_content_lines):
                # ensure card for every section
                if l and l.startswith('<h2') and "id=" in l:
                    prefix = _PAGE_SECTION_SUFFIX # if e > 0 else ""
                    html_content_lines[e] = (
                        prefix + _PAGE_SECTION_PREFIX + l
                    )

                # ensure TABLE styling
                if l and l.startswith('<table>'):
                    html_content_lines[e] = (
                        '<table class="table table-bordered field-table">'
                    )

        html_content = '\n'.join(html_content_lines)

    # Build full HTML
    template = get_html_template()
    full_html = template.replace('{{TITLE}}', title)
    full_html = full_html.replace('{{NAVBAR}}', navbar)
    full_html = full_html.replace('{{PAGE_HEADER}}', page_header)
    full_html = full_html.replace('{{CONTENT}}', html_content)
    full_html = full_html.replace('{{TOC}}', toc_html if toc_html else '<!-- No TOC -->')
    full_html = full_html.replace('{{FOOTER}}', footer)

    if dry_run:
        print(f"  Would write {html_filename} ({len(full_html)} chars)")
        if images_copied:
            print(f"  Would copy {images_copied} image(s)")
        return True

    # Write output
    output_path = output_dir / html_filename
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_html)

    print(f"  Written: {html_filename} ({len(full_html)} chars)")
    if images_copied:
        print(f"  Copied {images_copied} image(s)")
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate MyTraL HTML documentation from Markdown sources"
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("docs"),
        help="Source Markdown directory (default: docs)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("mytral/static/documentation"),
        help="Output directory for HTML files (default: mytral/static/documentation)",
    )
    parser.add_argument(
        "--sitemap",
        type=Path,
        default=Path("docs/_SITEMAP.md"),
        help="Sitemap file (default: docs/_SITEMAP.md)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write files, just show what would be done",
    )

    args = parser.parse_args()

    # Validate directories
    if not args.docs_dir.exists():
        print(f"Error: Source directory not found: {args.docs_dir}")
        sys.exit(1)

    # Create output directory if needed
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Parse sitemap for navigation
    print(f"Parsing sitemap: {args.sitemap}")
    sections = parse_sitemap(args.sitemap)
    print(f"  Found {len(sections)} section(s)")
    for section in sections:
        print(f"    - {section.title}: {len(section.items)} item(s)")
    print()

    # Find Markdown files to convert (exclude _SITEMAP.md and feature analysis docs)
    md_files = [
        f for f in args.docs_dir.glob("*.md")
        if not f.name.startswith('_') and 'FEATURE_ANALYSIS' not in f.name
    ]

    if not md_files:
        print(f"No Markdown files found to convert in {args.docs_dir}")
        sys.exit(0)

    print(f"Found {len(md_files)} Markdown file(s) to convert\n")

    # Convert each file
    success_count = 0
    for md_file in sorted(md_files):
        if generate_html_page(md_file, args.docs_dir, args.output_dir, sections, args.dry_run):
            success_count += 1

    print(f"\n{'='*60}")
    print(f"Generation complete: {success_count}/{len(md_files)} files")

    if args.dry_run:
        print("(Dry run - no files written)")
        print("\nTo generate files, run without --dry-run flag")


if __name__ == "__main__":
    main()
