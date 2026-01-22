# CI Audit Documentation

This directory contains the MkDocs-based documentation for the CI Audit system.

## Building the Documentation

### Prerequisites

Install documentation dependencies:

```bash
pip install mkdocs mkdocs-material mkdocstrings[python] pymdown-extensions
```

Or install all dependencies including docs:

```bash
pip install -r requirements.txt
```

### Local Development Server

Start the MkDocs development server to preview docs locally:

```bash
# From the project root directory
mkdocs serve
```

The documentation will be available at: `http://127.0.0.1:8000`

**Features of development server**:

- Live reload on file changes
- Search functionality
- Full navigation

### Build Static Site

Build the documentation as static HTML:

```bash
mkdocs build
```

This creates a `site/` directory with the built documentation.

### Deploy to GitHub Pages

Deploy documentation to GitHub Pages:

```bash
mkdocs gh-deploy
```

This builds and pushes documentation to the `gh-pages` branch.

## Documentation Structure

```
docs/
├── index.md                 # Home page
├── setup/                   # Installation and configuration
├── prow/                    # Prow CI and testing overview
├── analysis/                # Data analysis sections
│   ├── duration/            # Test duration analysis
│   ├── failures/            # Failure analysis
│   └── failure-types/       # Breakdown by failure type
├── findings/                # Analysis results and insights
├── code/                    # Code examples and query library
└── api/                     # API reference (auto-generated)
```

## Writing Documentation

### Markdown Features

The documentation uses [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) with extended Markdown features:

**Code blocks with syntax highlighting**:

```python
def example():
    return "Hello"
```

**Admonitions**:

```markdown
!!! note
    This is a note.

!!! warning
    This is a warning.
```

**Tabbed content**:

```markdown
=== "Tab 1"
    Content 1

=== "Tab 2"
    Content 2
```

**Task lists**:

```markdown
- [x] Completed task
- [ ] Pending task
```

### Navigation

Edit `mkdocs.yml` to modify the navigation structure:

```yaml
nav:
  - Home: index.md
  - Setup:
    - Installation: setup/installation.md
```

### API Documentation

API reference pages use mkdocstrings to auto-generate documentation from Python docstrings:

```markdown
::: ci_audit.collectors.github_collector
    options:
      show_source: true
```

Ensure your Python code has proper docstrings:

```python
def example_function(param: str) -> int:
    """
    Brief description.

    Args:
        param: Parameter description

    Returns:
        Return value description
    """
    ...
```

## Adding Analysis Results

As you complete analysis tasks:

1. **Update placeholder sections** marked with `<!-- TODO: ... -->`
2. **Add SQL queries** and results in code blocks
3. **Include visualizations** by saving plots to `docs/images/` and referencing:
   ```markdown
   ![Chart Title](../images/chart.png)
   ```
4. **Add Python code** in code blocks with syntax highlighting

### Example Analysis Page

```markdown
# Analysis Title

## Overview

Brief description of the analysis.

## SQL Query

\```sql
SELECT COUNT(*) FROM test_cases WHERE status = 'failed';
\```

## Results

Total failed tests: 1,234

## Visualization

![Failure Distribution](../images/failure_distribution.png)

## Findings

Key insights from the analysis.
```

## Configuration

### Theme Customization

Edit `mkdocs.yml` to customize the Material theme:

```yaml
theme:
  name: material
  palette:
    - scheme: default      # Light mode
      primary: indigo
      accent: indigo
```

### Plugins

Currently enabled plugins:

- `search`: Full-text search
- `mkdocstrings`: API documentation generation

### Extensions

Enabled Markdown extensions:

- `pymdownx.highlight`: Code highlighting
- `pymdownx.superfences`: Code blocks
- `pymdownx.tabbed`: Tabbed content
- `admonition`: Callout boxes
- `tables`: Markdown tables

## Troubleshooting

### Build Errors

```bash
# Clear cache and rebuild
rm -rf site/
mkdocs build
```

### Development Server Not Reloading

- Check file permissions
- Restart the server: `Ctrl+C` then `mkdocs serve`

### Missing API Documentation

Ensure:

- Python modules are importable
- Docstrings are properly formatted
- Module paths in `mkdocs.yml` are correct

## Related Files

- `mkdocs.yml`: Main configuration file
- `requirements.txt`: Python dependencies (includes MkDocs)
- `CLAUDE.md`: Project instructions for Claude Code

## Resources

- [MkDocs Documentation](https://www.mkdocs.org/)
- [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
- [mkdocstrings](https://mkdocstrings.github.io/)
- [PyMdown Extensions](https://facelessuser.github.io/pymdown-extensions/)
