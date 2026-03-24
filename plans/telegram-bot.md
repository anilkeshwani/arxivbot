# Telegram Paper Import Bot — Implementation Plan

## Context

A single Python script in the `arxivbot` repo that runs locally on the Mac, long-polls Telegram for paper links, imports them with `obsidian-import`, analyzes them with `claude -p` (covered by Max subscription), extracts key figures to a temp dir, sends the analysis + figures back to Telegram, cleans up, and pushes to git.

**One script. One process. Zero cloud infrastructure.**

## Architecture

```
Telegram message (paper link)
  → Local Python script (long-polling getUpdates)
    1. Parse paper identifiers from message
    2. Reply "Processing..."
    3. Run obsidian-import (direct local filesystem)
    4. Download PDF to temp dir, extract figures with pymupdf
    5. Run claude -p for analysis (Max subscription)
    6. Append analysis to paper markdown (no images in vault)
    7. Reply with analysis text + selected figures
    8. Clean up temp dir (figures deleted)
    9. git commit && git push
```

## Implementation Steps

### Step 1: Make arxivbot paths configurable via env vars — DONE

**File**: `arxivbot/constants.py`

Already modified to read from env vars with current values as defaults. Tested successfully.

### Step 2: Add Telegram bot module to arxivbot — DONE

**File**: `arxivbot/telegram_bot.py` — created

**Entry point** added to `pyproject.toml`:
```toml
[project.scripts]
obsidian-import = "arxivbot.obsidian_importer:main"
arxivbot-telegram = "arxivbot.telegram_bot:main"
```

**Dependency** added to `pyproject.toml`:
```
PyMuPDF>=1.24.0
```

Installed via `uv tool install --force --editable .` — binary at `~/.local/bin/arxivbot-telegram`.

(`requests` and `python-dotenv` are already arxivbot dependencies)

**Core loop** — Telegram long polling (no framework needed, just `requests`):

```python
offset = 0
while True:
    updates = requests.get(
        f"{TELEGRAM_API_BASE}/getUpdates",
        params={"offset": offset, "timeout": 30},
    ).json()
    for update in updates["result"]:
        offset = update["update_id"] + 1
        handle_message(update["message"])
```

Long polling with `timeout=30` blocks waiting for messages, uses minimal resources, responds within seconds.

**handle_message** logic:

1. Validate `chat.id` against `ARXIVBOT_TELEGRAM_ALLOWED_CHAT_IDS`
2. Extract paper identifiers — reuse `arxivbot.utils.parse_paper_id()`
3. Send "Processing..." reply via Telegram `sendMessage`
4. Run `obsidian-import` as subprocess: `obsidian-import <ids>`
   (this creates the markdown note, downloads PDF to `PDFs/`, updates `.papers.db`)
5. **Inside a `tempfile.TemporaryDirectory()` context manager**:
   a. Extract images from PDF with `pymupdf`, filter by size (>200x200px), save into the temp dir
   b. Run `claude -p` with the PDF path + extracted figure paths → analysis + figure selection
   c. Parse `<!-- FIGURES: fig_001.png, fig_003.png -->` from Claude's response
   d. Append analysis text (without the FIGURES comment) to the paper markdown
   e. Send analysis text to Telegram via `sendMessage` (split at 4096 chars if needed)
   f. Send selected figures to Telegram via `sendPhoto`
6. Temp dir auto-cleaned on context manager exit — no images persist on disk
7. `git -C {vault_dir} add Papers/ .papers.db && git commit && git push`

**Figures never touch the Obsidian vault.** They exist only in a `tempfile.TemporaryDirectory()` for the duration of the Telegram send, then are deleted automatically.

**Analysis prompt** — based on the existing literature analysis prompt at `journal/assets/prompts/Paper Summary Prompt.md`, with a figure-selection addendum. Stored as `ANALYSIS_PROMPT` constant:

