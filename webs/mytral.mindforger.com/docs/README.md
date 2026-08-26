# Public Documentation for www.mytral.fitness

This directory contains auto-generated HTML documentation pages for the public-facing website at www.mytral.fitness/docs.

## Features

- **Modern Dark Theme**: Based on the design from index.html with Space Grotesk font and dark gradient background
- **Left Sidebar Navigation**: Page navigation generated from `docs/_SITEMAP.md`
- **Right Sidebar TOC**: Table of contents for in-page navigation (headings from the document)
- **Responsive Layout**: Adapts to different screen sizes

## Generation

Documentation is generated from Markdown files in the `docs/` directory using:

```bash
make www-docs
```

This will:
1. Parse `docs/_SITEMAP.md` for navigation structure
2. Convert Markdown files to HTML with modern styling
3. Generate left sidebar with page links
4. Generate right sidebar with table of contents
5. Copy image files (*.png) from docs/ to this directory

## Development

### Generate documentation
```bash
make www-docs
```

### Clean generated files
```bash
make www-docs-clean
```

### Serve locally for preview
```bash
make www-docs-serve
```
Then open http://localhost:8080

## Files

- `*.html` - Generated HTML documentation pages (do not edit manually)
- `*.png` - Copied image files from docs/ directory (do not edit manually)

All generated files are ignored by git (see `.gitignore`).
