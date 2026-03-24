# Semantic Scholar API Migration Reference

> **Status: Complete.** The migration from the `arxiv` Python package to the Semantic Scholar API is done. This document is retained as a reference.

Reference document for migrating arxivbot from the `arxiv` Python package to the Semantic Scholar (S2) Academic Graph API.

Researched: 2026-03-17

---

## 1. Semantic Scholar Academic Graph API

### 1.1 Base URL and Versioning

| API | Base URL |
|-----|----------|
| Academic Graph API | `https://api.semanticscholar.org/graph/v1` |
| Recommendations API | `https://api.semanticscholar.org/recommendations/v1` |
| Datasets API | `https://api.semanticscholar.org/datasets/v1/` |

Only the Academic Graph API is relevant for this migration.

Documentation:
- API docs (Swagger/Redoc): https://api.semanticscholar.org/api-docs/graph
- OpenAPI spec: https://api.semanticscholar.org/graph/v1/swagger.json
- Tutorial: https://www.semanticscholar.org/product/api/tutorial
- Release notes: https://github.com/allenai/s2-folks/blob/main/API_RELEASE_NOTES.md

### 1.2 Authentication

API key is passed via HTTP header:

| Header | Value |
|--------|-------|
| `x-api-key` | Your API key string |

Example:
```bash
curl -H "x-api-key: YOUR_KEY" "https://api.semanticscholar.org/graph/v1/paper/ArXiv:2408.16532?fields=title"
```

API keys are **optional** for most endpoints. Unauthenticated requests use a shared rate limit pool (see below).

To request an API key: https://www.semanticscholar.org/product/api#api-key-form

**Important notes from release notes (Nov 2024):**
- Keys from free email domains (gmail, etc.) are no longer accepted
- Inactive keys (~60 days of no use) are automatically revoked
- Third-party app key requests are no longer approved

### 1.3 Rate Limits

| User Type | Rate Limit | Notes |
|-----------|-----------|-------|
| **Unauthenticated** | 5,000 requests per 5 minutes (shared pool) | Shared across ALL unauthenticated users. Subject to additional throttling during heavy traffic. |
| **Authenticated (new key)** | 1 RPS on all endpoints | Introductory rate for all new key requests |
| **Authenticated (established)** | 1 RPS on `/paper/batch`, `/paper/search`, `/recommendations`; 10 RPS on all other endpoints | Higher rates may be granted after review |

**Rate limit response (HTTP 429):**
```json
{
  "message": "Too Many Requests. Please wait and try again or apply for a key for higher rate limits. https://www.semanticscholar.org/product/api#api-key-form",
  "code": "429"
}
```

**No `Retry-After` header is provided.** The response headers include standard AWS CloudFront/API Gateway headers but no rate-limit-specific headers (no `X-RateLimit-Remaining`, `X-RateLimit-Limit`, or `Retry-After`). Confirmed by inspecting actual response headers.

### 1.4 Paper Lookup Endpoint

```
GET /graph/v1/paper/{paper_id}?fields=<comma-separated fields>
```

#### Accepted `paper_id` Formats

| Format | Example | Notes |
|--------|---------|-------|
| S2 Paper ID (SHA) | `649def34f8be52c8b66281af98ae884c09aef38b` | 40-char hex hash |
| `CorpusId:<id>` | `CorpusId:215416146` | Numeric S2 corpus ID |
| `DOI:<doi>` | `DOI:10.18653/v1/N18-3011` | Digital Object Identifier |
| `ARXIV:<id>` | `ARXIV:2106.15928` | arXiv identifier (no version suffix) |
| `MAG:<id>` | `MAG:112218234` | Microsoft Academic Graph ID |
| `ACL:<id>` | `ACL:W12-3903` | ACL Anthology ID |
| `PMID:<id>` | `PMID:19872477` | PubMed/Medline ID |
| `PMCID:<id>` | `PMCID:2323736` | PubMed Central ID |
| `URL:<url>` | `URL:https://arxiv.org/abs/2106.15928` | URL from recognized sites |