```
You are a senior ML researcher and technical writer. Your task is to produce a comprehensive, self-contained analysis of the attached research paper. The analysis should be written so that a reader with general ML familiarity — but no prior knowledge of this specific subfield or paper — can fully understand every claim, contribution, and result without needing to read the original.

The paper PDF is at: {pdf_path}

The following figures were extracted from the paper: {figure_paths}

Follow the structure below exactly.

---

### 1. The Headline: What This Paper Actually Does (2–4 sentences)

Open with a crisp, jargon-free statement of what the paper achieves and why it matters. Think of this as the "elevator pitch" — what would you tell a sharp colleague over coffee? Avoid vague phrases like "we propose a novel framework." Be concrete: what input goes in, what comes out, and what changes because of this work?

### 2. Why This Matters: The Problem in Context

Before diving into contributions, set the stage:

- **The task or problem domain.** Define it from first principles. What is the goal? What does the input look like, what does the desired output look like? Give a concrete example if it helps.
- **Why it's hard.** What specific technical barriers, trade-offs, or limitations have made this problem difficult? Be precise — not "previous methods are slow" but *why* they are slow, and what architectural or algorithmic constraint causes it.
- **Where the field stood before this paper.** Briefly describe the dominant approaches (1–3 sentences each). What do they do well? Where do they fall short? Name specific prior works if they are important baselines.
- **The gap this paper targets.** Articulate exactly what unsolved problem or unaddressed limitation this paper goes after. This should flow naturally from the prior-work discussion.

### 3. Key Contributions and Ideas

This is the centrepiece. For each major contribution:

- **State each contribution clearly in one to two sentences.**
- **Explain the core idea or insight.** What is the key observation, hypothesis, or design principle? Why does it work, intuitively? Use analogies or simplified examples where they genuinely clarify — but never at the cost of accuracy.
- **Provide the necessary technical detail.** Define any new terms, components, objectives, or architectural choices. If the contribution involves a new loss function, describe what each term does and why it's there. If it's an architectural change, explain the information flow. The reader should understand the mechanism, not just the label.
- **Contrast with the prior approach.** What did people do before, and how does this differ? Be specific about what is changed and what stays the same.

Present contributions in order of importance, not necessarily the order they appear in the paper.

### 4. Method: Full Technical Breakdown

Walk through the complete method end-to-end:

- **Architecture / pipeline overview.** Describe the full system: its major components, how data flows through them, and how they connect.
- **Training procedure.** What objective(s) are optimised? What data is used, and how is it prepared or augmented?
- **Key design choices.** Highlight non-obvious decisions — things the authors chose to do (or not do) that meaningfully affect the outcome.
- **Notation and formalism.** Where equations are central to understanding, reproduce the key ones and explain every symbol.

### 5. Experiments and Results

For each major experiment or evaluation:

- **Setup.** What datasets, metrics, and baselines are used?
- **Main results.** State the headline numbers and what they mean.
- **Ablations and analysis.** What do the ablation studies reveal about which components matter most?
- **Limitations the authors acknowledge** (or that you observe).

### 6. Connections, Implications, and Open Questions

- **Relationship to concurrent or subsequent work.**
- **Potential extensions or applications.**
- **What remains unsolved.**

---

## Figure Selection

After the analysis, on a separate line, output a comment listing only the figures most relevant to understanding the paper's key contributions and method:
<!-- FIGURES: fig_001.png, fig_003.png -->

## Formatting and Style Guidelines

- Be self-contained. Define every acronym on first use.
- Be concrete over abstract. Prefer specific dimensions, sizes, numbers.
- Be honest about uncertainty. If the paper is vague, say so.
- Use structure aggressively. Bullet points for lists, paragraphs for narrative.
- Target 600–1500 words depending on paper complexity.
- Output Obsidian-compatible markdown.
```

**Config**: reads from `~/.config/arxivbot/credentials.env` (permissions `0600`):

```
ARXIVBOT_TELEGRAM_BOT_TOKEN=<from BotFather>
ARXIVBOT_TELEGRAM_ALLOWED_CHAT_IDS=<comma-separated chat IDs>
```

**Error handling**: if any step fails, send error message to Telegram chat and continue polling.

### Step 3: Create launchd service — PENDING

**File**: `~/Library/LaunchAgents/com.arxivbot.telegram.plist`

Runs `arxivbot-telegram` as a persistent service. launchd restarts it if it crashes.

