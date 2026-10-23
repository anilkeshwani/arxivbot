"""Telegram bot for arxivbot: imports papers (optionally analyzed with Claude Code) and clips web pages."""

from __future__ import annotations

import logging
import os
import re
import stat
import subprocess
import sys
import tempfile
from functools import partial
from pathlib import Path
from urllib.parse import urlparse

import fitz  # PyMuPDF
import requests
from dotenv import load_dotenv

from arxivbot.constants import CLIPPINGS_DIR, DB_PATH, OBSIDIAN_VAULT_DIR, PAPERS_DIR, PDFS_DIR
from arxivbot.database import get_paper_title, init_db
from arxivbot.identifiers import ARXIV_ID_RE, ARXIV_URL_RE, DOI_RE, S2_URL_RE, extract_dois, parse_paper_id
from arxivbot.obsidian_importer import _query_id_fields
from arxivbot.web_clipper import clip_url


LOGGER = logging.getLogger(__name__)

CREDENTIALS_PATH = Path("~/.config/arxivbot/credentials.env").expanduser()

# Vault paths the bot writes to and commits (PDFs/ is not committed)
VAULT_WRITE_PATHS = (PAPERS_DIR, DB_PATH, CLIPPINGS_DIR)
GIT_TIMEOUT = 120

# Sites whose URLs carry a bare arXiv ID for a paper page, e.g. https://huggingface.co/papers/2408.16532
ARXIV_MIRROR_HOSTS = {"huggingface.co", "alphaxiv.org", "www.alphaxiv.org", "arxiv-sanity-lite.com"}

# Minimum image dimensions to keep (filters out icons, logos, etc.)
MIN_IMAGE_WIDTH = 200
MIN_IMAGE_HEIGHT = 200

ANALYSIS_PROMPT = """\
You are a senior ML researcher and technical writer. Your task is to produce a comprehensive, \
self-contained analysis of the attached research paper. The analysis should be written so that a \
reader with general ML familiarity — but no prior knowledge of this specific subfield or paper — \
can fully understand every claim, contribution, and result without needing to read the original.

The paper PDF is at: {pdf_path}

{figure_instructions}

Follow the structure below exactly.

---

### 1. The Headline: What This Paper Actually Does (2–4 sentences)

Open with a crisp, jargon-free statement of what the paper achieves and why it matters. Think of \
this as the "elevator pitch" — what would you tell a sharp colleague over coffee? Avoid vague \
phrases like "we propose a novel framework." Be concrete: what input goes in, what comes out, and \
what changes because of this work?

### 2. Why This Matters: The Problem in Context

Before diving into contributions, set the stage:

- **The task or problem domain.** Define it from first principles. What is the goal? What does the \
input look like, what does the desired output look like? Give a concrete example if it helps.
- **Why it's hard.** What specific technical barriers, trade-offs, or limitations have made this \
problem difficult? Be precise — not "previous methods are slow" but *why* they are slow, and what \
architectural or algorithmic constraint causes it.
- **Where the field stood before this paper.** Briefly describe the dominant approaches (1–3 \
sentences each). What do they do well? Where do they fall short? Name specific prior works if \
they are important baselines.
- **The gap this paper targets.** Articulate exactly what unsolved problem or unaddressed limitation \
this paper goes after. This should flow naturally from the prior-work discussion.

### 3. Key Contributions and Ideas

This is the centrepiece. For each major contribution:

- **State each contribution clearly in one to two sentences.**
- **Explain the core idea or insight.** What is the key observation, hypothesis, or design \
principle? Why does it work, intuitively? Use analogies or simplified examples where they genuinely \
clarify — but never at the cost of accuracy.
- **Provide the necessary technical detail.** Define any new terms, components, objectives, or \
architectural choices. If the contribution involves a new loss function, describe what each term \
does and why it's there. If it's an architectural change, explain the information flow. The reader \
should understand the mechanism, not just the label.
- **Contrast with the prior approach.** What did people do before, and how does this differ? Be \
specific about what is changed and what stays the same.

Present contributions in order of importance, not necessarily the order they appear in the paper.

### 4. Method: Full Technical Breakdown

Walk through the complete method end-to-end:

- **Architecture / pipeline overview.** Describe the full system: its major components, how data \
flows through them, and how they connect. If there are multiple stages (e.g. pre-training then \
fine-tuning, or an encoder-decoder with a separate module), explain each.
- **Training procedure.** What objective(s) are optimised? What data is used, and how is it \
prepared or augmented? Are there curriculum strategies, scheduled hyperparameters, or multi-phase \
training?
- **Key design choices.** Highlight non-obvious decisions — things the authors chose to do (or \
not do) that meaningfully affect the outcome. Explain the rationale where the paper provides one.
- **Notation and formalism.** Where equations are central to understanding, reproduce the key ones \
and explain every symbol. Do not just paste equations — narrate what they compute and why.

### 5. Experiments and Results

For each major experiment or evaluation:

- **Setup.** What datasets, metrics, and baselines are used? Briefly describe any dataset or \
metric the reader might not know.
- **Main results.** State the headline numbers and what they mean. How large are the improvements? \
Are they consistent across settings?
- **Ablations and analysis.** What do the ablation studies reveal about which components matter \
most? Are there surprising findings?
- **Limitations the authors acknowledge** (or that you observe). Where does the method struggle? \
What settings or domains are not tested?

### 6. Connections, Implications, and Open Questions

- **Relationship to concurrent or subsequent work.** If you are aware of related work published \
around the same time or after, briefly note how this paper fits into the broader trajectory.
- **Potential extensions or applications.** What natural follow-up questions does this work raise? \
Where could the ideas be applied beyond the paper's scope?
- **What remains unsolved.** What limitations or open problems does this work leave on the table?

---

## Figure Selection

After the analysis, on a SEPARATE line, output a comment listing only the extracted figure \
filenames most relevant to understanding the paper's key contributions and method:
<!-- FIGURES: fig_001.png, fig_003.png -->

If no figures were extracted or none are relevant, output:
<!-- FIGURES: none -->

## Formatting and Style Guidelines

- Be self-contained. Define every acronym on first use.
- Be concrete over abstract. Prefer specific dimensions, sizes, numbers.
- Be honest about uncertainty. If the paper is vague on a detail, say so.
- Use structure aggressively. Bullet points for lists, paragraphs for narrative.
- Target 600–1500 words depending on paper complexity.
- Output Obsidian-compatible markdown.
"""

