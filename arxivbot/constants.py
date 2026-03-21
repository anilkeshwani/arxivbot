from pathlib import Path


OBSIDIAN_VAULT_DIR = Path("~/Desktop/journal/").expanduser().resolve()
PAPERS_DIR = OBSIDIAN_VAULT_DIR / "Papers"
PDFS_DIR = OBSIDIAN_VAULT_DIR / "PDFs"
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
DB_PATH = OBSIDIAN_VAULT_DIR / ".papers.db"
