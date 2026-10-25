"""Interactive setup for arxivbot-telegram: find the channel, write the credentials file, install the service."""

from __future__ import annotations

from argparse import ArgumentParser
from getpass import getpass, getuser
from pathlib import Path
import shutil
import subprocess

import requests

from arxivbot.constants import OBSIDIAN_VAULT_DIR
from arxivbot.telegram_bot import CREDENTIALS_PATH, telegram_api


SERVICE_PATH = Path("~/.config/systemd/user/arxivbot-telegram.service").expanduser()
# Programs the bot runs, whose folders the service's PATH must include (systemd does not read shell profiles)
SERVICE_PROGRAMS = ("arxivbot-telegram", "obsidian-import", "defuddle", "node", "claude", "git")

SERVICE_TEMPLATE = """\
[Unit]
Description=arxivbot Telegram bot: import papers and clip web pages into the Obsidian vault

[Service]
ExecStart={exec_start}
Environment=OBSIDIAN_VAULT_DIR={vault}
Environment=PATH={path}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""


def chats_from_updates(updates: list[dict]) -> dict[int, str]:
    """Chats seen in pending updates, as {chat ID: description}, channels first."""
    chats: dict[int, str] = {}
    for update in updates:
        message = update.get("channel_post") or update.get("message") or {}
        chat = message.get("chat") or {}
        if "id" in chat:
            name = chat.get("title") or chat.get("username") or chat.get("first_name") or "?"
            chats[chat["id"]] = f"{chat.get('type', 'chat')} {name!r}"
    return dict(sorted(chats.items(), key=lambda item: not item[1].startswith("channel")))


def credentials_text(token: str, chat_ids: list[int]) -> str:
    allowed = ",".join(map(str, chat_ids))
    return f'ARXIVBOT_TELEGRAM_BOT_TOKEN="{token}"\nARXIVBOT_TELEGRAM_ALLOWED_CHAT_IDS="{allowed}"\n'


def render_service(vault: Path) -> str:
    """The systemd user unit, with PATH built from where this shell finds the programs the bot runs."""
    found = {name: shutil.which(name) for name in SERVICE_PROGRAMS}
    if missing := [name for name, path in found.items() if not path]:
        print(f"Not found on PATH, so the service cannot run them: {', '.join(missing)}")
    folders = dict.fromkeys(str(Path(path).parent) for path in found.values() if path)
    folders.update(dict.fromkeys(["/usr/local/bin", "/usr/bin", "/bin"]))
    exec_start = found["arxivbot-telegram"] or "arxivbot-telegram"
    return SERVICE_TEMPLATE.format(exec_start=exec_start, vault=vault, path=":".join(folders))


def _ask(question: str) -> bool:
    return input(f"{question} [y/N] ").strip().lower() in {"y", "yes"}


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(text, encoding="utf-8")


def find_chats(token: str) -> list[int]:
    """Wait for a post to reach the bot, then let the user pick the chats to allow."""
    while True:
        # Without an offset, getUpdates leaves the updates pending, so the bot still receives them later
        chats = chats_from_updates(telegram_api(token, "getUpdates", json={"timeout": 0})["result"])
        if chats:
            break
        input("No posts have reached the bot yet. Post anything in the channel, then press Enter to check again.")

    listed = list(chats.items())
    for n, (chat_id, description) in enumerate(listed, 1):
        print(f"  {n}. {chat_id}  {description}")
    if len(listed) == 1:
        return [listed[0][0]]
    picked = input("Numbers of the chats to allow, comma-separated [1]: ").strip() or "1"
    return [listed[int(n) - 1][0] for n in picked.split(",")]


def install_service(vault: Path) -> None:
    if not (vault / ".git").exists():
        print(f"{vault} is not a git checkout of the vault. Set OBSIDIAN_VAULT_DIR and run this again.")
        return
    unit = render_service(vault)
    print(f"\n{SERVICE_PATH}:\n\n{unit}")
    if SERVICE_PATH.exists() and not _ask(f"{SERVICE_PATH} exists. Replace it?"):
        return
    SERVICE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SERVICE_PATH.write_text(unit, encoding="utf-8")
    commands = [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", "arxivbot-telegram"],
        ["loginctl", "enable-linger", getuser()],
    ]
    print("To start it now and keep it running after you log out:\n" + "\n".join(" ".join(c) for c in commands))
    if _ask("Run these now?"):
        for command in commands:
            subprocess.run(command, check=True)
        print("Follow its log with: journalctl --user -u arxivbot-telegram -f")


def main() -> None:
    parser = ArgumentParser(description="Set up arxivbot-telegram: credentials and, optionally, a systemd service")
    parser.add_argument("--service", action="store_true", help="Also install and start a systemd user service")
    args = parser.parse_args()

    token = getpass("Bot token from @BotFather (input hidden): ").strip()
    try:
        username = telegram_api(token, "getMe")["result"]["username"]
    except requests.RequestException as e:
        raise SystemExit(f"Telegram rejected the token or could not be reached: {e}") from e
    print(f"Bot: @{username}")
    print("\nAdd it to your channel as an admin that can post messages:")
    print(f"  https://t.me/{username}?startchannel&admin=post_messages")
    input("Then post anything in the channel and press Enter.")

    try:
        chat_ids = find_chats(token)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 409:
            raise SystemExit("The bot is already running and taking its updates. Stop it, then run this again.") from e
        raise

    if not CREDENTIALS_PATH.exists() or _ask(f"{CREDENTIALS_PATH} exists. Replace it?"):
        _write_private(CREDENTIALS_PATH, credentials_text(token, chat_ids))
        print(f"Wrote {CREDENTIALS_PATH} (readable only by you), allowing chat(s) {', '.join(map(str, chat_ids))}")

    if args.service:
        install_service(OBSIDIAN_VAULT_DIR)
    else:
        print(f"\nStart the bot with: OBSIDIAN_VAULT_DIR={OBSIDIAN_VAULT_DIR} arxivbot-telegram")


if __name__ == "__main__":
    main()
