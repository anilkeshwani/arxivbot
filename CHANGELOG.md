# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/). Versions before 0.5.0 were tagged without a changelog.

## [Unreleased]

### Changed

- Whether a paper is already in the vault is read from the frontmatter of the notes in `Papers/` (`s2_paper_id`, `arxiv_id` or `link`, `doi`), instead of from `.papers.db`. Notes imported before the database existed are now recognized, and nothing is left for two machines importing into the same vault to conflict over in git.
- What each note's frontmatter says is cached in `$XDG_CACHE_HOME/arxivbot/` (default `~/.cache/arxivbot/`), outside the vault, and a note is read again only when the file changes (its modification time, change time, size or inode). A run is then about as fast as a database lookup.
- The Telegram bot no longer commits `.papers.db`.

### Removed

- The SQLite database `.papers.db` and the `OBSIDIAN_DB_PATH` environment variable. Remove the file from the vault with `git rm --cached .papers.db` and add it to `.gitignore`, or delete it.

## [0.8.0] - 2026-11-04

### Added

- A clip queue for pages the Telegram bot cannot get: refused by the site (401, 403, 429 and similar), failing (5xx), timing out or showing no content. ([#16](https://github.com/anilkeshwani/arxivbot/pull/16))
  - The page is first clipped from a Wayback Machine snapshot taken the same day, in local time, if there is one. A snapshot from another day is never used. `obsidian-clip` does the same.
  - Otherwise it is queued: listed in a message pinned in the channel and in `Clip Queue.md` in the vault, kept in `.clip-queue.json`.
  - A queued page leaves the queue once a clipping with its link as `source` reaches the vault, from the Web Clipper or a file sent to the bot. The bot pulls the vault hourly, and before each post and `/pending`, while the queue has pages.
  - `/pending` lists the queue and `/done <number or link>` drops a page.
  - `OBSIDIAN_CLIP_QUEUE_PATH` and `OBSIDIAN_CLIP_QUEUE_NOTE` environment variables.

### Changed

- `arxivbot-telegram-setup` asks for the right to edit messages as well as post them, which the bot needs to pin the clip queue. ([#16](https://github.com/anilkeshwani/arxivbot/pull/16))

### Fixed

- The bot token no longer appears in the bot's log. Telegram API URLs carry it, and tracebacks and connection errors printed them in full. ([#16](https://github.com/anilkeshwani/arxivbot/pull/16))
- A Telegram server error (5xx) while polling is logged as a one-line warning instead of an error with a traceback. ([#16](https://github.com/anilkeshwani/arxivbot/pull/16))

## [0.7.0] - 2026-10-27

### Added

- Clipping pages the server cannot load, such as paywalled articles, gift links and sites behind bot checks, from what your browser loaded. ([#15](https://github.com/anilkeshwani/arxivbot/pull/15))
  - The Telegram bot accepts a `.html` page saved from the browser or a `.md` note saved from the Obsidian Web Clipper, posted as a file. A link in the caption is the page's URL when the page names none.
  - `obsidian-clip` accepts the same files, with `--url` for a saved page without a canonical URL.
  - A saved page's source is its canonical URL, and its relative links and images resolve against it. A Web Clipper note is saved unchanged. Either is skipped when its source is already clipped.

## [0.6.0] - 2026-10-26

### Added

- `arxivbot-telegram-setup`: checks the bot token, prints a link that adds the bot to a channel as an admin, finds the channel's chat ID from a test post and writes `~/.config/arxivbot/credentials.env` with private permissions. With `--service` it also writes a systemd user service whose `PATH` points at the programs the bot runs, and offers to enable it. ([#14](https://github.com/anilkeshwani/arxivbot/pull/14))
- `docs/telegram-bot-setup.md`: the full setup guide, with the manual alternative and troubleshooting. ([#14](https://github.com/anilkeshwani/arxivbot/pull/14))

### Removed

- `deploy/arxivbot-telegram.service`, whose host-specific paths needed editing by hand. `arxivbot-telegram-setup --service` generates the unit for the host it runs on. ([#14](https://github.com/anilkeshwani/arxivbot/pull/14))

## [0.5.3] - 2026-10-24

### Changed

- An X post is clipped under `https://x.com/<handle>/status/<id>`, so `twitter.com`, `mobile.x.com` and share-suffix links such as `?s=20` match the same note instead of creating duplicates. ([#13](https://github.com/anilkeshwani/arxivbot/pull/13))
- An X post's clipping is titled `@handle on X: <opening words>` instead of Defuddle's `Post by @handle on X`, so notes for different posts by the same person get distinct names. ([#13](https://github.com/anilkeshwani/arxivbot/pull/13))

### Fixed

- The clipper's YAML-unsafe character pattern spells U+2028 and U+2029 as escapes instead of holding the invisible characters in the source. ([#13](https://github.com/anilkeshwani/arxivbot/pull/13))

## [0.5.2] - 2026-10-24

### Changed

- The Telegram bot's Claude analysis follows the vault's paper summary format: an H2 title naming the paper's main claim and model, a `> [!info] #llm-generated/<model ID>` callout with date and source, then its six sections as H3. It also asks for results tables with ↑/↓ arrows, bolded key findings and `[[wikilinks]]` to papers already in `Papers/`. ([#12](https://github.com/anilkeshwani/arxivbot/pull/12))
- A note that already carries an `#llm-generated/` summary, such as one written by hand, is not analyzed again. ([#12](https://github.com/anilkeshwani/arxivbot/pull/12))

## [0.5.1] - 2026-10-24

### Fixed

- `obsidian-clip` and the Telegram bot fetch pages with a browser User-Agent, so sites such as Medium that refuse Defuddle's default no longer fail with 403. Sites behind bot protection such as PerimeterX still do. ([#11](https://github.com/anilkeshwani/arxivbot/pull/11))
- The Telegram bot logs a failed clip as one line instead of a traceback. ([#11](https://github.com/anilkeshwani/arxivbot/pull/11))

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

[0.7.0]: https://github.com/anilkeshwani/arxivbot/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/anilkeshwani/arxivbot/compare/v0.5.3...v0.6.0
[0.5.3]: https://github.com/anilkeshwani/arxivbot/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/anilkeshwani/arxivbot/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/anilkeshwani/arxivbot/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/anilkeshwani/arxivbot/compare/v0.4.1...v0.5.0