```xml
<dict>
    <key>Label</key>
    <string>com.arxivbot.telegram</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/anilkeshwani/.local/bin/arxivbot-telegram</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/anilkeshwani/Desktop/journal</string>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/arxivbot-telegram.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/arxivbot-telegram.err</string>
</dict>
```

### Step 4: Setup — IN PROGRESS

1. Create bot via BotFather — **DONE**
2. Get chat ID via `getUpdates` — **DONE**
3. Create credentials directory — **DONE** (`~/.config/arxivbot/` with `0700`)
4. Write credentials file — **WAITING ON USER** (bot token + chat ID)
   ```bash
   nano ~/.config/arxivbot/credentials.env
   ```
   Contents:
   ```
   ARXIVBOT_TELEGRAM_BOT_TOKEN=<from BotFather>
   ARXIVBOT_TELEGRAM_ALLOWED_CHAT_IDS=<your chat ID>
   ```
   Then: `chmod 600 ~/.config/arxivbot/credentials.env`
5. Install arxivbot with new entry point — **DONE** (`~/.local/bin/arxivbot-telegram`)
6. Create launchd plist — **PENDING** (after manual test)
7. `launchctl load` — **PENDING** (after manual test)

## Credential Security

Credentials stored at `~/.config/arxivbot/credentials.env` with:
- File permissions `0600` (owner read/write only)
- Directory permissions `0700` on `~/.config/arxivbot/`
- Loaded via `python-dotenv` (already an arxivbot dependency)
- All env var names prefixed `ARXIVBOT_TELEGRAM_` to avoid collisions with other services

The script validates permissions on startup and warns if the file is world-readable.

## Files to Create/Modify

| File | Action | Status |
|---|---|---|
| `arxivbot/constants.py` | env var overrides | **DONE** |
| `arxivbot/telegram_bot.py` | Create (the bot) | **DONE** |
| `pyproject.toml` | Add entry point + `PyMuPDF` dep | **DONE** |
| `~/.config/arxivbot/credentials.env` | Create (0600) | **WAITING ON USER** |
| `~/Library/LaunchAgents/com.arxivbot.telegram.plist` | Create | PENDING |

## Clean up from previous approach — DONE

Removed from journal repo:
- ~~`.github/workflows/telegram-paper-import.yml`~~
- ~~`scripts/analyze_paper.py`~~
- ~~`worker/` directory~~

## Expected Latency

| Phase | Time |
|---|---|
| Message received (long poll returns) | ~0-1s |
| "Processing..." reply | ~200ms |
| `obsidian-import` (S2 API + markdown + PDF) | ~10-20s |
| Figure extraction (pymupdf, temp dir) | ~2-5s |
| Claude Code analysis | ~30-90s |
| Telegram reply with analysis + figures | ~2s |
| Temp dir cleanup | instant |
| git commit + push | ~5s |
| **Total** | **~1-2 minutes** |

## Remaining Implementation Work

None — all code is written and installed. The bot is ready to run once credentials are configured.

Future refinements (not blockers):
- The `ANALYSIS_PROMPT` constant in `telegram_bot.py` can be tuned after testing real output
- Consider adding `/status` command to check bot health
- Consider adding a `/recent` command to list recently imported papers

## What You Need To Do

1. **Write credentials** to `~/.config/arxivbot/credentials.env`:
   ```
   ARXIVBOT_TELEGRAM_BOT_TOKEN=<your token from BotFather>
   ARXIVBOT_TELEGRAM_ALLOWED_CHAT_IDS=<your chat ID>
   ```
   Then: `chmod 600 ~/.config/arxivbot/credentials.env`

2. **Test manually**: run `arxivbot-telegram` in a terminal and send a paper link to your bot

3. **After successful test**: I will create the launchd plist and load it so the bot runs persistently

## Verification

1. Run `arxivbot-telegram` manually in a terminal
2. Send an arXiv link to the Telegram bot
3. Verify: "Processing..." reply appears within 1s
4. Verify: paper markdown created in `Papers/`, PDF in `PDFs/`
5. Verify: analysis appended to markdown
6. Verify: analysis text + figures received in Telegram
7. Verify: no leftover temp files on disk
8. Verify: changes pushed to GitHub
9. Load launchd plist, verify bot survives restarts
