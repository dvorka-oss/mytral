#!/usr/bin/env python3
"""
Generate public HTML documentation from Markdown sources.

This script reads Markdown files from docs/ directory and generates
modern styled HTML pages with dark theme for webs/www.mytral.fitness/docs/.
Features left sidebar navigation and right sidebar table of contents.
"""

import argparse
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import markdown


# Configuration
GITHUB_BASE_EDIT = "https://github.com/dvorka/my-training-log/edit/main/docs/"
GITHUB_BASE_VIEW = "https://github.com/dvorka/my-training-log/blob/main/docs/"
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


def generate_sidebar_nav_html(sections: list[NavSection], active_page: str = "") -> str:
    """
    Generate left sidebar navigation HTML from sitemap sections.

    Args:
        sections: List of NavSection objects
        active_page: Current page filename for highlighting

    Returns:
        Sidebar navigation HTML string
    """
    nav_items = []

    for section in sections:
        # Add section header
        nav_items.append(f'<div class="nav-section-title">{section.title}</div>')

        # Add section items
        for item in section.items:
            if item.is_separator:
                nav_items.append('<div class="nav-divider"></div>')
            elif item.source:
                href = md_filename_to_html(item.source)
                active_class = " active" if active_page == href else ""
                nav_items.append(
                    f'<a href="{href}" class="nav-item{active_class}">{item.title}</a>'
                )

    nav_html = '\n'.join(nav_items)

    return f'''<nav class="docs-nav">
        <div class="nav-brand">
            <img src="../mytral-logo.png" alt="MyTraL" class="nav-logo">
            <span class="nav-brand-text">MyTraL Docs</span>
        </div>
        <div class="nav-items">
            {nav_html}
        </div>
    </nav>'''


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
        return '<div class="docs-toc"></div>'

    toc_items = []
    for level, text, heading_id in headings:
        indent_class = " toc-h3" if level == 3 else " toc-h2"
        toc_items.append(
            f'<a href="#{heading_id}" class="toc-item{indent_class}">{text}</a>'
        )

    toc_html = '\n'.join(toc_items)

    return f'''<div class="docs-toc">
        <div class="toc-title">On This Page</div>
        {toc_html}
    </div>'''


def add_heading_ids(html_content: str) -> str:
    """
    Add id attributes to headings for anchor links.

    Args:
        html_content: HTML string

    Returns:
        HTML with heading IDs added
    """
    def replace_heading(match):
        level = match.group(1)
        content = match.group(2).strip()
        # strip HTML tags for id generation
        text = re.sub(r'<[^>]+>', '', content)
        heading_id = text.lower().replace(' ', '-').replace("'", "").replace('"', '')
        heading_id = re.sub(r'[^a-z0-9-]', '', heading_id)
        return f'<h{level} id="{heading_id}">{content}</h{level}>'

    # match headings without existing id attribute, including those with child elements
    pattern = r'<h([23])>(.*?)</h\1>'
    return re.sub(pattern, replace_heading, html_content)


