"""Telegram bot for arxivbot: imports papers and analyzes them with Claude Code."""

from __future__ import annotations

import logging
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
import requests
from dotenv import load_dotenv

from arxivbot.constants import OBSIDIAN_VAULT_DIR, PAPERS_DIR, PDFS_DIR


LOGGER = logging.getLogger(__name__)

CREDENTIALS_PATH = Path("~/.config/arxivbot/credentials.env").expanduser()

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


def send_message(token: str, chat_id: int, text: str) -> int:
    """Send a text message, return message_id. Splits if >4096 chars."""
    max_len = 4096
    chunks = [text[i : i + max_len] for i in range(0, len(text), max_len)]
    msg_id = 0
    for chunk in chunks:
        result = telegram_api(token, "sendMessage", json={"chat_id": chat_id, "text": chunk})
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


# Patterns for extracting paper identifiers from Telegram messages
ARXIV_URL_RE = re.compile(r"https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)")
S2_URL_RE = re.compile(r"https?://(?:www\.)?semanticscholar\.org/paper/[a-zA-Z0-9-]+/([0-9a-f]{40})")
DOI_RE = re.compile(r"\b(10\.\d{4,9}/\S+)")
ARXIV_BARE_RE = re.compile(r"(?:^|\s)(\d{4}\.\d{4,5}(?:v\d+)?)(?:\s|$)")


def extract_paper_ids(text: str) -> list[str]:
    """Extract paper identifiers from message text. Returns raw IDs (not S2-formatted)."""
    ids: list[str] = []

    for m in ARXIV_URL_RE.finditer(text):
        ids.append(m.group(1))

    for m in S2_URL_RE.finditer(text):
        ids.append(m.group(1))

    for m in DOI_RE.finditer(text):
        ids.append(m.group(1))

    # Only try bare arXiv IDs if no URLs matched (avoids double-matching)
    if not ids:
        for m in ARXIV_BARE_RE.finditer(text):
            ids.append(m.group(1))

    # Deduplicate preserving order
    seen = set()
    unique = []
    for pid in ids:
        if pid not in seen:
            seen.add(pid)
            unique.append(pid)
    return unique


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


def git_commit_and_push() -> bool:
    """Stage paper changes, commit, and push."""
    try:
        subprocess.run(["git", "add", "Papers/", ".papers.db"], cwd=str(OBSIDIAN_VAULT_DIR), check=True)

        # Check if there are staged changes
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=str(OBSIDIAN_VAULT_DIR), capture_output=True
        )
        if result.returncode == 0:
            LOGGER.info("No changes to commit")
            return False

        subprocess.run(
            ["git", "commit", "-m", "Import and analyze paper(s) via arxivbot-telegram"],
            cwd=str(OBSIDIAN_VAULT_DIR),
            check=True,
        )
        subprocess.run(["git", "push"], cwd=str(OBSIDIAN_VAULT_DIR), check=True)
        LOGGER.info("Committed and pushed to remote")
        return True
    except subprocess.CalledProcessError as e:
        LOGGER.error(f"Git operation failed: {e}")
        return False


def process_paper(paper_id: str, token: str, chat_id: int) -> str:
    """Import a paper, analyze it, send to Telegram. Returns status message."""
    # 1. Run obsidian-import
    LOGGER.info(f"Running obsidian-import for: {paper_id}")
    result = subprocess.run(
        ["obsidian-import", paper_id],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        LOGGER.error(f"obsidian-import failed: {result.stderr[:500]}")
        return f"Import failed for {paper_id}"

    # 2. Find the created markdown and PDF
    # Parse the title from obsidian-import output or scan for new files
    # The simplest approach: scan Papers/ for files modified in the last 30s
    import time

    now = time.time()
    recent_mds = sorted(
        (p for p in PAPERS_DIR.glob("*.md") if now - p.stat().st_mtime < 30),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not recent_mds:
        return f"Import succeeded but could not find markdown for {paper_id}"

    md_path = recent_mds[0]
    title = md_path.stem

    # Check idempotency
    if IDEMPOTENCY_MARKER in md_path.read_text(encoding="utf-8"):
        return f"Already analyzed: {title}"

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
            return f"Imported {title} but Claude analysis failed"

        # 5. Parse figure selection and send to Telegram
        selected_figures = parse_figure_selection(analysis, figures)
        clean_analysis = strip_figure_comment(analysis)

        # 6. Append to markdown
        append_analysis_to_markdown(md_path, clean_analysis)

        # 7. Send analysis to Telegram
        send_message(token, chat_id, f"Analysis of: {title}\n\n{clean_analysis}")

        # 8. Send selected figures
        for fig in selected_figures:
            try:
                send_photo(token, chat_id, fig, caption=f"Figure from: {title}")
            except Exception as e:
                LOGGER.warning(f"Failed to send figure {fig.name}: {e}")

    # Temp dir is now cleaned up

    return f"Imported and analyzed: {title}"


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
    """Handle a single Telegram message."""
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if chat_id not in allowed_chat_ids:
        return

    # Handle /help
    if text.strip().startswith("/help"):
        send_message(
            token,
            chat_id,
            "arxivbot-telegram\n\n"
            "Send me a paper link or ID and I'll import it into your Obsidian vault with AI analysis.\n\n"
            "Supported formats:\n"
            "- arXiv URL: https://arxiv.org/abs/2408.16532\n"
            "- arXiv ID: 2408.16532\n"
            "- DOI: 10.1234/example\n"
            "- Semantic Scholar URL\n\n"
            "You can send multiple papers in one message.",
        )
        return

    # Extract paper IDs
    paper_ids = extract_paper_ids(text)
    if not paper_ids:
        return  # Silently ignore messages without paper IDs

    # Send "Processing..." reply
    processing_msg_id = send_message(token, chat_id, f"Processing {len(paper_ids)} paper(s)...")

    results = []
    for pid in paper_ids:
        try:
            status = process_paper(pid, token, chat_id)
            results.append(status)
        except Exception as e:
            LOGGER.error(f"Error processing {pid}: {e}", exc_info=True)
            results.append(f"Error processing {pid}: {e}")

    # Git commit and push all changes at once
    git_commit_and_push()

    # Edit the "Processing..." message with final status
    summary = "\n".join(results)
    edit_message(token, chat_id, processing_msg_id, summary)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    token, allowed_chat_ids = load_credentials()
    LOGGER.info(f"arxivbot-telegram started. Allowed chat IDs: {allowed_chat_ids}")

    offset = 0
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40,  # slightly longer than Telegram's long poll timeout
            )
            resp.raise_for_status()
            data = resp.json()

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message")
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