**Recognized URL domains for `URL:` format:** semanticscholar.org, aclweb.org, arxiv.org, acm.org, biorxiv.org

**Verified by live API calls:** `ARXIV:`, `DOI:`, `CorpusId:`, and `URL:` formats all confirmed working.

**Important for migration:** The arxivbot currently uses bare arXiv IDs like `2408.16532`. For S2 lookup, prefix with `ARXIV:` to get `ARXIV:2408.16532`.

#### Available Fields (via `fields` query parameter)

Fields are requested as a comma-separated list. Default response includes only `paperId` and `title`.

**Core scalar fields:**

| Field | Type | Description | Example Value |
|-------|------|-------------|---------------|
| `paperId` | string | S2 40-char hex ID | `"ebdbded60f48131ed7ba73807c3c086993a96f89"` |
| `corpusId` | integer | Numeric S2 corpus ID | `272146429` |
| `url` | string | S2 paper page URL | `"https://www.semanticscholar.org/paper/ebdbd..."` |
| `title` | string | Paper title | `"Attention is All you Need"` |
| `abstract` | string | Full abstract text | (full text) |
| `venue` | string | Publication venue name | `"Neural Information Processing Systems"` |
| `year` | integer | Publication year only | `2017` |
| `referenceCount` | integer | Number of references | `41` |
| `citationCount` | integer | Total citation count | `169526` |
| `influentialCitationCount` | integer | Influential citations | `19437` |
| `isOpenAccess` | boolean | Open access flag | `true` |
| `publicationDate` | string or null | Date in YYYY-MM-DD format | `"2017-06-12"` or `null` |
| `publicationTypes` | array of strings | Paper type labels | `["JournalArticle", "Conference"]` |

**Structured object fields:**

| Field | Type | Description |
|-------|------|-------------|
| `externalIds` | object | External IDs: `ArXiv`, `DOI`, `DBLP`, `MAG`, `CorpusId`, `PubMed`, `PubMedCentral`, `ACL` |
| `tldr` | object | `{"model": "tldr@v2.0.0", "text": "..."}` — AI-generated one-line summary |
| `openAccessPdf` | object | `{"url": "...", "status": "GREEN"/"HYBRID"/null, "license": ..., "disclaimer": ...}` |
| `authors` | array | `[{"authorId": "...", "name": "..."}]` |
| `journal` | object | `{"name": "...", "volume": "...", "pages": "..."}` |
| `publicationVenue` | object | `{"id": "...", "name": "...", "type": "conference"/"journal", "alternate_names": [...], "url": "..."}` |
| `fieldsOfStudy` | array of strings | `["Computer Science", "Engineering"]` |
| `s2FieldsOfStudy` | array of objects | S2-specific field classifications |
| `citationStyles` | object | Citation strings in various formats |
| `embedding` | object | Paper embedding vectors (e.g. `embedding.specter_v2`) |

**Nested/expandable fields:**

| Field | Type | Description |
|-------|------|-------------|
| `authors` | array | Each has `authorId` and `name`; can expand with `authors.*` |
| `citations` | array | Papers citing this paper; expandable with `citations.title`, `citations.abstract`, etc. |
| `references` | array | Papers this paper cites; expandable with `references.title`, etc. |

#### Critical Field Details

**`tldr`** — Returns an object with two keys:
```json
{
  "model": "tldr@v2.0.0",
  "text": "A new simple network architecture, the Transformer, based solely on attention mechanisms..."
}
```
This is an AI-generated one-sentence summary. Very useful for arxivbot.

**`externalIds`** — Always includes `CorpusId`. Includes `ArXiv` when paper is on arXiv. Example:
```json
{
  "DBLP": "journals/corr/VaswaniSPUJGKP17",
  "MAG": "2963403868",
  "ArXiv": "1706.03762",
  "CorpusId": 13756489
}
```
Note: The `ArXiv` value is the bare ID (e.g. `"1706.03762"`), NOT a URL. Does NOT include version numbers.

