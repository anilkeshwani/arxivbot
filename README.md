# arxivbot

A minimal paper clipper for Obsidian, powered by Semantic Scholar.

## Installation

Install as a tool (recommended for general use):

```bash
uv tool install git+https://github.com/anilkeshwani/arxivbot
```

Or into a project environment:

```bash
uv pip install .
# or
pip install .
```

## Configuration

### API key

Set `S2_API_KEY` in your environment, or copy `credentials_template.env` to `credentials.env` in the directory where you run `obsidian-import`:

```bash
cp credentials_template.env credentials.env
```

```
S2_API_KEY="your_key_here"
```

An S2 API key is optional — unauthenticated requests work but share a rate-limited pool. Request a key at https://www.semanticscholar.org/product/api#api-key-form.

### Environment variables

All paths can be overridden via environment variables (defaults shown):

| Variable | Default | Description |
|---|---|---|
| `OBSIDIAN_VAULT_DIR` | `~/Desktop/journal/` | Root of your Obsidian vault |
| `OBSIDIAN_PAPERS_DIR` | `$OBSIDIAN_VAULT_DIR/Papers` | Directory for paper notes |
| `OBSIDIAN_PDFS_DIR` | `$OBSIDIAN_VAULT_DIR/PDFs` | Directory for downloaded PDFs |
| `OBSIDIAN_DB_PATH` | `$OBSIDIAN_VAULT_DIR/.papers.db` | SQLite database path |
| `S2_API_KEY` | _(none)_ | Semantic Scholar API key |

## Usage

```
obsidian-import <id> [<id> ...] [--no_pdf] [--force]
```

### Arguments

| Argument | Description |
|---|---|
| `id` | One or more paper identifiers: arXiv IDs, arXiv URLs, S2 paper IDs, S2 URLs, or DOIs |
| `--no_pdf` | Skip PDF download |
| `--force` | Re-fetch papers already present in the local database |

### Examples

```bash
# Import by arXiv ID
obsidian-import 2408.16532

# Import by arXiv URL
obsidian-import https://arxiv.org/abs/1706.03762

# Import by Semantic Scholar URL
obsidian-import https://www.semanticscholar.org/paper/ebdbded60f48131ed7ba73807c3c086993a96f89

# Import by DOI
obsidian-import DOI:10.18653/v1/N18-3011

# Import multiple papers, skip PDF download
obsidian-import 2408.16532 1706.03762 --no_pdf

# Re-fetch a paper that's already in the database
obsidian-import 2408.16532 --force
```

## Clipping web pages

`obsidian-clip` saves a page to `Clippings/` with the same frontmatter as the Obsidian Web Clipper's default template (`title`, `source`, `author`, `published`, `created`, `description`, `tags: clippings`). Extraction uses [Defuddle](https://github.com/kepano/defuddle), the library behind the Web Clipper, through its CLI:

```bash
npm install -g defuddle   # replaces the deprecated defuddle-cli package
obsidian-clip https://example.com/some-article [<url> ...]
```

Re-clipping a URL that is already in `Clippings/` is a no-op. Pages that need JavaScript or a login to render usually yield no content and fail, as they would in the Web Clipper.

| Variable | Default | Description |
|---|---|---|
| `OBSIDIAN_CLIPPINGS_DIR` | `$OBSIDIAN_VAULT_DIR/Clippings` | Directory for clipped pages |
| `DEFUDDLE_BIN` | `defuddle` | Defuddle CLI to run (set an absolute path when `PATH` lacks it, e.g. under systemd) |

## Telegram bot

`arxivbot-telegram` watches a Telegram chat or channel. Every link or identifier posted is routed:

- **Papers** (arXiv URLs and IDs, DOIs and publisher links containing one, Semantic Scholar URLs, Hugging Face and alphaXiv paper pages) are imported with `obsidian-import`.
- **Any other link** is clipped with `obsidian-clip`.

Each paper or page is committed to the vault as its own commit, staging only the files that item created, then pushed once per post. By default each imported paper is also analyzed with `claude -p` and the analysis appended to its note; set `ARXIVBOT_TELEGRAM_ANALYZE=0` to only import (PDFs are then not downloaded either).

### Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) (`/newbot`) and copy its token.
2. Create a private channel and add the bot as an administrator with permission to post messages.
3. Post anything in the channel, then find its chat ID (it starts with `-100`) from `https://api.telegram.org/bot<TOKEN>/getUpdates` under `channel_post.chat.id`. Do this before starting the bot, which consumes updates.
4. Write the credentials file:

   ```bash
   mkdir -p ~/.config/arxivbot && chmod 700 ~/.config/arxivbot
   cat > ~/.config/arxivbot/credentials.env <<'EOF'
   ARXIVBOT_TELEGRAM_BOT_TOKEN="123456:ABC..."
   ARXIVBOT_TELEGRAM_ALLOWED_CHAT_IDS="-1001234567890"
   EOF
   chmod 600 ~/.config/arxivbot/credentials.env
   ```

   `ARXIVBOT_TELEGRAM_ALLOWED_CHAT_IDS` is comma-separated, so a direct chat with the bot can be allowed alongside the channel. Posts from any other chat are ignored.

5. Run it on a machine with a checkout of the vault that can `git push`, either directly (`arxivbot-telegram`) or as a systemd user service:

   ```bash
   cp deploy/arxivbot-telegram.service ~/.config/systemd/user/
   # edit OBSIDIAN_VAULT_DIR, DEFUDDLE_BIN and PATH in the unit to match the host
   systemctl --user daemon-reload
   systemctl --user enable --now arxivbot-telegram
   loginctl enable-linger "$USER"   # keep it running while logged out
   journalctl --user -u arxivbot-telegram -f
   ```

The bot replies to each post with a status line per item, and `/help` lists what it recognizes.

## Directory structure

```
.
├── README.md
├── arxivbot/
│   ├── __init__.py
│   ├── arxiv_api.py
│   ├── constants.py
│   ├── database.py
│   ├── find_arxiv_links.py
│   ├── identifiers.py
│   ├── obsidian_importer.py
│   ├── s2_api.py
│   ├── telegram_bot.py
│   ├── web_clipper.py
│   └── utils.py
├── credentials_template.env
├── deploy/
│   └── arxivbot-telegram.service
├── plans/
│   ├── additional_features.md
│   ├── ai_summary_generation.md
│   ├── feature_requests.md
│   ├── resources.md
│   └── s2_api_migration_reference.md
├── pyproject.toml
├── tests/
└── uv.lock
```

## Development

Install pre-commit hooks:

```bash
pre-commit install
```

Lint and format with [ruff](https://github.com/astral-sh/ruff):

```bash
ruff check --fix .
ruff format .
```

## Resources

See [`plans/resources.md`](plans/resources.md) for a full list of references and related projects.