IDEMPOTENCY_MARKER = "### 1. The Headline"


# --- Telegram API helpers ---


def telegram_api(token: str, method: str, **kwargs) -> dict:
    """Call a Telegram Bot API method."""
    resp = requests.post(f"https://api.telegram.org/bot{token}/{method}", **kwargs, timeout=60)
    resp.raise_for_status()
    return resp.json()


def send_message(token: str, chat_id: int, text: str, reply_to: int | None = None) -> int:
    """Send a text message, return message_id. Splits if >4096 chars."""
    max_len = 4096
    chunks = [text[i : i + max_len] for i in range(0, len(text), max_len)]
    msg_id = 0
    for chunk in chunks:
        payload: dict = {"chat_id": chat_id, "text": chunk}
        if reply_to:
            payload["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        result = telegram_api(token, "sendMessage", json=payload)
        msg_id = result.get("result", {}).get("message_id", 0)
    return msg_id


def edit_message(token: str, chat_id: int, message_id: int, text: str) -> None:
    """Edit an existing message."""
    try:
        telegram_api(token, "editMessageText", json={"chat_id": chat_id, "message_id": message_id, "text": text})
    except Exception as e:
        LOGGER.warning(f"Failed to edit message: {e}")


def send_photo(token: str, chat_id: int, photo_path: Path, caption: str = "") -> None:
    """Send a photo from a local file path."""
    with open(photo_path, "rb") as f:
        data: dict[str, int | str] = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption[:1024]  # Telegram caption limit
        telegram_api(token, "sendPhoto", data=data, files={"photo": f})


# --- Paper ID extraction ---


def extract_paper_ids(text: str) -> list[str]:
    """Extract paper identifiers from message text. Returns raw IDs (not S2-formatted), one per paper."""
    ids = [m.group(1) for regex in (ARXIV_URL_RE, S2_URL_RE) for m in regex.finditer(text)] + extract_dois(text)
    # Bare arXiv IDs are only read from what the URLs and DOIs leave, so none is matched twice
    for regex in (ARXIV_URL_RE, S2_URL_RE, DOI_RE):
        text = regex.sub(" ", text)
    ids += [m.group(0) for m in ARXIV_ID_RE.finditer(text)]

    # One raw ID per paper, e.g. an arXiv link and its arXiv DOI in the same message
    raw_by_s2_id: dict[str, str] = {}
    for raw_id in ids:
        try:
            raw_by_s2_id.setdefault(parse_paper_id(raw_id), raw_id)
        except ValueError:
            continue
    return list(raw_by_s2_id.values())


def message_text(message: dict) -> str:
    return message.get("text") or message.get("caption") or ""


def extract_links(message: dict) -> tuple[list[str], str]:
    """Web links in a message or channel post, and its text with the links cut out.

    Telegram marks links with entities, whose offsets count UTF-16 code units.
    """
    utf16 = message_text(message).encode("utf-16-le")
    entities = message.get("entities") or message.get("caption_entities") or []
    links, rest, pos = [], [], 0
    for entity in sorted(entities, key=lambda e: e["offset"]):
        if entity["type"] == "url":
            start, end = 2 * entity["offset"], 2 * (entity["offset"] + entity["length"])
            link = utf16[start:end].decode("utf-16-le")
            links.append(link if "://" in link else f"https://{link}")
            rest.append(utf16[pos:start].decode("utf-16-le"))
            pos = end
        elif entity["type"] == "text_link":
            links.append(entity["url"])
    rest.append(utf16[pos:].decode("utf-16-le"))
    web_links = [link for link in dict.fromkeys(links) if urlparse(link).scheme.lower() in ("http", "https")]
    return web_links, " ".join(rest)


def is_paper_url(url: str) -> bool:
    if ARXIV_URL_RE.search(url) or S2_URL_RE.search(url) or extract_dois(url):
        return True
    return urlparse(url).hostname in ARXIV_MIRROR_HOSTS and ARXIV_ID_RE.search(url) is not None


def route_message(message: dict) -> tuple[list[tuple[str, str | None]], list[str]]:
    """Split a message into papers to import, as (raw ID, link it came from), and page URLs to clip."""
    links, text = extract_links(message)
    paper_urls = [url for url in links if is_paper_url(url)]
    # Bare IDs and DOIs are only read outside links, so a number in a blog URL is never taken for an arXiv ID
    found = [(raw_id, None) for raw_id in extract_paper_ids(text)]
    found += [(raw_id, url) for url in paper_urls for raw_id in extract_paper_ids(url)]

    papers: dict[str, tuple[str, str | None]] = {}
    for raw_id, url in found:
        papers.setdefault(parse_paper_id(raw_id), (raw_id, url))
    return list(papers.values()), [url for url in links if url not in paper_urls]


# --- Figure extraction ---


def extract_figures(pdf_path: Path, output_dir: Path) -> list[Path]:
    """Extract images from a PDF, filter by size, save to output_dir. Returns paths."""
    figures: list[Path] = []
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        LOGGER.warning(f"Could not open PDF {pdf_path}: {e}")
        return figures

    img_index = 0
    for page_num in range(len(doc)):
        page = doc[page_num]
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                base_image = doc.extract_image(xref)
            except Exception:
                continue

            width = base_image.get("width", 0)
            height = base_image.get("height", 0)
            if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
                continue

            ext = base_image.get("ext", "png")
            img_index += 1
            fig_path = output_dir / f"fig_{img_index:03d}.{ext}"
            fig_path.write_bytes(base_image["image"])
            figures.append(fig_path)

    doc.close()
    LOGGER.info(f"Extracted {len(figures)} figures from {pdf_path.name}")
    return figures


# --- Claude Code analysis ---


def run_claude_analysis(pdf_path: Path, figure_paths: list[Path]) -> str | None:
    """Run claude -p with the analysis prompt. Returns Claude's response text or None."""
    if figure_paths:
        figure_list = ", ".join(str(p) for p in figure_paths)
        figure_instructions = f"The following figures were extracted from the paper: {figure_list}"
    else:
        figure_instructions = "No figures were extracted from the paper."

    prompt = ANALYSIS_PROMPT.format(pdf_path=pdf_path, figure_instructions=figure_instructions)

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(OBSIDIAN_VAULT_DIR),
        )
        if result.returncode != 0:
            LOGGER.error(f"Claude exited with code {result.returncode}: {result.stderr[:500]}")
            return None
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        LOGGER.error("Claude analysis timed out (300s)")
        return None
    except FileNotFoundError:
        LOGGER.error("'claude' CLI not found. Is Claude Code installed?")
        return None


