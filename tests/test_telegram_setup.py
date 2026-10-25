import stat

import pytest

from arxivbot import telegram_setup
from arxivbot.telegram_setup import chats_from_updates, credentials_text, render_service


UPDATES = [
    {"update_id": 1, "message": {"chat": {"id": 42, "type": "private", "first_name": "Anil"}}},
    {"update_id": 2, "channel_post": {"chat": {"id": -1001, "type": "channel", "title": "Vault Inbox"}}},
    {"update_id": 3, "channel_post": {"chat": {"id": -1001, "type": "channel", "title": "Vault Inbox"}}},
    {"update_id": 4, "my_chat_member": {"chat": {"id": -1002}}},
]


def test_chats_from_updates_lists_each_chat_once_channels_first():
    assert chats_from_updates(UPDATES) == {-1001: "channel 'Vault Inbox'", 42: "private 'Anil'"}


def test_credentials_text():
    assert credentials_text("1:abc", [-1001, 42]) == (
        'ARXIVBOT_TELEGRAM_BOT_TOKEN="1:abc"\nARXIVBOT_TELEGRAM_ALLOWED_CHAT_IDS="-1001,42"\n'
    )


def test_render_service_builds_path_from_where_programs_are(tmp_path, monkeypatch):
    found = {"arxivbot-telegram": "/home/u/.local/bin/arxivbot-telegram", "defuddle": "/opt/node/bin/defuddle"}
    monkeypatch.setattr(telegram_setup.shutil, "which", found.get)
    unit = render_service(tmp_path)
    assert "ExecStart=/home/u/.local/bin/arxivbot-telegram\n" in unit
    assert f"Environment=OBSIDIAN_VAULT_DIR={tmp_path}\n" in unit
    assert "Environment=PATH=/home/u/.local/bin:/opt/node/bin:/usr/local/bin:/usr/bin:/bin\n" in unit


def test_main_finds_the_channel_and_writes_private_credentials(tmp_path, monkeypatch, capsys):
    creds = tmp_path / "arxivbot" / "credentials.env"
    responses = {
        "getMe": [{"result": {"username": "vault_inbox_bot"}}],
        "getUpdates": [{"result": []}, {"result": UPDATES}],
    }
    monkeypatch.setattr(telegram_setup, "telegram_api", lambda token, method, **kw: responses[method].pop(0))
    monkeypatch.setattr(telegram_setup, "getpass", lambda prompt: " 1:abc ")
    answers = iter(["", "", "1"])  # added the bot; no posts yet, retry; pick the channel
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr(telegram_setup, "CREDENTIALS_PATH", creds)
    monkeypatch.setattr("sys.argv", ["arxivbot-telegram-setup"])

    telegram_setup.main()

    assert creds.read_text() == credentials_text("1:abc", [-1001])
    assert stat.S_IMODE(creds.stat().st_mode) == 0o600
    assert stat.S_IMODE(creds.parent.stat().st_mode) == 0o700
    assert "https://t.me/vault_inbox_bot?startchannel&admin=post_messages" in capsys.readouterr().out


def test_main_explains_a_conflict_with_a_running_bot(monkeypatch):
    import requests

    def api(token, method, **kw):
        if method == "getMe":
            return {"result": {"username": "b"}}
        raise requests.HTTPError(response=type("R", (), {"status_code": 409})())

    monkeypatch.setattr(telegram_setup, "telegram_api", api)
    monkeypatch.setattr(telegram_setup, "getpass", lambda prompt: "1:abc")
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    monkeypatch.setattr("sys.argv", ["arxivbot-telegram-setup"])
    with pytest.raises(SystemExit, match="already running"):
        telegram_setup.main()