**`publicationDate`** — See dedicated section below (Section 4).

**`openAccessPdf`** — Returns an object:
```json
{
  "url": "http://arxiv.org/pdf/1705.09406",
  "status": "GREEN",
  "license": null
}
```
Status values follow the OpenAccess classification: `"GREEN"`, `"HYBRID"`, or `null`.
When a paper is known to be on arXiv but S2 doesn't classify it as open access, the `url` field may be an empty string `""` with `status: null`. **Cannot be relied upon as sole PDF source for arXiv papers.**

### 1.5 Batch Endpoint

```
POST /graph/v1/paper/batch?fields=<comma-separated fields>
Content-Type: application/json

{
  "ids": ["ARXIV:2408.16532", "ARXIV:1706.03762"]
}
```

| Property | Value |
|----------|-------|
| Max batch size | **500 paper IDs** |
| Max response size | **10 MB** |
| Rate limit (authenticated) | 1 RPS |
| Accepts same ID formats as single lookup | Yes |

**Response:** Returns a JSON array in the **same order and size** as the requested IDs. If a paper is not found, the corresponding array element is `null`.

Verified by live API call:
```json
[
  {"paperId": "ebdbd...", "title": "WavTokenizer...", "publicationDate": "2024-08-29"},
  {"paperId": "204e3...", "title": "Attention is All you Need", "publicationDate": "2017-06-12"}
]
```

### 1.6 Search Endpoint

#### Relevance Search

```
GET /graph/v1/paper/search?query=<query>&fields=<fields>&limit=<n>&offset=<n>
```

| Parameter | Required | Default | Max | Description |
|-----------|----------|---------|-----|-------------|
| `query` | Yes | — | — | Plain-text search query |
| `fields` | No | `paperId`, `title` | — | Comma-separated field list |
| `limit` | No | 100 | 100 | Results per page |
| `offset` | No | 0 | — | Pagination offset |
| `publicationDateOrYear` | No | — | — | Filter: `YYYY-MM-DD:YYYY-MM-DD` |
| `year` | No | — | — | Filter by year or range: `2020-2023` |
| `venue` | No | — | — | Filter by venue |
| `fieldsOfStudy` | No | — | — | Filter by field |
| `publicationTypes` | No | — | — | Filter by type |
| `openAccessPdf` | No | — | — | Filter to open access only |
| `minCitationCount` | No | — | — | Minimum citations |

**Max total results:** 1,000 (reduced from 10,000 in October 2023).

**Response format:**
```json
{
  "total": 437,
  "offset": 0,
  "next": 3,
  "data": [
    {"paperId": "...", "title": "...", ...},
    ...
  ]
}
```

#### Bulk Search

```
GET /graph/v1/paper/search/bulk?query=<query>&fields=<fields>&sort=<field>:<order>
```

Returns up to 1,000 papers per call. Uses continuation token for pagination. Supports boolean query operators: `+` (AND), `|` (OR), `-` (NOT), `"phrase"`, `*wildcard`, `~edit_distance`. Supports sorting by `publicationDate` or `citationCount`.

### 1.7 Error Handling

| HTTP Status | Meaning | Response Body |
|-------------|---------|---------------|
| 200 | Success | JSON response |
| 400 | Bad Request | `{"error": "..."}` — malformed request, invalid field name, etc. |
| 401 | Unauthorized | Invalid or missing API key (for endpoints that require one) |
| 403 | Forbidden | Access denied |
| 404 | Not Found | `{"error": "Paper with id ArXiv:9999.99999 not found"}` |
| 429 | Too Many Requests | `{"message": "Too Many Requests...", "code": "429"}` |
| 500 | Internal Server Error | Server-side failure |