def parse_figure_selection(analysis: str, available_figures: list[Path]) -> list[Path]:
    """Parse <!-- FIGURES: fig_001.png, fig_003.png --> from Claude's response."""
    match = re.search(r"<!--\s*FIGURES:\s*(.+?)\s*-->", analysis)
    if not match:
        return []

    raw = match.group(1).strip()
    if raw.lower() == "none":
        return []

    selected_names = {name.strip() for name in raw.split(",")}
    return [p for p in available_figures if p.name in selected_names]


def strip_figure_comment(analysis: str) -> str:
    """Remove the <!-- FIGURES: ... --> comment from the analysis text."""
    return re.sub(r"\n?<!--\s*FIGURES:.*?-->\n?", "", analysis).strip()


# --- Core paper processing ---


def find_paper_markdown(title: str) -> Path | None:
    """Find the markdown file for a paper by title (matching obsidian-import's naming)."""
    from pathvalidate import sanitize_filename

    filename = sanitize_filename(title.replace(".", " ")) + ".md"
    candidate = PAPERS_DIR / filename
    if candidate.exists():
        return candidate
    return None


def find_paper_pdf(title: str) -> Path | None:
    """Find the PDF file for a paper by title."""
    from pathvalidate import sanitize_filename

    filename = sanitize_filename(title.replace(".", " ")) + ".pdf"
    candidate = PDFS_DIR / filename
    if candidate.exists():
        return candidate
    return None