def get_html_template() -> str:
    """
    Get the base HTML template for documentation pages.

    Returns:
        HTML template string
    """
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{TITLE}} - MyTraL Documentation</title>
    <meta name="description" content="{{DESCRIPTION}}">
    <link rel="icon" href="../mytral-logo.png" type="image/png">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --primary: #0ea5e9;
            --secondary: #8b5cf6;
            --accent: #10b981;
            --dark: #0f172a;
            --darker: #020617;
            --gray: #64748b;
            --light-gray: #cbd5e1;
            --bg: #0f172a;
            --card-bg: #1e293b;
            --nav-width: 260px;
            --toc-width: 240px;
        }

        body {
            font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg);
            color: #e2e8f0;
            line-height: 1.6;
            position: relative;
        }

        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background:
                radial-gradient(circle at 20% 50%, rgba(14, 165, 233, 0.15) 0%, transparent 50%),
                radial-gradient(circle at 80% 80%, rgba(139, 92, 246, 0.15) 0%, transparent 50%);
            pointer-events: none;
            z-index: 0;
        }

        /* Left Navigation Sidebar */
        .docs-nav {
            position: fixed;
            left: 0;
            top: 0;
            bottom: 0;
            width: var(--nav-width);
            background: rgba(15, 23, 42, 0.95);
            border-right: 1px solid rgba(226, 232, 240, 0.1);
            overflow-y: auto;
            z-index: 100;
            padding: 2rem 0;
        }

        .nav-brand {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0 1.5rem;
            margin-bottom: 2rem;
        }

        .nav-logo {
            width: 32px;
            height: 32px;
            filter: drop-shadow(0 0 8px rgba(14, 165, 233, 0.5));
        }

        .nav-brand-text {
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.25rem;
            font-weight: 700;
            color: white;
        }

        .nav-items {
            display: flex;
            flex-direction: column;
        }

        .nav-section-title {
            padding: 0.75rem 1.5rem;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--gray);
            margin-top: 1rem;
        }

        .nav-item {
            padding: 0.625rem 1.5rem;
            color: var(--light-gray);
            text-decoration: none;
            transition: all 0.2s;
            border-left: 3px solid transparent;
            display: block;
        }

        .nav-item:hover {
            background: rgba(14, 165, 233, 0.1);
            color: white;
            border-left-color: var(--primary);
        }

        .nav-item.active {
            background: rgba(14, 165, 233, 0.15);
            color: white;
            border-left-color: var(--primary);
            font-weight: 600;
        }

        .nav-divider {
            height: 1px;
            background: rgba(226, 232, 240, 0.1);
            margin: 0.5rem 1.5rem;
        }

        /* Right TOC Sidebar */
        .docs-toc {
            position: fixed;
            right: 0;
            top: 0;
            bottom: 0;
            width: var(--toc-width);
            background: rgba(15, 23, 42, 0.95);
            border-left: 1px solid rgba(226, 232, 240, 0.1);
            overflow-y: auto;
            z-index: 100;
            padding: 2rem 1rem;
        }

        .toc-title {
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--gray);
            margin-bottom: 1rem;
            padding-left: 0.75rem;
        }

        .toc-item {
            display: block;
            padding: 0.5rem 0.75rem;
            color: var(--light-gray);
            text-decoration: none;
            font-size: 0.875rem;
            transition: all 0.2s;
            border-left: 2px solid transparent;
        }

        .toc-item:hover {
            color: white;
            border-left-color: var(--primary);
        }

        .toc-item.toc-h3 {
            padding-left: 1.5rem;
            font-size: 0.8125rem;
        }

        /* Main Content Area */
        .docs-container {
            margin-left: var(--nav-width);
            margin-right: var(--toc-width);
            padding: 3rem 4rem;
            position: relative;
            z-index: 1;
            max-width: 900px;
        }

        /* Page Header */
        .page-header {
            margin-bottom: 3rem;
            padding-bottom: 2rem;
            border-bottom: 1px solid rgba(226, 232, 240, 0.1);
        }

        .page-title {
            font-size: 3rem;
            font-weight: 700;
            margin-bottom: 1rem;
            background: linear-gradient(135deg, #ffffff 0%, var(--primary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            line-height: 1.2;
        }

        .page-description {
            font-size: 1.25rem;
            color: var(--light-gray);
            line-height: 1.8;
        }

        /* Content Styles */
        .docs-content {
            color: #e2e8f0;
        }

        .docs-content h2 {
            font-size: 2rem;
            font-weight: 700;
            margin-top: 3rem;
            margin-bottom: 1.5rem;
            color: white;
            padding-top: 1rem;
            border-top: 1px solid rgba(226, 232, 240, 0.1);
        }

        .docs-content h2:first-child {
            margin-top: 0;
            border-top: none;
            padding-top: 0;
        }

        .docs-content h3 {
            font-size: 1.5rem;
            font-weight: 600;
            margin-top: 2rem;
            margin-bottom: 1rem;
            color: white;
        }

        .docs-content p {
            margin-bottom: 1.25rem;
            line-height: 1.8;
            color: var(--light-gray);
        }

        .docs-content ul, .docs-content ol {
            margin-bottom: 1.25rem;
            padding-left: 1.5rem;
        }

        .docs-content li {
            margin-bottom: 0.5rem;
            line-height: 1.8;
            color: var(--light-gray);
        }

        .docs-content code {
            font-family: 'JetBrains Mono', monospace;
            background: var(--card-bg);
            padding: 0.2rem 0.4rem;
            border-radius: 0.25rem;
            font-size: 0.875em;
            color: var(--primary);
        }

        .docs-content pre {
            background: var(--card-bg);
            border: 1px solid rgba(226, 232, 240, 0.1);
            border-radius: 0.5rem;
            padding: 1.5rem;
            overflow-x: auto;
            margin-bottom: 1.25rem;
        }

        .docs-content pre code {
            background: none;
            padding: 0;
            color: #e2e8f0;
        }

        .docs-content a {
            color: var(--primary);
            text-decoration: none;
            transition: color 0.2s;
        }

        .docs-content a:hover {
            color: var(--secondary);
            text-decoration: underline;
        }

        .docs-content blockquote {
            border-left: 4px solid var(--primary);
            padding-left: 1.5rem;
            margin: 1.5rem 0;
            font-style: italic;
            color: var(--light-gray);
        }

        .docs-content table {
            width: 100%;
            margin-bottom: 1.25rem;
            border-collapse: collapse;
        }

        .docs-content th,
        .docs-content td {
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid rgba(226, 232, 240, 0.1);
        }

        .docs-content th {
            font-weight: 600;
            color: white;
            background: var(--card-bg);
        }

        .docs-content img {
            max-width: 100%;
            height: auto;
            border-radius: 0.5rem;
            margin: 1.5rem 0;
        }

        /* Footer */
        .docs-footer {
            margin-top: 4rem;
            padding-top: 2rem;
            border-top: 1px solid rgba(226, 232, 240, 0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.875rem;
            color: var(--gray);
        }

        .footer-links a {
            color: var(--gray);
            text-decoration: none;
            margin-left: 1rem;
            transition: color 0.2s;
        }

        .footer-links a:hover {
            color: var(--primary);
        }

        /* Responsive Design */
        @media (max-width: 1200px) {
            .docs-toc {
                display: none;
            }
            .docs-container {
                margin-right: 0;
            }
        }

        @media (max-width: 768px) {
            .docs-nav {
                transform: translateX(-100%);
                transition: transform 0.3s;
            }
            .docs-container {
                margin-left: 0;
                padding: 2rem 1.5rem;
            }
            .page-title {
                font-size: 2rem;
            }
        }
    </style>
</head>
<body>
    {{SIDEBAR_NAV}}

    <div class="docs-container">
        <div class="page-header">
            <h1 class="page-title">{{TITLE}}</h1>
        </div>

        <div class="docs-content">
            {{CONTENT}}
        </div>

        <div class="docs-footer">
            <div>&copy; 2026 MyTraL</div>
            <div class="footer-links">
                <a href="{{MINDFORGER_LINK}}" target="_blank">Doc made with MindForger</a>
                <a href="{{GITHUB_EDIT_URL}}" target="_blank">Edit on GitHub</a>
                <a href="{{GITHUB_VIEW_URL}}" target="_blank">View Source</a>
                <a href="../index.html">Home</a>
            </div>
        </div>
    </div>

    {{TOC}}
</body>
</html>
'''


def extract_title(md_content: str) -> str:
    """
    Extract title from Markdown content (first # heading).

    Args:
        md_content: Markdown content

    Returns:
        Title string
    """
    lines = md_content.split('\n')
    for line in lines:
        match = re.match(r'^#\s+(.+)$', line.strip())
        if match:
            return match.group(1).strip()
    return "Documentation"


def generate_html_page(
    md_file: Path,
    output_file: Path,
    sections: list[NavSection],
    template: str
) -> None:
    """
    Generate HTML page from Markdown file.

    Args:
        md_file: Input Markdown file path
        output_file: Output HTML file path
        sections: Navigation sections for sidebar
        template: HTML template string
    """
    print(f"Generating {output_file.name}...")

    # Read Markdown content
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()

    # Extract title
    title = extract_title(md_content)

    # Convert Markdown to HTML
    md_processor = markdown.Markdown(
        extensions=[
            'extra',
            'codehilite',
            'tables',
            'toc',
            'fenced_code',
            'nl2br'
        ]
    )
    html_content = md_processor.convert(md_content)

    # Add heading IDs for anchor links
    html_content = add_heading_ids(html_content)

    # Extract headings for TOC
    headings = extract_headings(html_content)

    # Generate navigation and TOC
    active_page = output_file.name
    sidebar_nav = generate_sidebar_nav_html(sections, active_page)
    toc_html = generate_toc_html(headings)

    # GitHub URLs
    github_edit_url = f"{GITHUB_BASE_EDIT}{md_file.name}"
    github_view_url = f"{GITHUB_BASE_VIEW}{md_file.name}"

    # Fill template
    html = template
    html = html.replace('{{TITLE}}', title)
    html = html.replace('{{DESCRIPTION}}', f"{title} - MyTraL Documentation")
    html = html.replace('{{SIDEBAR_NAV}}', sidebar_nav)
    html = html.replace('{{CONTENT}}', html_content)
    html = html.replace('{{TOC}}', toc_html)
    html = html.replace('{{GITHUB_EDIT_URL}}', github_edit_url)
    html = html.replace('{{GITHUB_VIEW_URL}}', github_view_url)

    # Write output file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate public HTML documentation from Markdown'
    )
    parser.add_argument(
        '--source',
        type=Path,
        default=Path('docs'),
        help='Source directory containing Markdown files (default: docs)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('webs/www.mytral.fitness/docs'),
        help='Output directory for HTML files (default: webs/www.mytral.fitness/docs)'
    )
    args = parser.parse_args()

    source_dir = args.source
    output_dir = args.output

    # Check source directory exists
    if not source_dir.exists():
        print(f"Error: Source directory not found: {source_dir}")
        sys.exit(1)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse sitemap
    sitemap_path = source_dir / '_SITEMAP.md'
    sections = parse_sitemap(sitemap_path)

    if not sections:
        print("Warning: No navigation sections found in sitemap")

    # Get HTML template
    template = get_html_template()

    # Generate HTML pages for all Markdown files referenced in sitemap
    generated_count = 0
    for section in sections:
        # Process section-level source
        if section.source:
            md_file = source_dir / section.source
            if md_file.exists():
                output_file = output_dir / md_filename_to_html(section.source)
                generate_html_page(md_file, output_file, sections, template)
                generated_count += 1

        # Process item sources
        for item in section.items:
            if item.source and not item.is_separator:
                md_file = source_dir / item.source
                if md_file.exists():
                    output_file = output_dir / md_filename_to_html(item.source)
                    generate_html_page(md_file, output_file, sections, template)
                    generated_count += 1
                else:
                    print(f"Warning: Markdown file not found: {md_file}")

    # Copy PNG files from source to output
    png_files = list(source_dir.glob('*.png'))
    for png_file in png_files:
        output_png = output_dir / png_file.name
        shutil.copy2(png_file, output_png)
        print(f"Copied {png_file.name}")

    print(f"\nGenerated {generated_count} HTML pages and copied {len(png_files)} images")
    print(f"Output directory: {output_dir}")


if __name__ == '__main__':
    main()