All confirmed by live API testing (404 and 429 tested directly).

---

## 2. arXiv API (via `arxiv` Python Package)

### 2.1 Package Details

| Property | Value |
|----------|-------|
| Package | `arxiv` (PyPI) |
| Current version | 2.4.1 (installed in this project at 2.2.0+) |
| Underlying API | arXiv Atom feed API |

### 2.2 `arxiv.Result` Object Fields

Confirmed by live inspection (running `arxiv` 2.4.1 against paper `2408.16532`):

| Field | Type | Example Value |
|-------|------|---------------|
| `title` | `str` | `"WavTokenizer: an Efficient Acoustic Discrete Codec Tokenizer for Audio Language Modeling"` |
| `entry_id` | `str` | `"http://arxiv.org/abs/2408.16532v3"` |
| `published` | `datetime` (tz-aware) | `2024-08-29 13:43:36+00:00` |
| `updated` | `datetime` (tz-aware) | `2025-02-25 11:45:12+00:00` |
| `summary` | `str` | Full abstract text (may contain `\n` line breaks) |
| `authors` | `list[arxiv.Result.Author]` | Each has `.name` attribute |
| `primary_category` | `str` | `"eess.AS"` |
| `categories` | `list[str]` | `["eess.AS", "cs.LG", "cs.MM", "cs.SD", "eess.SP"]` |
| `pdf_url` | `str` | `"https://arxiv.org/pdf/2408.16532v3"` |
| `doi` | `str` or `None` | Often `None` for preprints |
| `links` | `list[arxiv.Result.Link]` | Each has `.href`; includes abs and pdf URLs |
| `comment` | `str` or `None` | `"Accepted by ICLR 2025"` |
| `journal_ref` | `str` or `None` | Often `None` |

### 2.3 `entry_id` Format

Format: `http://arxiv.org/abs/YYMM.NNNNN[vN]`

Example: `http://arxiv.org/abs/2408.16532v3`

This is a full URL with version suffix. The current `canonicalise_arxiv()` in arxivbot strips this to just `2408.16532` (or with version if present).

---

## 3. Field Mapping Table

Fields currently used by arxivbot mapped to their S2 API equivalents:

| Usage in arxivbot | `arxiv.Result` field | S2 API field | S2 field type | Format differences |
|---|---|---|---|---|
| Paper title | `arxiv_paper.title` | `title` | `string` | Identical string content |
| Authors list | `arxiv_paper.authors` → `[a.name for a in ...]` | `authors` | `array` of `{"authorId", "name"}` | S2 returns objects; extract `.name`. Author ordering is preserved. |
| Published datetime | `arxiv_paper.published` | `publicationDate` | `string` or `null` | **CRITICAL DIFFERENCE:** arXiv gives full datetime with time+timezone (`2024-08-29 13:43:36+00:00`). S2 gives date only (`"2024-08-29"`) or `null`. See Section 4. |
| Published year | (derived from `published`) | `year` | `integer` | S2 has it as a separate field |
| Link / entry ID | `arxiv_paper.entry_id` | `url` (S2 page URL) or `externalIds.ArXiv` | `string` | arXiv gives `http://arxiv.org/abs/2408.16532v3`. S2 `url` gives `https://www.semanticscholar.org/paper/<sha>`. To reconstruct arXiv URL: use `externalIds.ArXiv` value and build `https://arxiv.org/abs/{id}`. |
| Abstract | `arxiv_paper.summary` | `abstract` | `string` | Equivalent content. arXiv may have `\n` line breaks; S2 abstract may differ slightly in whitespace. |
| PDF URL | `arxiv_paper.pdf_url` | `openAccessPdf.url` | `string` or empty | S2's `openAccessPdf.url` may be empty string even for arXiv papers. Safer to construct from `externalIds.ArXiv`: `https://arxiv.org/pdf/{id}`. |
| Primary category | `arxiv_paper.primary_category` | `fieldsOfStudy` | `array[string]` | arXiv uses specific taxonomy (e.g. `cs.LG`). S2 uses broader fields (e.g. `"Computer Science"`). Not a 1:1 mapping. |
| arXiv categories | `arxiv_paper.categories` | `s2FieldsOfStudy` | `array[object]` | Different taxonomy entirely |
| DOI | `arxiv_paper.doi` | `externalIds.DOI` | `string` | Equivalent when present |

