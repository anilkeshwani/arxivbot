from pathlib import Path


OBSIDIAN_VAULT_DIR = Path("~/Desktop/journal/").expanduser()
PAPERS_DIR = OBSIDIAN_VAULT_DIR / "Papers"
PDFS_DIR = OBSIDIAN_VAULT_DIR / "PDFs"
PDFS_INDEX = PDFS_DIR / "index.tsv"
PDFS_INDEX_FIELD_NAMES = ["ID", "Published", "Added", "Title"]
PDFS_INDEX_ID = "ID"
