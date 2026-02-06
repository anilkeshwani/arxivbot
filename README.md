# arxivbot

A minimal arXiv clipper for importing academic papers into [Notion](https://www.notion.so/) and [Obsidian](https://obsidian.md/).

## Installation

Requires Python >= 3.11.

```bash
pip install -e .
```

## Usage

### Import to Notion

```bash
notion-import 2301.12345 2302.00001
# or via module
python -m arxivbot.notion_importer 2301.12345 --add_topic_tag --add_arxiv_type
```

Options:
- `--no_abstract`: skip writing the abstract to the Notion page
- `--add_topic_tag`: add the arXiv primary category as a tag
- `--add_arxiv_type`: add "arXiv" as the entry type
- `--max_results N`: limit number of results returned per ID

### Import to Obsidian

```bash
obsidian-import 2301.12345 2302.00001
# or via module
python -m arxivbot.obsidian_importer 2301.12345
```

Options:
- `--no_pdf`: skip downloading the PDF
- `--max_results N`: limit number of results returned per ID

### Find arXiv links in files

```bash
python -m arxivbot.find_arxiv_links <directory> <file_extension>
```

### Convert PDF index TSV to SQLite

```bash
python scripts/tsv2sqlite.py <tsv_file> <db_file> [--table_name <name>]
```

## Configuration

### Credentials

Copy `credentials_template.env` to `credentials.env` in the project root and fill in your tokens:

```
NOTION_TOKEN="your_notion_integration_token"
IEEE_API_KEY="your_ieee_api_key"
```

Copy `template.env` to `.env` and set your Notion database ID:

```
READING_LIST_DATABASE_ID="your_database_id"
```

### Environment variables

| Variable | Description | Default |
|---|---|---|
| `OBSIDIAN_VAULT_DIR` | Path to your Obsidian vault | `~/Desktop/journal/` |
| `NOTION_TOKEN` | Notion integration token (loaded from `credentials.env`) | - |
| `READING_LIST_DATABASE_ID` | Notion database ID (loaded from `.env`) | - |

## Testing

```bash
pytest
```

## Feature Requests

- [ ] Provide cleaner abstracts
  - [ ] Parse URLs and hyperlink them
  - [ ] Parse LaTeX and render it as an equation
- [ ] Telegram integration via GitHub Actions
- [x] Write abstract to entries as text
- [x] Add check for duplicate entries before adding to database
- [ ] arXiv papers as EPUBs on Kindle
    - https://tex.stackexchange.com/questions/1551/use-latex-to-produce-epub
    - https://www.reddit.com/r/MachineLearning/comments/5xtnl4/d_reading_arxiv_preprints_on_an_ereader/
- [ ] Semantic Scholar API integration (see below)
- [ ] OpenReview support

## Semantic Scholar Resources

Move the arxivbot onto the [Semantic Scholar (S2) Academic Graph API](https://api.semanticscholar.org/api-docs/graph).

Motivations:
- More general: aggregates data from a wide array of sources (arXiv, ACL, Nature, etc.)
- Easily queryable by extracting S2 paper SHA from URL

Resources:
- [S2 API Tutorial](https://www.semanticscholar.org/product/api/tutorial)
- [Get Open Access PDFs](https://github.com/allenai/s2-folks/tree/3c786b3f0727cca5049afd5654494acd99b80efb/examples/python/get_open_access_pdf)
- [Get details about a paper - Academic Graph API](https://api.semanticscholar.org/api-docs/#tag/Paper-Data/operation/get_graph_get_paper)
- [API usage examples](https://github.com/allenai/s2-folks/tree/3c786b3f0727cca5049afd5654494acd99b80efb/examples) and [Python examples](https://github.com/allenai/s2-folks/tree/3c786b3f0727cca5049afd5654494acd99b80efb/examples/python)
- Unofficial Python wrapper: [danielnsilva/semanticscholar](https://github.com/danielnsilva/semanticscholar)

### Example S2 Academic Graph API queries

```
https://api.semanticscholar.org/graph/v1/paper/ebdbded60f48131ed7ba73807c3c086993a96f89?fields=url,year,authors,externalIds,abstract,venue,references,influentialCitationCount,fieldsOfStudy
```

[Example response](/example_s2_academic_api_response.json)

![S2 Academic Graph - Details about a paper - Sample Response - 200 OK](/S2%20Academic%20Graph%20-%20Details%20about%20a%20paper%20-%20Sample%20Response%20-%20200%20OK.png)

## Resources

- arxiv Python library
  - http://lukasschwab.me/arxiv.py/index.html
  - [Result](http://lukasschwab.me/arxiv.py/index.html#Result)
  - [Search](http://lukasschwab.me/arxiv.py/index.html#Search)
- arXiv API
  - https://info.arxiv.org/help/api/basics.html#quickstart
  - https://info.arxiv.org/help/api/user-manual.html#sort
- Notion API
  - https://www.notion.so/my-integrations
  - [Create a page](https://developers.notion.com/reference/post-page)
  - [Update a page](https://developers.notion.com/reference/patch-page)
  - [Property object](https://developers.notion.com/reference/property-object)
- Similar projects
  - https://github.com/wangjksjtu/arxiv2notionplus

## Directory structure

```
.
├── arxivbot/
│   ├── __init__.py
│   ├── constants.py
│   ├── find_arxiv_links.py
│   ├── ieee_api.py
│   ├── ieee_scrape.py
│   ├── migrate_notion_obsidian.py
│   ├── notion_importer.py
│   ├── obsidian_importer.py
│   └── utils.py
├── scripts/
│   └── tsv2sqlite.py
├── tests/
│   ├── example_inputs/
│   │   └── ieee/
│   │       └── 9381661.html
│   ├── test_find_arxiv_links.py
│   ├── test_ieee_scrape.py
│   ├── test_tsv2sqlite.py
│   └── test_utils.py
├── _notion-sdk-py-examples/
│   ├── README.md
│   ├── assets/
│   ├── authenication.py
│   ├── db_read.py
│   ├── db_write.py
│   ├── page_read.py
│   └── page_write.py
├── docs/
├── credentials_template.env
├── template.env
├── pyproject.toml
├── requirements.txt
├── LICENSE
└── README.md
```
