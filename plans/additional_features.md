# Additional Features Plan

## 1. Citation Count Refresh Command

### What
Add a `--refresh-citations` mode (or separate `obsidian-refresh-citations` entry point) that batch-fetches current `citationCount` and `influentialCitationCount` from S2, updates DB rows, and walks `Papers/` updating the `citation_count` field in each note's frontmatter via `_update_existing_note`.

### Why
Citation count is the one field that goes stale quickly. Currently requires a full `--force` re-import which is heavier than necessary. The entire vault can be refreshed in 1-2 API calls since `S2_BATCH_SIZE=500`.

### Implementation
1. Read all `s2_paper_id` values from the SQLite DB
2. Batch-fetch only `citationCount` and `influentialCitationCount` from S2 (smaller payload)
3. Update DB rows via `upsert_paper`
4. Walk `Papers/*.md`, match by `s2_paper_id` in frontmatter, update `citation_count` via `_update_existing_note`
5. Add `--refresh-citations` flag to `ArgumentParser` in `main()`

---

## 2. Vault Audit / Drift Report

### What
An `obsidian-audit` command that compares the SQLite DB against `Papers/` and reports three classes of divergence:
- (a) Notes whose filename title no longer matches the DB title (title drift from `sanitize_filename`)
- (b) Notes that exist in the vault but have no corresponding DB row (from older import paths or manual creation)
- (c) DB rows that have no corresponding note file

### Why
The vault has lived through at least two importer generations (Notion CSV migration, arXiv API, now S2). The `migrate_notion_obsidian.py` script imports from a different code path that does not write to the DB. The audit makes invisible drift visible without touching anything.

### Implementation
1. Load all DB rows into a dict keyed by `paper_id` and `arxiv_id`
2. Walk `Papers/*.md`, parse frontmatter, check for matching DB row
3. Report mismatches as a Rich table or TSV
4. Add as a new entry point: `python -m arxivbot.audit`

---

## 3. `--from-file` Bulk Input Mode

### What
Extend `ArgumentParser` to accept `--from-file <path>` as an alternative to positional `id_list` arguments. One identifier per line, `#` comments allowed.

### Why
Current workflow requires pasting IDs on the command line, awkward for >10 papers. A reading list file is natural for managing a backlog. The `find_arxiv_links.py` script already outputs newline-separated IDs.

### Implementation
1. Add `--from-file` argument to `ArgumentParser`
2. If provided, read file, strip comments/blanks, extend `id_list`
3. Feed into existing Phase 1/2/3 pipeline (deduplication, local-DB skipping, batch fetching all continue to work)

---

## 4. Frontmatter Consistency Validator

### What
An `obsidian-validate` command that checks every `.md` in `Papers/` against the canonical schema (`_FRONTMATTER_KEY_ORDER`). Reports:
- Missing required keys (e.g. `s2_paper_id`, `arxiv_id`)
- Keys present but holding empty strings vs `None` vs YAML null
- Notes where key order deviates from canonical
- Optional `--fix` to rewrite non-conforming notes in-place

### Why
`_update_existing_note` is additive and never overwrites, so field-order guarantees only hold for newly written notes. Older notes will have differing key orders, causing inconsistent Dataview query results. The validator makes scope of inconsistency concrete and `--fix` resolves it without re-fetching from S2.

### Implementation
1. Walk `Papers/*.md`, parse frontmatter
2. Compare key set and key order against `_FRONTMATTER_KEY_ORDER`
3. Flag inconsistencies (missing, extra, misordered, null-vs-empty)
4. `--fix` mode: rebuild frontmatter dict in canonical order via `yaml.dump(sort_keys=False)`, write back
5. Add as entry point: `python -m arxivbot.validate`

---

## 5. `obsidian-stats` Vault Summary

### What
An `obsidian-stats` command that queries the SQLite DB and prints:
- Total papers
- Year-by-year publication distribution
- Top 10 venues by paper count
- Top 10 fields of study
- Papers with/without TLDRs
- Papers with/without PDFs
- Top 10 most-cited papers

### Why
The DB already mirrors the vault's paper metadata. A few `GROUP BY` aggregations give genuine insight into reading habits and collection shape with near-zero implementation cost. Also immediately surfaces data quality issues (e.g. papers with `year = NULL`).

### Implementation
1. Query DB with standard SQL aggregations
2. `fields_of_study` is stored as JSON array — `json.loads` per row + `Counter`
3. Output as Rich table with optional `--format tsv` flag
4. Add as entry point: `python -m arxivbot.stats`
