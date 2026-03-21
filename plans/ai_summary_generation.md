# AI Summary Generation Plan

## Goal
Automate generation of Opus 4.6 paper summaries for all papers in the vault that don't already have one. Process PDFs directly for highest fidelity.

## Scale
- ~2,053 papers without AI summaries
- ~854 with `pdf_url` in frontmatter, ~886 with `arxiv_id` (all arXiv papers have constructable PDF URLs)
- ~158 non-arXiv papers where PDF access may require alternative approaches

## Convention (from existing 9 summaries)

### H2 Heading Format
```
## [Paper Title]: Summary by Opus 4.6 #llm-generated/claude-opus-4-6
```

### Info Callout (immediately below H2)
```
> [!info] #llm-generated/claude-opus-4-6
> Date: YYYY-MM-DD
> Source: Claude Code CLI
```

### Summary Structure (H3 subheadings, following paper's own structure)
1. **Problem / Context** — what gap the paper addresses, what preceded it
2. **The Contribution / Solution** — what the paper introduces, named subsections matching paper architecture
3. **Methodology / How It Works** — detailed technical explanation, preserving equations, training procedures, architectural decisions
4. **Results** — precise quantitative benchmarks, tables, ablations
5. **Limitations / Broader Significance** — honest accounting of what didn't work or isn't covered

Written for a Master's-level ML engineer. Mathematical notation preserved where load-bearing.

### Placement
Appended after the abstract callout and `---` separator, at the end of the document.

## Idempotency
Check for `#llm-generated/claude-opus-4-6` in the note body text. If present, skip.

## PDF Processing Options

### Option A: pymupdf4llm (existing `pdf-to-md` skill)
- Converts PDF to Markdown with images, preserving structure
- Good for tables, figures, layout
- Already available as a skill in the project
- Generates intermediate Markdown that can be passed as context to Claude

### Option B: Direct PDF bytes to Claude API
- Pass raw PDF to Claude's document understanding via the API
- Highest fidelity — Claude sees the actual rendered document
- Simpler pipeline (no intermediate conversion)
- Cost: ~$0.10-0.30 per paper depending on length

### Option C: LaTeX source from arXiv
- Fetch LaTeX source instead of PDF for arXiv papers
- Highest fidelity for equations and notation
- More complex: need to download, extract, find main .tex file
- Not all arXiv papers have accessible source

### Recommendation
Option B (direct PDF to Claude API) for simplicity and fidelity. Fall back to Option A for non-arXiv papers where direct PDF URLs may not work.

## Implementation Design

### New module: `arxivbot/summarizer.py`

```python
def needs_summary(note_path: Path) -> bool:
    """Check if note already has an Opus 4.6 summary."""
    text = note_path.read_text()
    return "#llm-generated/claude-opus-4-6" not in text

def fetch_pdf(pdf_url: str) -> bytes:
    """Download PDF from URL."""

def generate_summary(pdf_bytes: bytes, title: str, authors: list[str]) -> str:
    """Call Claude API with PDF and return formatted summary section."""

def append_summary(note_path: Path, summary: str) -> None:
    """Append summary section to end of note."""

def process_vault(papers_dir: Path, dry_run: bool = False) -> None:
    """Walk vault, find papers needing summaries, generate and append."""
```

### Prompt Template
```
You are summarizing an academic paper for a research vault. The reader is a Master's-level ML engineer.

Paper: {title}
Authors: {authors}

Provide a comprehensive summary structured as:
1. Problem / Context — what gap the paper addresses
2. The Contribution — what the paper introduces
3. Methodology — detailed technical explanation (preserve equations, training procedures)
4. Results — precise quantitative benchmarks, ablations
5. Limitations / Broader Significance

Use H3 (###) headings that follow the paper's own structure where possible.
Preserve mathematical notation. Be precise about numbers and benchmarks.
```

### CLI Entry Point
```bash
python -m arxivbot.summarizer [--dry-run] [--limit N] [--paper TITLE]
```

- `--dry-run`: list papers that need summaries without generating
- `--limit N`: process only first N papers (for cost control / testing)
- `--paper TITLE`: process a single specific paper

### Error Handling & Resume
- Log each paper processed to a simple state file (`~/.papers_summarized.txt`)
- On restart, skip already-processed papers
- Failed papers logged separately for retry

### Cost Estimate
- ~854 arXiv papers with PDF URLs
- ~$0.10-0.30 per Opus 4.6 call with full paper PDF
- Total: ~$85-250 for full vault
- Recommend starting with `--limit 10` for validation

### Frontmatter Tag Addition
After appending summary, also add `llm-generated/claude-opus-4-6` to the `tags` list in frontmatter (using `_update_existing_note` pattern).
