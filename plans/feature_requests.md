# Feature Requests

Feature requests for arxivbot. Completed items are retained for historical reference.

---

## Completed

- [x] Write abstract to entries as text
- [x] Add check for duplicate entries before adding to database (i.e. if arXiv ID is already in database)

---

## Consistent logging on paper import

When importing papers via `obsidian-import`, log messages should always include **both** the user's input (URL/ID) and the resolved human-readable paper title. Currently:

- **Already in database**: logs only the raw input URL, not the paper title.
- **Newly fetched**: logs only the paper title, not the original input.

Example showing the inconsistency:

```
INFO  Already in local database, skipping: 'https://arxiv.org/abs/2110.01900' (use --force to re-fetch)
INFO  /Users/.../Papers/CLUB A Contrastive Log-ratio Upper Bound of Mutual Information.md
```

The "already in database" message gives no indication of which paper the URL corresponds to, and the "newly fetched" message gives no indication of what the user originally passed. Both cases should log the input and the title, e.g.:

```
INFO  Already in local database, skipping: 'https://arxiv.org/abs/2110.01900' — "WavLM: Large-Scale Self-Supervised Pre-Training for Full Stack Speech Processing" (use --force to re-fetch)
INFO  Fetched: 'https://arxiv.org/abs/2006.12013' — "CLUB: A Contrastive Log-ratio Upper Bound of Mutual Information"
```

---

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
