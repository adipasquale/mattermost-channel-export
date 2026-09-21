# mattermost-channel-export

Three scripts to select, export a Mattermost channel history, and render it as a self-contained static HTML archive.

Tested against Mattermost **10.12.4**.

---

## Scripts

| Script       | Input                 | Output                 |
| ------------ | --------------------- | ---------------------- |
| `export.py`  | Mattermost REST API   | `channel_export.json`  |
| `export_channels_list.py` | Mattermost REST API | `channels.tsv` |
| `to_html.py` | `channel_export.json` | `channel_archive.html` |

---

## Setup

```bash
uv sync
cp .env.example .env
# Edit .env with your Mattermost URL and personal access token
```

---

## Export Channels List — `export_channels_list.py`

Export channels that the user is a member of to a TSV file with columns: `name | id | Open or Private | members count`

```bash
uv run --env-file .env export_channels_list.py [-o output.tsv]
```

---

## Export a channel's messages — `export.py`

Fetches the full history of a channel via the Mattermost API and writes a clean JSON file.

```bash
uv run --env-file .env export.py
```

### Environment variables

You can `cp .env.example .env` and edit the values there.
`.env` is gitignored.

| Variable        | Required | Description                                                                                              |
| --------------- | -------- | -------------------------------------------------------------------------------------------------------- |
| `MM_URL`        | Yes      | Base URL of your instance, e.g. `https://mattermost.example.com`                                         |
| `MM_TOKEN`      | Yes      | Personal access token (Account Settings → Security → Personal Access Tokens)                             |
| `MM_CHANNEL_ID` | Yes      | ID of the channel(s) to export. Comma-separated for multiple channels, e.g. `abc123,def456`              |
| `MM_OUTPUT_DIR` | No       | Directory where the output files are written (default: current directory)                                |
| `MM_COOKIE`     | No       | Cookie header to send with every request, needed when the instance sits behind an auth proxy (see below) |


### Cookie-based authentication (`MM_COOKIE`)

If the Mattermost instance is behind `oauth2-proxy`, a personal access token alone may not be enough to get past the proxy. In that case, grab the `_oauth2_proxy` cookie value from your browser's dev tools (Application/Storage → Cookies) after logging in, and export it:

`MM_COOKIE` accepts a standard `key=value; key2=value2` cookie string, so you can pass additional cookies alongside `_oauth2_proxy` if needed.

### Usage

If you have setup channel ID(s) and output dir in your `.env` you can simply run

```bash
uv run --env-file .env export.py
```

### What it exports

- All messages, chronologically ordered, fully paginated
- Per-message: author (username, display name), timestamp, message text, edit status
- Reactions with emoji and list of users
- File attachments (name, MIME type, size)
- Link embeds (URL, OpenGraph title and description)
- Thread replies nested under their root post
- System messages and deleted posts are excluded

### Output format

```json
{
  "exported_at": "2026-04-21T10:00:00+00:00",
  "channel": {
    "id": "...",
    "name": "general",
    "display_name": "General",
    "type": "O",
    "purpose": "...",
    "team": "Acme Corp",
    "created_at": "..."
  },
  "message_count": 1234,
  "messages": [
    {
      "id": "...",
      "created_at": "2026-01-15T09:32:00+00:00",
      "updated_at": null,
      "user": {
        "id": "...",
        "username": "alice",
        "first_name": "Alice",
        "last_name": "Smith",
        "nickname": "",
        "email": "alice@example.com"
      },
      "message": "Hello everyone! :wave:",
      "reactions": [
        { "emoji": "thumbsup", "count": 3, "users": ["bob", "carol", "dave"] }
      ],
      "files": [
        {
          "id": "...",
          "name": "report.pdf",
          "mime_type": "application/pdf",
          "size": 48320
        }
      ],
      "links": [{ "type": "opengraph", "url": "https://...", "title": "..." }],
      "thread": [
        {
          "id": "...",
          "created_at": "...",
          "user": { "username": "bob", "...": "..." },
          "message": "Great!",
          "reactions": [],
          "files": [],
          "links": []
        }
      ]
    }
  ]
}
```

## Render a proper HTML page with a channel's history — `to_html.py`

Converts the JSON export into a fully self-contained HTML file (no external dependencies, works offline).

```bash
uv run --env-file .env to_html.py [input.json] [output.html]

# defaults:
uv run --env-file .env to_html.py
# reads channel_export.json → writes channel_archive.html
```

### Features

- Dark theme (Discord-style), clean and readable
- Sidebar with channel info, message count, and month-by-month navigation
- Messages grouped by date with dividers
- User avatars with initials, color-coded by username
- Real Unicode emoji in reactions and message text (`:thumbsup:` → 👍)
- Markdown rendering: bold, italic, strikethrough, inline code, code blocks, blockquotes, headings, horizontal rules, **tables**
- Reactions shown as pills with user list on hover
- File attachments displayed as pills with size
- Link embeds with title and description
- Thread replies collapsed by default, expandable inline
- Live search bar — filters messages and highlights matches in real-time
- Zebra-striped, horizontally-scrollable tables

