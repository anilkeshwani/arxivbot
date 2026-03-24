import os
from pathlib import Path

_default_vault = Path("~/Desktop/journal/").expanduser().resolve()

OBSIDIAN_VAULT_DIR = Path(os.environ.get("OBSIDIAN_VAULT_DIR", str(_default_vault))).expanduser().resolve()
PAPERS_DIR = Path(os.environ.get("OBSIDIAN_PAPERS_DIR", str(OBSIDIAN_VAULT_DIR / "Papers"))).expanduser().resolve()
PDFS_DIR = Path(os.environ.get("OBSIDIAN_PDFS_DIR", str(OBSIDIAN_VAULT_DIR / "PDFs"))).expanduser().resolve()
DEFAULT_PAPER_TAGS = ["paper"]

# Semantic Scholar API
S2_FIELDS = [
    "paperId",
    "title",
    "abstract",
    "authors",
    "year",
    "publicationDate",
    "venue",
    "externalIds",
    "url",
    "openAccessPdf",
    "tldr",
    "fieldsOfStudy",
    "citationCount",
    "influentialCitationCount",
]

S2_BATCH_SIZE = 500  # Max IDs per POST /paper/batch request

# Database
DB_PATH = Path(os.environ.get("OBSIDIAN_DB_PATH", str(OBSIDIAN_VAULT_DIR / ".papers.db"))).expanduser().resolve()