def append_analysis_to_markdown(md_path: Path, analysis: str) -> None:
    """Append analysis to paper markdown, idempotently."""
    text = md_path.read_text(encoding="utf-8")
    if IDEMPOTENCY_MARKER in text:
        LOGGER.info(f"Skipping {md_path.name}: analysis already present")
        return

    if not text.endswith("\n"):
        text += "\n"
    text += "\n" + analysis + "\n"
    md_path.write_text(text, encoding="utf-8")
    LOGGER.info(f"Appended analysis to {md_path.name}")


def _git(*args: str) -> subprocess.CompletedProcess:
    # Literal pathspecs, so a note title with [brackets] is not read as a glob that stages other files
    return subprocess.run(
        ["git", "--literal-pathspecs", *args],
        cwd=str(OBSIDIAN_VAULT_DIR),
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        capture_output=True,
        text=True,
        check=True,
        timeout=GIT_TIMEOUT,
    )


def _git_error(e: subprocess.SubprocessError) -> str:
    return (getattr(e, "stderr", None) or str(e)).strip()[:500]


def vault_snapshot() -> dict[Path, tuple[int, int] | None]:
    """(mtime, size) of the uncommitted files under VAULT_WRITE_PATHS, keyed by absolute path."""
    root = Path(_git("rev-parse", "--show-toplevel").stdout.strip())
    out = _git("status", "--porcelain", "-z", "--untracked-files=all", "--", *map(str, VAULT_WRITE_PATHS)).stdout
    # Entries are "XY path"; the original path of a rename follows as a bare field and is skipped
    paths = [root / entry[3:] for entry in out.split("\0") if entry[2:3] == " "]
    return {path: (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None for path in paths}


def changed_paths(before: dict[Path, tuple[int, int] | None], after: dict[Path, tuple[int, int] | None]) -> list[Path]:
    return sorted(path for path, stamp in after.items() if path not in before or before[path] != stamp)


def git_commit(paths: list[Path], message: str) -> bool:
    """Commit only the given paths, leaving anything else staged or dirty in the vault alone."""
    try:
        _git("add", "--", *map(str, paths))
        _git("commit", "-m", message, "--", *map(str, paths))
        LOGGER.info(f"Committed: {message}")
        return True
    except subprocess.SubprocessError as e:
        LOGGER.error(f"git commit failed: {_git_error(e)}")
        return False


def git_push() -> bool:
    """Push, rebasing onto the remote first if it has moved on."""
    try:
        _git("push")
        return True
    except subprocess.SubprocessError:
        LOGGER.info("Push rejected, rebasing onto remote and retrying")
    try:
        _git("pull", "--rebase", "--autostash")
        _git("push")
        return True
    except subprocess.SubprocessError as e:
        LOGGER.error(f"git push failed: {_git_error(e)}")
        # Never leave the vault mid-rebase, where later commits would land on a detached HEAD
        subprocess.run(["git", "rebase", "--abort"], cwd=str(OBSIDIAN_VAULT_DIR), capture_output=True)
        return False


def analysis_enabled() -> bool:
    return os.environ.get("ARXIVBOT_TELEGRAM_ANALYZE", "1") != "0"


def clip_page(url: str) -> tuple[str, str | None]:
    """Clip a web page. Returns (status, commit message or None if nothing was written)."""
    note_path, created = clip_url(url)
    if not created:
        return f"Already clipped: {note_path.stem}", None
    return f"Clipped: {note_path.stem}", f'Clip "{note_path.stem}" via Telegram'


def process_paper(
    paper_id: str, source_url: str | None, token: str, chat_id: int, reply_to: int
) -> tuple[str, str | None]:
    """Import a paper and, if enabled, analyze it and send the analysis to Telegram.

    A paper neither Semantic Scholar nor arXiv knows is clipped from source_url instead, if it came from a link.
    Returns (status, commit message or None if nothing was written).
    """
    if title := get_paper_title(DB_PATH, **_query_id_fields(parse_paper_id(paper_id))):
        return f"Already in the vault: {title}", None
    analyze = analysis_enabled()

    # 1. Run obsidian-import (the PDF is only needed for the analysis)
    LOGGER.info(f"Running obsidian-import for: {paper_id}")
    before = vault_snapshot()
    result = subprocess.run(
        ["obsidian-import", paper_id] + ([] if analyze else ["--no_pdf"]),
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        LOGGER.error(f"obsidian-import failed: {result.stderr[:500]}")
        return f"Import failed for {paper_id}", None

    # 2. Find the created markdown from what the import changed in the vault
    mds = [p for p in changed_paths(before, vault_snapshot()) if p.parent == PAPERS_DIR and p.suffix == ".md"]
    if not mds:
        return clip_page(source_url) if source_url else (f"Paper not found: {paper_id}", None)

    md_path = mds[0]
    title = md_path.stem
    commit_message = f'Import "{title}" paper via Telegram'

    if not analyze:
        return f"Imported: {title}", commit_message

    # Check idempotency
    if IDEMPOTENCY_MARKER in md_path.read_text(encoding="utf-8"):
        return f"Already analyzed: {title}", commit_message

    pdf_path = find_paper_pdf(title)

    # 3. Extract figures and run analysis in temp dir
    with tempfile.TemporaryDirectory(prefix="arxivbot_figs_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        figures: list[Path] = []
        if pdf_path:
            figures = extract_figures(pdf_path, tmp_path)

        # 4. Run Claude Code analysis
        analysis_target = pdf_path or md_path
        LOGGER.info(f"Running Claude analysis on: {analysis_target.name}")
        analysis = run_claude_analysis(analysis_target, figures)

        if not analysis:
            return f"Imported {title} but Claude analysis failed", commit_message

        # 5. Parse figure selection and send to Telegram
        selected_figures = parse_figure_selection(analysis, figures)
        clean_analysis = strip_figure_comment(analysis)

        # 6. Append to markdown
        append_analysis_to_markdown(md_path, clean_analysis)

        # 7. Send analysis to Telegram
        send_message(token, chat_id, f"Analysis of: {title}\n\n{clean_analysis}", reply_to=reply_to)

        # 8. Send selected figures
        for fig in selected_figures:
            try:
                send_photo(token, chat_id, fig, caption=f"Figure from: {title}")
            except Exception as e:
                LOGGER.warning(f"Failed to send figure {fig.name}: {e}")

    # Temp dir is now cleaned up

    return f"Imported and analyzed: {title}", f'Import and analyze "{title}" paper via Telegram'


def run_item(label: str, job) -> tuple[str, bool]:
    """Run one import or clip and commit what it wrote, even if it failed partway. Returns (status, committed)."""
    before = vault_snapshot()
    try:
        status, commit_message = job()
    except Exception as e:
        LOGGER.error(f"Error processing {label}: {e}", exc_info=True)
        status, commit_message = f"Error processing {label}: {e}", None

    paths = changed_paths(before, vault_snapshot())
    if not paths:
        return status, False
    if git_commit(paths, commit_message or f"Add {label} via Telegram"):
        return status, True
    return f"{status} (not committed, see the bot log)", False


# --- Credential loading and validation ---


def load_credentials() -> tuple[str, set[int]]:
    """Load and validate credentials. Returns (bot_token, allowed_chat_ids)."""
    if not CREDENTIALS_PATH.exists():
        print(f"Credentials file not found: {CREDENTIALS_PATH}", file=sys.stderr)
        print("Create it with:", file=sys.stderr)
        print(f"  mkdir -p {CREDENTIALS_PATH.parent}", file=sys.stderr)
        print(f"  chmod 700 {CREDENTIALS_PATH.parent}", file=sys.stderr)
        print(f"  touch {CREDENTIALS_PATH}", file=sys.stderr)
        print(f"  chmod 600 {CREDENTIALS_PATH}", file=sys.stderr)
        sys.exit(1)

    # Check file permissions
    file_mode = CREDENTIALS_PATH.stat().st_mode
    if file_mode & (stat.S_IRGRP | stat.S_IROTH):
        LOGGER.warning(
            f"Credentials file {CREDENTIALS_PATH} is readable by group/others. "
            f"Fix with: chmod 600 {CREDENTIALS_PATH}"
        )

    load_dotenv(CREDENTIALS_PATH)

    token = os.environ.get("ARXIVBOT_TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("ARXIVBOT_TELEGRAM_BOT_TOKEN not set in credentials file", file=sys.stderr)
        sys.exit(1)

    raw_ids = os.environ.get("ARXIVBOT_TELEGRAM_ALLOWED_CHAT_IDS", "")
    if not raw_ids:
        print("ARXIVBOT_TELEGRAM_ALLOWED_CHAT_IDS not set in credentials file", file=sys.stderr)
        sys.exit(1)

    allowed = set()
    for cid in raw_ids.split(","):
        cid = cid.strip()
        if cid:
            try:
                allowed.add(int(cid))
            except ValueError:
                print(f"Invalid chat ID: {cid!r}", file=sys.stderr)
                sys.exit(1)

    return token, allowed


# --- Main loop ---


def handle_message(token: str, allowed_chat_ids: set[int], message: dict) -> None:
    """Handle a single Telegram message or channel post."""
    chat_id = message.get("chat", {}).get("id")
    text = message_text(message)
    message_id = message.get("message_id")

    if chat_id not in allowed_chat_ids:
        return

    # Handle /help
    if text.strip().startswith("/help"):
        send_message(
            token,
            chat_id,
            "arxivbot-telegram\n\n"
            "Post a paper and I'll import it into your Obsidian vault"
            f"{' with AI analysis' if analysis_enabled() else ''}. "
            "Post any other link and I'll clip the page into Clippings/.\n\n"
            "Recognized as papers:\n"
            "- arXiv URL: https://arxiv.org/abs/2408.16532\n"
            "- arXiv ID: 2408.16532\n"
            "- DOI: 10.1234/example, or a publisher link containing one\n"
            "- Semantic Scholar URL\n"
            "- Hugging Face / alphaXiv paper pages\n\n"
            "A paper link that cannot be imported is clipped instead. "
            "You can send several links in one message.",
            reply_to=message_id,
        )
        return

    papers, clip_urls = route_message(message)
    if not papers and not clip_urls:
        return  # Silently ignore messages without links or paper IDs

    jobs = [(pid, partial(process_paper, pid, url, token, chat_id, message_id)) for pid, url in papers]
    jobs += [(url, partial(clip_page, url)) for url in clip_urls]
    processing_msg_id = send_message(token, chat_id, f"Processing {len(jobs)} item(s)...", reply_to=message_id)

    # One commit per paper or page keeps the vault history atomic; a single push at the end
    results = []
    committed = False
    for label, job in jobs:
        status, item_committed = run_item(label, job)
        results.append(status)
        committed |= item_committed

    if committed and not git_push():
        results.append("Committed locally but git push failed, see the bot log")

    edit_message(token, chat_id, processing_msg_id, "\n".join(results)[:4096])


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    token, allowed_chat_ids = load_credentials()
    init_db(DB_PATH)
    LOGGER.info(f"arxivbot-telegram started. Allowed chat IDs: {allowed_chat_ids}")

    offset = 0
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"offset": offset, "timeout": 30, "allowed_updates": '["message", "channel_post"]'},
                timeout=40,  # slightly longer than Telegram's long poll timeout
            )
            resp.raise_for_status()
            data = resp.json()

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                # Posts in a channel the bot administers arrive as channel_post rather than message
                message = update.get("message") or update.get("channel_post")
                if message:
                    try:
                        handle_message(token, allowed_chat_ids, message)
                    except Exception as e:
                        LOGGER.error(f"Unhandled error in handle_message: {e}", exc_info=True)

        except requests.exceptions.Timeout:
            continue  # Normal for long polling
        except requests.exceptions.ConnectionError as e:
            LOGGER.warning(f"Connection error (retrying in 5s): {e}")
            import time

            time.sleep(5)
        except Exception as e:
            LOGGER.error(f"Unexpected error in main loop: {e}", exc_info=True)
            import time

            time.sleep(5)


if __name__ == "__main__":
    main()