### New Fields Available from S2 (not in arXiv)

| S2 Field | Description | Useful for |
|----------|-------------|------------|
| `tldr` | AI-generated one-sentence summary | Quick paper overview |
| `citationCount` | Total citations | Impact assessment |
| `influentialCitationCount` | Influential citations | Impact assessment |
| `venue` | Publication venue | Metadata |
| `publicationVenue` | Structured venue info (name, type, URL) | Rich metadata |
| `publicationTypes` | `["JournalArticle", "Conference"]` | Filtering |
| `fieldsOfStudy` | `["Computer Science"]` | Categorization |
| `references` | List of referenced papers | Graph navigation |
| `citations` | List of citing papers | Graph navigation |

---

## 4. The `publicationDate` Question

### Summary

**`publicationDate` IS available as a requestable field from the S2 API.** It returns a date string in `YYYY-MM-DD` format.

### Evidence (live API calls)

| Paper | `year` | `publicationDate` |
|-------|--------|-------------------|
| WavTokenizer (ArXiv:2408.16532) | 2024 | `"2024-08-29"` |
| Attention Is All You Need (ArXiv:1706.03762) | 2017 | `"2017-06-12"` |
| Multimodal ML Survey (CorpusId:10137425) | 2017 | `"2017-05-26"` |
| S2 Literature Graph (649def34...) | 2018 | `"2018-05-06"` |
| Techniques for Measuring Sea Turtles (MAG:112218234) | 1999 | **`null`** |

### Key Findings

1. **Format:** `YYYY-MM-DD` string (date only, no time component, no timezone)
2. **Can be `null`:** Yes, confirmed for older/obscure papers. The `year` field (integer) is generally more reliably present.
3. **Precision loss vs arXiv:** arXiv's `published` field gives full datetime with timezone (e.g. `2024-08-29 13:43:36+00:00`). S2's `publicationDate` gives only the date (`2024-08-29`). The time-of-day component is lost.

### Impact on Migration

The current arxivbot uses `arxiv_paper.published` (a Python `datetime`) in two ways:

1. **YAML frontmatter:** `arxiv_paper.published.isoformat()` -- produces `"2024-08-29T13:43:36+00:00"`. S2 would produce `"2024-08-29"` (less precise).
2. **Pretty-printed date:** `inflect_day(published.day) + published.strftime(" %B %Y (%A) @ %H:%M:%S")` -- produces something like `"29th August 2024 (Thursday) @ 13:43:36"`. S2 can provide the date portion but NOT the time. The day-of-week can be computed from the date string.
3. **Notion importer:** `arxiv_paper.published.isoformat()` for the `Published` date property.

**Recommendation:** When the source is arXiv and full datetime precision is needed, a fallback to the arXiv API may be warranted. For most use cases, `YYYY-MM-DD` is sufficient. Always check for `null` and fall back to `year` if needed.

---

## 5. Python Client Libraries

### 5.1 `danielnsilva/semanticscholar` (Unofficial)

| Property | Value |
|----------|-------|
| PyPI name | `semanticscholar` |
| Latest version | 0.11.0 |
| Last release | 2025-09-14 |
| Python support | 3.9 - 3.13 |
| License | MIT |
| GitHub stars | ~435 |
| Status | Beta (active development) |

