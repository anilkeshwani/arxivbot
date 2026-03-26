# Feature Requests

Feature requests for arxivbot. Completed items are retained for historical reference.

---

## Completed

- [x] Write abstract to entries as text
- [x] Add check for duplicate entries before adding to database (i.e. if arXiv ID is already in database)
- [x] Consistent logging on paper import — show both user input and paper title in all cases
- [x] arXiv API fallback for papers not indexed by Semantic Scholar
- [x] Prevent yaml.dump from wrapping long strings in frontmatter

---

## Dedup guardrail for arXiv-only papers re-imported via S2

When a paper is first imported via the arXiv API fallback, it gets a synthetic `paper_id` of `"arxiv:{id}"`. If Semantic Scholar later indexes the same paper and the user re-imports it, a new row is created under the S2 SHA — resulting in a duplicate. Need a check against `arxiv_id` during import/upsert to detect this overlap and migrate the existing row rather than creating a second one.

## Frontmatter update rewrites entire YAML document

`_update_existing_note` round-trips the full frontmatter through `yaml.safe_load` → `yaml.dump`. Even with `width=inf`, this still changes quoting style (`"` → `'`) and list indentation for fields that weren't modified. Ideally the function should insert only the new keys into the raw YAML text without re-serializing existing fields.

## Non-arXiv papers not in database

161 vault papers have no arXiv ID (sourced from ACL Anthology, IEEE, JMLR, direct PDFs, etc.) and therefore can't be backfilled via the S2 or arXiv APIs. Would need support for additional metadata sources (e.g. Crossref via DOI, or direct scraping) or a manual import pathway.

## Cleaner abstracts

- Parse URLs in abstracts and hyperlink them
- Parse LaTeX and render it as an equation

## Telegram integration

Provide integration via Telegram so that users can send their paper link to an authenticated channel and GitHub Actions will trigger uploads nightly or in response to a Telegram trigger.

## Kindle / epub support

Read arXiv papers as epubs on a Kindle.

References:
- https://tex.stackexchange.com/questions/1551/use-latex-to-produce-epub
- https://www.reddit.com/r/MachineLearning/comments/5xtnl4/d_reading_arxiv_preprints_on_an_ereader/
