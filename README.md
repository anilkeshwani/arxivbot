# arxivbot

A minimal paper clipper for Obsidian, powered by Semantic Scholar.

## Installation

Install as a tool (recommended for general use):

```bash
uv tool install git+https://github.com/anilkeshwani/arxivbot
```

Or into a project environment:

```bash
uv pip install .
# or
pip install .
```

## Configuration

### API key

Set `S2_API_KEY` in your environment, or copy `credentials_template.env` to `credentials.env` in the directory where you run `obsidian-import`:

```bash
cp credentials_template.env credentials.env
```

```
S2_API_KEY="your_key_here"
```

An S2 API key is optional — unauthenticated requests work but share a rate-limited pool. Request a key at https://www.semanticscholar.org/product/api#api-key-form.

### Environment variables

All paths can be overridden via environment variables (defaults shown):

| Variable | Default | Description |
|---|---|---|
| `OBSIDIAN_VAULT_DIR` | `~/Desktop/journal/` | Root of your Obsidian vault |
| `OBSIDIAN_PAPERS_DIR` | `$OBSIDIAN_VAULT_DIR/Papers` | Directory for paper notes |
| `OBSIDIAN_PDFS_DIR` | `$OBSIDIAN_VAULT_DIR/PDFs` | Directory for downloaded PDFs |
| `OBSIDIAN_DB_PATH` | `$OBSIDIAN_VAULT_DIR/.papers.db` | SQLite database path |
| `S2_API_KEY` | _(none)_ | Semantic Scholar API key |

## Usage

```
obsidian-import <id> [<id> ...] [--no_pdf] [--force]
```

### Arguments

| Argument | Description |
|---|---|
| `id` | One or more paper identifiers: arXiv IDs, arXiv URLs, S2 paper IDs, S2 URLs, or DOIs |
| `--no_pdf` | Skip PDF download |
| `--force` | Re-fetch papers already present in the local database |

### Examples

```bash
# Import by arXiv ID
obsidian-import 2408.16532

# Import by arXiv URL
obsidian-import https://arxiv.org/abs/1706.03762

# Import by Semantic Scholar URL
obsidian-import https://www.semanticscholar.org/paper/ebdbded60f48131ed7ba73807c3c086993a96f89

# Import by DOI
obsidian-import DOI:10.18653/v1/N18-3011

# Import multiple papers, skip PDF download
obsidian-import 2408.16532 1706.03762 --no_pdf

# Re-fetch a paper that's already in the database
obsidian-import 2408.16532 --force
```

## Directory structure

```
.
├── README.md
├── arxivbot/
│   ├── __init__.py
│   ├── constants.py
│   ├── database.py
│   ├── find_arxiv_links.py
│   ├── obsidian_importer.py
│   └── utils.py
├── credentials_template.env
├── plans/
│   ├── additional_features.md
│   ├── ai_summary_generation.md
│   ├── feature_requests.md
│   ├── resources.md
│   └── s2_api_migration_reference.md
├── pyproject.toml
└── uv.lock
```

## Development

Install pre-commit hooks:

```bash
pre-commit install
```

Lint and format with [ruff](https://github.com/astral-sh/ruff):

```bash
ruff check --fix .
ruff format .
```

## Resources

- [danielnsilva/semanticscholar](https://github.com/danielnsilva/semanticscholar) — Python client for the S2 API