**Key features:**
- API key support: `SemanticScholar(api_key='...')`
- Single paper lookup: `sch.get_paper('DOI:10.xxxx/yyyy')` or `sch.get_paper('ARXIV:2408.16532')`
- Batch lookups: `sch.get_papers(['id1', 'id2', ...])` (up to 1,000 IDs)
- Paper search: `sch.search_paper('query', year='2020-2023', limit=50)`
- Bulk search: `sch.search_paper(query='...', bulk=True, sort='citationCount:desc')`
- Title match: `sch.search_paper(query='...', match_title=True)`
- Author lookup: `sch.get_author(author_id)`
- Automatic retry on 429: up to 10 retries with 30-second waits (enabled by default, configurable)
- Timeout: configurable (default 30s)
- Typed response objects (e.g. `Paper`, `Author`, `Tldr`)
- Pagination support with `.next_page()`
- Async support

**Usage example:**
```python
from semanticscholar import SemanticScholar

sch = SemanticScholar(api_key='YOUR_KEY')  # or omit for unauthenticated
paper = sch.get_paper('ARXIV:2408.16532')
print(paper.title)
print(paper.publicationDate)
print(paper.tldr)
print(paper.authors)
```

### 5.2 Official Client

There is **no official Semantic Scholar Python client**. The `danielnsilva/semanticscholar` package is the most widely used unofficial wrapper.

Allen AI provides example code in https://github.com/allenai/s2-folks/tree/main/examples but these are standalone scripts using `requests`, not a maintained client library.

### 5.3 Recommendation: Wrapper vs Raw HTTP

| Approach | Pros | Cons |
|----------|------|------|
| `danielnsilva/semanticscholar` | Built-in retry/rate-limit handling, typed objects, batch support, well-maintained | Extra dependency, Beta status, abstracts away API details |
| Raw `requests`/`httpx` | Full control, no extra dependency, transparent | Must implement retry logic, rate limiting, response parsing manually |

**Recommendation:** Use `danielnsilva/semanticscholar` for initial implementation. It handles the most painful part (rate limiting with retries) out of the box. The API surface is simple enough that switching to raw HTTP later would be straightforward if needed. The package is actively maintained (last release Sep 2025) and covers all endpoints we need.

If using raw HTTP, prefer `httpx` over `requests` for async support and HTTP/2.

---

## 6. Rate Limiting Best Practices

### 6.1 General Strategy

1. **Always use an API key.** Even the introductory 1 RPS is better than the shared unauthenticated pool, which is congested and unpredictable.

2. **Implement exponential backoff with jitter.** S2 explicitly "require[s] the use of exponential backoff strategies for API requests" (per release notes). Since no `Retry-After` header is provided, implement client-side backoff:
   ```
   delay = min(base_delay * 2^attempt + random_jitter, max_delay)
   ```
   Suggested: base_delay=1s, max_delay=60s, max_retries=5-10.

3. **Use batch endpoints** when looking up multiple papers. One POST to `/paper/batch` with 500 IDs uses 1 request instead of 500.

4. **Request only needed fields.** The `fields` parameter reduces response size and potentially improves performance. Never request `references` or `citations` unless actually needed (they can be very large).

5. **Respect the 1 RPS limit.** For sequential requests, add a 1-second delay between calls. For the `danielnsilva/semanticscholar` library, the built-in retry mechanism handles this.

### 6.2 The `danielnsilva/semanticscholar` Library's Built-in Handling

The library automatically:
- Retries on HTTP 429 up to 10 times
- Waits 30 seconds between retries
- Can be disabled: `SemanticScholar(retry=False)`
- Timeout is configurable: `SemanticScholar(timeout=5)`

### 6.3 Practical Limits for arxivbot

For arxivbot's typical usage (looking up 1-10 papers at a time):
- **Single paper:** 1 request, trivial
- **Multiple papers:** Use batch endpoint (1 request for up to 500 papers)
- **Rate limiting is unlikely to be an issue** for this use case, but the retry logic should be in place for robustness

---

## 7. Uncertainties and Open Questions

