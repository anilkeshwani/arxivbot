# Telegram bot setup

This guide sets up `arxivbot-telegram` so that anything you post in a private Telegram channel lands in your Obsidian vault: papers are imported into `Papers/` and other links are clipped into `Clippings/`, each as its own commit that is pushed to the vault's remote.

You need:

- a Telegram account, on any device;
- a host that stays on (the "server"), with a git checkout of the vault that can push without a password prompt;
- arxivbot and Defuddle installed on that host:

  ```bash
  uv tool install git+https://github.com/anilkeshwani/arxivbot
  npm install -g defuddle
  ```

## 1. Create the bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram and send `/newbot`.
2. Give it a display name (for example `Vault Inbox`) and a username ending in `bot` (for example `my_vault_inbox_bot`).
3. BotFather replies with a token such as `123456789:AAH...`. Anyone holding it controls the bot, so keep it out of chats and repositories.
4. Optional: send `/setcommands`, pick the bot and send `help - What the bot recognizes`, so `/help` autocompletes in the channel.

## 2. Create a private channel

In Telegram, choose **New Channel**, name it (for example `Vault Inbox`) and make it **Private**. Telegram has no link that creates a channel, so this step is manual.

## 3. Connect the bot to the channel and write the credentials

On the server, stop the bot if it is already running (the setup reads the bot's pending updates, which a running bot takes first), then run:

```bash
OBSIDIAN_VAULT_DIR=~/journal arxivbot-telegram-setup --service
```

It asks for the token without echoing it, then:

1. prints a link, `https://t.me/<bot username>?startchannel&admin=post_messages`, that opens Telegram's "add to channel" picker with the **Post Messages** right already ticked. Open it on any device where you use Telegram, pick the channel and confirm;
2. asks you to post anything in the channel, then lists the chats that have reached the bot. Pick the channel (and your direct chat with the bot, if you also messaged it);
3. writes `~/.config/arxivbot/credentials.env`, readable only by you;
4. with `--service`, writes `~/.config/systemd/user/arxivbot-telegram.service` with a `PATH` built from where your shell finds `arxivbot-telegram`, `obsidian-import`, `defuddle`, `node`, `claude` and `git`, shows it, and offers to enable it and turn on lingering so it keeps running after you log out.

Without `--service` it only writes the credentials and prints the command that starts the bot in the foreground.

### Doing it by hand

If you would rather not run the setup command:

1. Make the bot an admin of the channel: open `https://t.me/<bot username>?startchannel&admin=post_messages`, or go to the channel's **Manage Channel** > **Administrators** > **Add Admin**, search for the bot and keep **Post Messages** on.
2. Post anything in the channel, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser. The channel's ID is the number at `"channel_post"` > `"chat"` > `"id"`, starting with `-100`. An empty `"result": []` means no post reached the bot: check it is an admin and post again.
3. Write the credentials file. `ARXIVBOT_TELEGRAM_ALLOWED_CHAT_IDS` takes several IDs separated by commas, and posts from any other chat are ignored:

   ```bash
   mkdir -p ~/.config/arxivbot && chmod 700 ~/.config/arxivbot
   cat > ~/.config/arxivbot/credentials.env <<'EOF'
   ARXIVBOT_TELEGRAM_BOT_TOKEN="123456789:AAH..."
   ARXIVBOT_TELEGRAM_ALLOWED_CHAT_IDS="-1001234567890"
   EOF
   chmod 600 ~/.config/arxivbot/credentials.env
   ```

## 4. Check the server can push unattended

The bot commits and pushes with nobody at the keyboard, and a systemd service has no SSH agent. Check that git can reach the remote without one:

```bash
env -u SSH_AUTH_SOCK ssh -o BatchMode=yes -T git@github.com
```

It should greet you by your GitHub username. If it reports `Permission denied`, give the host a key without a passphrase (a deploy key with write access to the vault repository works) or an HTTPS credential helper.

## 5. Try it

Start the bot in the foreground if you did not install the service:

```bash
OBSIDIAN_VAULT_DIR=~/journal arxivbot-telegram
```

Then post in the channel, one message at a time:

- `/help`, which gets a reply listing what counts as a paper;
- a paper, such as `https://arxiv.org/abs/1706.03762`, which gets `Imported: ...` or `Already in the vault: ...`;
- an article or blog link, which gets `Clipped: ...`.

Replies are threaded under your posts. `git -C ~/journal log --oneline -3` shows the new commits.

By default every imported paper is also analyzed with `claude -p`, which takes a few minutes and uses your Claude Code account, and the analysis is appended to the note in the vault's summary format. To import without analysis, set `ARXIVBOT_TELEGRAM_ANALYZE=0`: on the command line in front of `arxivbot-telegram`, or as an `Environment=` line in the service file followed by `systemctl --user daemon-reload` and a restart.

## Running as a service

```bash
systemctl --user status arxivbot-telegram       # is it running?
journalctl --user -u arxivbot-telegram -f       # follow its log
systemctl --user restart arxivbot-telegram      # after upgrading arxivbot
```

Upgrade with `uv tool install --reinstall git+https://github.com/anilkeshwani/arxivbot` and restart the service.

## What the bot recognizes

- **Papers**, imported with `obsidian-import`: arXiv links and IDs, DOIs and publisher links containing one, Semantic Scholar links, and Hugging Face and alphaXiv paper pages. A paper link that neither Semantic Scholar nor arXiv knows is clipped instead.
- **Everything else**, clipped as by `obsidian-clip`. X posts are titled with the handle and the post's opening words, and saved under one `x.com` URL whichever form the link had.

One post can hold several links; each becomes its own commit, and the post ends with one push. A `.html` or `.md` file is clipped as described in [Pages that need your login](#pages-that-need-your-login).

## Pages that need your login

Some pages cannot be fetched from the server: paywalled articles (including gift links, such as the FT's), pages behind a login, and sites whose bot checks block requests that do not come from a real browser. Your own browser can load them, so send the bot the page your browser loaded, as a file:

- **A note from the Obsidian Web Clipper.** Clip the page as usual, but save it as a file from the clipper's menu instead of adding it to Obsidian, then send the `.md` file to the channel. The bot saves it to `Clippings/` unchanged, so it matches clips made straight into the vault.
- **The page itself.** Save it from the browser with **Save Page As** > **Webpage, HTML Only** (Firefox: **Web Page, HTML only**), then send the `.html` file. The bot extracts it with Defuddle like any other page. The note's `source` is the page's canonical URL; for a page that names none, put its link in the file's caption.

Either way the server never contacts the site: it only processes what your browser loaded. A file whose `source` is already in `Clippings/` is skipped. Bots can download files up to 20 MB.

The same works from a shell with `obsidian-clip saved-page.html` or `obsidian-clip note.md` (`--url` gives a saved page without a canonical URL its source).

When the vault is open on the same machine as the browser, clipping with the Web Clipper directly into the vault is simpler still.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The bot never replies | The chat ID in `credentials.env` does not match the channel, so posts are ignored silently, or the bot is no longer an admin. Stop the bot and run `arxivbot-telegram-setup` again. |
| `409 Conflict` in the log | Two copies are polling the same bot, for example a foreground run and the service. Stop one. |
| `Committed locally but git push failed` | The push could not authenticate or hit a conflict it could not rebase. Run the check in step 4 and `git -C ~/journal status`. The commits are kept and go out with the next successful push. |
| `Defuddle CLI not found` or `obsidian-import: not found` | The service's `PATH` does not reach the program. Rerun `arxivbot-telegram-setup --service` from a shell where `command -v defuddle` works. |
| `Defuddle failed: ... 403 Forbidden` | The site blocks requests that do not come from a real browser (bot protection such as PerimeterX or a Cloudflare check). Send the page as a file instead (see [Pages that need your login](#pages-that-need-your-login)). |
| `Defuddle extracted no content` | The page needs JavaScript or a login to show its text. Send it as a Web Clipper `.md` file. |
| `The saved page does not name its URL` | The `.html` file has no canonical link. Send it again with the page's link as the caption. |
