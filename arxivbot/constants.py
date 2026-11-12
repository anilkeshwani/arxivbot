import os
from pathlib import Path

_default_vault = Path("~/Desktop/journal/").expanduser().resolve()

OBSIDIAN_VAULT_DIR = Path(os.environ.get("OBSIDIAN_VAULT_DIR", str(_default_vault))).expanduser().resolve()
PAPERS_DIR = Path(os.environ.get("OBSIDIAN_PAPERS_DIR", str(OBSIDIAN_VAULT_DIR / "Papers"))).expanduser().resolve()
PDFS_DIR = Path(os.environ.get("OBSIDIAN_PDFS_DIR", str(OBSIDIAN_VAULT_DIR / "PDFs"))).expanduser().resolve()
CLIPPINGS_DIR = (
    Path(os.environ.get("OBSIDIAN_CLIPPINGS_DIR", str(OBSIDIAN_VAULT_DIR / "Clippings"))).expanduser().resolve()
)
# Pages the Telegram bot could not clip, to clip by hand: the queue itself, and a note listing it
_default_clip_queue = OBSIDIAN_VAULT_DIR / ".clip-queue.json"
CLIP_QUEUE_PATH = Path(os.environ.get("OBSIDIAN_CLIP_QUEUE_PATH", str(_default_clip_queue))).expanduser().resolve()
CLIP_QUEUE_NOTE = (
    Path(os.environ.get("OBSIDIAN_CLIP_QUEUE_NOTE", str(OBSIDIAN_VAULT_DIR / "Clip Queue.md"))).expanduser().resolve()
)
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