1. **`publicationDate` null frequency:** Confirmed that `publicationDate` can be `null` for some papers (especially older ones not from major preprint servers). For arXiv papers specifically, it appears to be reliably present based on testing, but this is not guaranteed for all papers in the S2 corpus.

2. **`openAccessPdf` reliability for arXiv papers:** In testing, the `openAccessPdf.url` field was sometimes an empty string even for papers that are clearly on arXiv (e.g., WavTokenizer had `"url": ""`). For arXiv papers, it is safer to construct the PDF URL from `externalIds.ArXiv` directly: `https://arxiv.org/pdf/{arxiv_id}`.

3. **`tldr` availability:** Not all papers have a TLDR. The field may be `null` for papers that S2's model hasn't processed. For popular/recent CS papers it is generally available.

4. **Springer abstract licensing:** Per the Nov 2024 release notes, "Springer Nature abstracts are not available via the API" due to licensing. This affects papers published by Springer/Nature journals.

5. **Author name ordering:** S2 preserves author order, but the name format may differ slightly from arXiv (e.g., middle names, diacritics). The `name` field is a single string, not structured into first/last.

6. **Version information:** S2 does NOT provide arXiv version numbers. The `externalIds.ArXiv` value is the base ID (e.g., `"2408.16532"`) without version suffix. If version-specific linking is needed (e.g., `v3`), the arXiv API must be consulted.

---

## Appendix A: Example curl Commands

### Single paper lookup (all useful fields)
```bash
curl "https://api.semanticscholar.org/graph/v1/paper/ARXIV:2408.16532?fields=paperId,title,abstract,authors,year,publicationDate,venue,externalIds,url,openAccessPdf,tldr,fieldsOfStudy,citationCount,influentialCitationCount,referenceCount,isOpenAccess,publicationVenue,publicationTypes,journal"
```

### Batch lookup
```bash
curl -X POST "https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,publicationDate,externalIds,abstract,authors,tldr" \
  -H "Content-Type: application/json" \
  -d '{"ids":["ARXIV:2408.16532","ARXIV:1706.03762"]}'
```

### Keyword search
```bash
curl "https://api.semanticscholar.org/graph/v1/paper/search?query=wavtokenizer+acoustic+codec&fields=title,publicationDate,externalIds&limit=3"
```

### With API key
```bash
curl -H "x-api-key: YOUR_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/ARXIV:2408.16532?fields=title,tldr"
```

## Appendix B: Full Live API Response Example

Paper: WavTokenizer (ARXIV:2408.16532), all fields requested:

