# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/). Versions before 0.5.0 were tagged without a changelog.

## [0.5.0] - 2026-10-24

### Added

- `obsidian-clip`: saves web pages to `Clippings/` with the Obsidian Web Clipper's default frontmatter, extracted with the [Defuddle](https://github.com/kepano/defuddle) CLI (`npm install -g defuddle`). A URL already clipped is skipped. ([#10](https://github.com/anilkeshwani/arxivbot/pull/10))
- `arxivbot-telegram`: a Telegram bot that imports posted papers with `obsidian-import`, optionally analyzes them with Claude Code, and commits and pushes the vault.
  - Handles posts in a channel as well as direct messages, and clips any link that is not a paper. A paper link that cannot be found is clipped instead. ([#10](https://github.com/anilkeshwani/arxivbot/pull/10))
  - Each paper or page is its own commit containing only the files it wrote, and is committed even if it fails partway. ([#10](https://github.com/anilkeshwani/arxivbot/pull/10))
  - `ARXIVBOT_TELEGRAM_ANALYZE=0` turns off the Claude analysis (and the PDF download). ([#10](https://github.com/anilkeshwani/arxivbot/pull/10))
  - `deploy/arxivbot-telegram.service` runs the bot as a systemd user service. ([#10](https://github.com/anilkeshwani/arxivbot/pull/10))
- `OBSIDIAN_CLIPPINGS_DIR` environment variable. ([#10](https://github.com/anilkeshwani/arxivbot/pull/10))
- arXiv API fallback for papers Semantic Scholar does not find.
- `summary` frontmatter field.
- `arxivbot.identifiers`: one standard-library-only module for parsing arXiv IDs, DOIs and Semantic Scholar IDs and for deduplicating papers ([#9](https://github.com/anilkeshwani/arxivbot/pull/9)). arXiv DOIs, `doi.org` URLs and `DOI: ` with a space are recognized.
- Vault, papers, PDFs and database paths are configurable with environment variables.

### Changed

- Paper metadata comes from the Semantic Scholar Academic Graph API, fetched in batches, instead of the arXiv API. Papers already in the local SQLite database are skipped without calling the API, and existing notes gain new frontmatter fields without losing their own.
- The `semanticscholar` client library is replaced by direct requests with retries for rate limits, server errors and timeouts ([#9](https://github.com/anilkeshwani/arxivbot/pull/9)).
- `obsidian-import` creates `Papers/` and `PDFs/` but not the vault itself, and exits with an error when the vault path is wrong.
- Import log messages show both the input and the resolved paper title.

### Fixed

- Database connections are closed, so other processes' writes reach `.papers.db` instead of staying in the WAL file. ([#10](https://github.com/anilkeshwani/arxivbot/pull/10))
- A failed note write no longer leaves a database row that made later runs skip the paper.
- DOI cleanup no longer truncates DOIs that end in a balanced bracket, and legacy SICI DOIs are extracted whole.
- Bare DOIs that contain an arXiv-like run of digits parse as DOIs.
- Frontmatter strings are never wrapped across lines, and notes containing `---` in values or body text are parsed correctly.
- `find_arxiv_links` matches 4-digit arXiv IDs.

[0.5.0]: https://github.com/anilkeshwani/arxivbot/compare/v0.4.1...v0.5.0