```json
{
    "paperId": "ebdbded60f48131ed7ba73807c3c086993a96f89",
    "externalIds": {
        "DBLP": "conf/iclr/Ji00C0Z0C0LZY0J25",
        "ArXiv": "2408.16532",
        "DOI": "10.48550/arXiv.2408.16532",
        "CorpusId": 272146429
    },
    "publicationVenue": {
        "id": "939c6e1d-0d17-4d6e-8a82-66d960df0e40",
        "name": "International Conference on Learning Representations",
        "type": "conference",
        "alternate_names": ["Int Conf Learn Represent", "ICLR"],
        "url": "https://iclr.cc/"
    },
    "url": "https://www.semanticscholar.org/paper/ebdbded60f48131ed7ba73807c3c086993a96f89",
    "title": "WavTokenizer: an Efficient Acoustic Discrete Codec Tokenizer for Audio Language Modeling",
    "venue": "International Conference on Learning Representations",
    "year": 2024,
    "referenceCount": 85,
    "citationCount": 141,
    "influentialCitationCount": 21,
    "isOpenAccess": false,
    "openAccessPdf": {
        "url": "",
        "status": null,
        "license": null,
        "disclaimer": "Notice: Paper or abstract available at https://arxiv.org/abs/2408.16532..."
    },
    "fieldsOfStudy": ["Computer Science", "Engineering"],
    "tldr": {
        "model": "tldr@v2.0.0",
        "text": "WavTokenizer achieves state-of-the-art reconstruction quality with outstanding UTMOS scores and inherently contains richer semantic information by designing a broader VQ space, extended contextual windows, and improved attention networks, as well as introducing a powerful multi-scale discriminator and an inverse Fourier transform structure."
    },
    "publicationTypes": ["JournalArticle"],
    "publicationDate": "2024-08-29",
    "journal": {
        "name": "ArXiv",
        "volume": "abs/2408.16532"
    },
    "authors": [
        {"authorId": "72890649", "name": "Shengpeng Ji"},
        {"authorId": "2112347676", "name": "Ziyue Jiang"},
        {"authorId": "2191618494", "name": "Xize Cheng"},
        {"authorId": "2318012880", "name": "Yifu Chen"},
        {"authorId": "2234355048", "name": "Minghui Fang"},
        {"authorId": "2199136449", "name": "Jialong Zuo"},
        {"authorId": "2312341123", "name": "Qian Yang"},
        {"authorId": "2181010470", "name": "Ruiqi Li"},
        {"authorId": "2116461847", "name": "Ziang Zhang"},
        {"authorId": "2308224151", "name": "Xiaoda Yang"},
        {"authorId": "2048021099", "name": "Rongjie Huang"},
        {"authorId": "2317908181", "name": "Yidi Jiang"},
        {"authorId": "2257010473", "name": "Qian Chen"},
        {"authorId": "2307567397", "name": "Siqi Zheng"},
        {"authorId": "2144329841", "name": "Wen Wang"},
        {"authorId": "2304453961", "name": "Zhou Zhao"}
    ],
    "abstract": "Language models have been effectively applied to modeling natural signals..."
}
```

## Appendix C: Comparison of arXiv vs S2 for Same Paper

Paper: WavTokenizer (2408.16532)

| Property | arXiv Python package | S2 API |
|----------|---------------------|--------|
| Title | `"WavTokenizer: an Efficient Acoustic Discrete Codec Tokenizer for Audio Language Modeling"` | `"WavTokenizer: an Efficient Acoustic Discrete Codec Tokenizer for Audio Language Modeling"` |
| First 3 authors | `['Shengpeng Ji', 'Ziyue Jiang', 'Wen Wang']` (from `[:3]` slice of Atom feed) | `['Shengpeng Ji', 'Ziyue Jiang', 'Xize Cheng']` |
| Author count | 16 | 16 |
| Published | `2024-08-29 13:43:36+00:00` (datetime) | `"2024-08-29"` (date string) |
| Year | (derived: 2024) | `2024` (integer) |
| Link | `http://arxiv.org/abs/2408.16532v3` | `https://www.semanticscholar.org/paper/ebdbd...` |
| arXiv ID | (derived: `2408.16532`) | `externalIds.ArXiv`: `"2408.16532"` |
| Abstract | Full text with \n | Full text |
| PDF URL | `https://arxiv.org/pdf/2408.16532v3` | `openAccessPdf.url`: `""` (empty!) |
| Categories | `['eess.AS', 'cs.LG', 'cs.MM', 'cs.SD', 'eess.SP']` | `fieldsOfStudy`: `['Computer Science', 'Engineering']` |
| Version | v3 (in URL) | Not available |
| TLDR | Not available | Available |
| Citations | Not available | 141 |
| Venue | Not available (only `comment: "Accepted by ICLR 2025"`) | `"International Conference on Learning Representations"` |

**Notable discrepancy in author ordering:** The third author differs between arXiv (`Wen Wang`) and S2 (`Xize Cheng`). The arXiv Python package orders authors as listed in the Atom feed, which may differ from the order on the actual arXiv abstract page or in the paper PDF. S2 appears to follow the canonical author order from the paper itself. Both APIs list 16 total authors. This discrepancy is worth noting but is unlikely to affect arxivbot significantly -- both sources provide the complete author set.
