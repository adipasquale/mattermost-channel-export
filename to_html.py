#!/usr/bin/env python3
"""
Convert a Mattermost channel export JSON (produced by export.py) to a
self-contained, beautiful static HTML archive.

Usage:
    python to_html.py [input.json] [output.html]

Defaults:
    input  : channel_export.json
    output : channel_archive.html

Dependencies:
    pip install emoji
"""

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import emoji as _emoji_lib

    def to_emoji(shortcode: str) -> str:
        """Convert a Mattermost emoji shortcode (without colons) to a Unicode emoji."""
        result = _emoji_lib.emojize(f":{shortcode}:", language="alias")
        # emojize returns the original string unchanged when not found
        return result if result != f":{shortcode}:" else f":{shortcode}:"

    def emojize_text(text: str) -> str:
        """Convert all :shortcode: patterns in a string to Unicode emojis."""
        return _emoji_lib.emojize(text, language="alias")

except ImportError:
    print("Warning: 'emoji' package not installed — run: pip install emoji", file=sys.stderr)

    def to_emoji(shortcode: str) -> str:  # type: ignore[misc]
        return f":{shortcode}:"

    def emojize_text(text: str) -> str:  # type: ignore[misc]
        return text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%-d %b %Y")
    except Exception:
        return iso


def fmt_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%H:%M")
    except Exception:
        return ""


def fmt_datetime(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%-d %b %Y at %H:%M UTC")
    except Exception:
        return iso


def avatar_initials(user: dict) -> str:
    first = (user.get("first_name") or "").strip()
    last = (user.get("last_name") or "").strip()
    if first and last:
        return (first[0] + last[0]).upper()
    username = user.get("username", "?")
    return username[:2].upper()


def avatar_color(username: str) -> str:
    colors = [
        "#5865F2", "#3BA55C", "#FAA61A", "#ED4245", "#EB459E",
        "#57F287", "#FEE75C", "#EB459E", "#9B59B6", "#1ABC9C",
        "#E67E22", "#E74C3C", "#3498DB", "#2ECC71", "#F39C12",
    ]
    idx = sum(ord(c) for c in username) % len(colors)
    return colors[idx]


def display_name(user: dict) -> str:
    first = (user.get("first_name") or "").strip()
    last = (user.get("last_name") or "").strip()
    nick = (user.get("nickname") or "").strip()
    if nick:
        return nick
    if first or last:
        return f"{first} {last}".strip()
    return user.get("username", "unknown")


URL_RE = re.compile(
    r"(https?://[^\s<>\"\')]+)",
    re.IGNORECASE,
)

MD_CODE_BLOCK = re.compile(r"```(\w*)\n?(.*?)```", re.DOTALL)
MD_INLINE_CODE = re.compile(r"`([^`]+)`")
MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
MD_ITALIC = re.compile(r"\*(.+?)\*")
MD_STRIKE = re.compile(r"~~(.+?)~~")
MD_H1 = re.compile(r"^# (.+)$", re.MULTILINE)
MD_H2 = re.compile(r"^## (.+)$", re.MULTILINE)
MD_H3 = re.compile(r"^### (.+)$", re.MULTILINE)
MD_BLOCKQUOTE = re.compile(r"^> (.+)$", re.MULTILINE)
MD_HR = re.compile(r"^---+$", re.MULTILINE)


def _render_table(raw: str) -> str:
    """Convert a raw Markdown table (unescaped) to an HTML table string."""
    lines = [l.strip() for l in raw.strip().splitlines()]
    if len(lines) < 2:
        return html.escape(raw)

    def split_row(line: str) -> list[str]:
        return [c.strip() for c in line.strip("|").split("|")]

    headers = split_row(lines[0])
    # lines[1] is the separator row (---|---) — skip it
    body_lines = lines[2:]

    th_cells = "".join(f"<th>{html.escape(emojize_text(c))}</th>" for c in headers)
    thead = f"<thead><tr>{th_cells}</tr></thead>"

    rows = []
    for line in body_lines:
        if not line.strip():
            continue
        cells = split_row(line)
        # Pad or trim to match header count
        while len(cells) < len(headers):
            cells.append("")
        td_cells = "".join(f"<td>{html.escape(emojize_text(c))}</td>" for c in cells[: len(headers)])
        rows.append(f"<tr>{td_cells}</tr>")
    tbody = f"<tbody>{''.join(rows)}</tbody>"

    return f'<div class="table-wrap"><table>{thead}{tbody}</table></div>'


# A table block: header row | separator row (must contain ---) | 0+ data rows
_MD_TABLE = re.compile(
    r"(\|.+\|\n\|[-| :]+\|\n(?:\|.+\|\n?)*)",
    re.MULTILINE,
)


def render_message(text: str) -> str:
    """Lightweight Markdown-to-HTML renderer for Mattermost messages."""
    stash: list[str] = []

    def stash_block(block: str) -> str:
        stash.append(block)
        return f"\x00STASH{len(stash) - 1}\x00"

    # Stash code blocks first (protect their content from all further processing)
    def stash_code_block(m: re.Match) -> str:
        lang = html.escape(m.group(1))
        code = html.escape(m.group(2).rstrip())
        return stash_block(f'<pre><code class="language-{lang}">{code}</code></pre>')

    text = MD_CODE_BLOCK.sub(stash_code_block, text)

    # Stash tables (render from raw text before html.escape touches them)
    text = _MD_TABLE.sub(lambda m: stash_block(_render_table(m.group(1))), text)

    # Convert :shortcode: emoji before HTML-escaping (Unicode is safe in HTML)
    text = emojize_text(text)

    # Escape HTML in the remaining text
    text = html.escape(text)

    # Inline code
    text = MD_INLINE_CODE.sub(lambda m: f"<code>{html.escape(m.group(1))}</code>", text)

    # Headings
    text = MD_H1.sub(lambda m: f"<h4>{m.group(1)}</h4>", text)
    text = MD_H2.sub(lambda m: f"<h5>{m.group(1)}</h5>", text)
    text = MD_H3.sub(lambda m: f"<h6>{m.group(1)}</h6>", text)

    # Blockquote
    text = MD_BLOCKQUOTE.sub(lambda m: f"<blockquote>{m.group(1)}</blockquote>", text)

    # Horizontal rule
    text = MD_HR.sub("<hr>", text)

    # Bold / italic / strikethrough
    text = MD_BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", text)
    text = MD_ITALIC.sub(lambda m: f"<em>{m.group(1)}</em>", text)
    text = MD_STRIKE.sub(lambda m: f"<del>{m.group(1)}</del>", text)

    # URLs → clickable links
    text = URL_RE.sub(
        lambda m: f'<a href="{m.group(1)}" target="_blank" rel="noopener">{m.group(1)}</a>',
        text,
    )

    # Line breaks → <br> (but not inside block elements already rendered)
    text = text.replace("\n", "<br>")

    # Restore all stashed blocks
    for i, block in enumerate(stash):
        text = text.replace(f"\x00STASH{i}\x00", block)

    return text


# ---------------------------------------------------------------------------
# HTML component builders
# ---------------------------------------------------------------------------

def h(tag: str, content: str, **attrs) -> str:
    attr_str = " ".join(f'{k.rstrip("_")}="{v}"' for k, v in attrs.items())
    return f"<{tag} {attr_str}>{content}</{tag}>" if attr_str else f"<{tag}>{content}</{tag}>"


def render_avatar(user: dict, size: str = "md") -> str:
    color = avatar_color(user.get("username", ""))
    initials = avatar_initials(user)
    return f'<div class="avatar avatar-{size}" style="background:{color}" title="{html.escape(display_name(user))}">{initials}</div>'


def render_reactions(reactions: list[dict]) -> str:
    if not reactions:
        return ""
    items = []
    for r in reactions:
        users_tip = html.escape(", ".join(r.get("users", [])))
        shortcode = r.get("emoji", "")
        glyph = html.escape(to_emoji(shortcode))
        count = r.get("count", 0)
        items.append(
            f'<span class="reaction" title="{users_tip}">{glyph} {count}</span>'
        )
    return f'<div class="reactions">{"".join(items)}</div>'


def render_files(files: list[dict]) -> str:
    if not files:
        return ""
    items = []
    for f in files:
        name = html.escape(f.get("name", "file"))
        mime = f.get("mime_type", "")
        size = f.get("size", 0)
        size_str = f"{size // 1024} KB" if size else ""
        icon = "🖼" if mime.startswith("image/") else "📎"
        items.append(f'<div class="file-pill">{icon} <span class="file-name">{name}</span><span class="file-size">{size_str}</span></div>')
    return f'<div class="files">{"".join(items)}</div>'


def render_links(links: list[dict]) -> str:
    if not links:
        return ""
    items = []
    for lnk in links:
        url = html.escape(lnk.get("url") or "")
        title = html.escape(lnk.get("title") or url)
        desc = html.escape(lnk.get("description") or "")
        if not url:
            continue
        desc_html = f'<p class="embed-desc">{desc}</p>' if desc else ""
        items.append(
            f'<div class="embed">'
            f'<a class="embed-title" href="{url}" target="_blank" rel="noopener">{title}</a>'
            f'{desc_html}'
            f'</div>'
        )
    return "".join(items)


def render_thread(replies: list[dict]) -> str:
    if not replies:
        return ""
    items = []
    for msg in replies:
        user = msg.get("user", {})
        items.append(
            f'<div class="reply">'
            f'{render_avatar(user, "sm")}'
            f'<div class="reply-body">'
            f'<span class="reply-author">{html.escape(display_name(user))}</span>'
            f'<span class="reply-time" title="{html.escape(msg.get("created_at",""))}">{fmt_time(msg.get("created_at",""))}</span>'
            f'<div class="reply-text">{render_message(msg.get("message",""))}</div>'
            f'{render_reactions(msg.get("reactions",[]))}'
            f'{render_files(msg.get("files",[]))}'
            f'</div>'
            f'</div>'
        )
    count = len(replies)
    label = f"{count} repl{'ies' if count > 1 else 'y'}"
    return (
        f'<div class="thread">'
        f'<button class="thread-toggle" onclick="toggleThread(this)">'
        f'<span class="thread-icon">▶</span> {label}'
        f'</button>'
        f'<div class="thread-replies hidden">{"".join(items)}</div>'
        f'</div>'
    )


def render_message_card(msg: dict, is_reply: bool = False) -> str:
    user = msg.get("user", {})
    created = msg.get("created_at", "")
    updated = msg.get("updated_at")
    edited_badge = ' <span class="edited">(edited)</span>' if updated and updated != created else ""

    thread_html = render_thread(msg.get("thread", []))

    return (
        f'<div class="message" id="msg-{html.escape(msg.get("id",""))}">'
        f'{render_avatar(user)}'
        f'<div class="message-body">'
        f'<div class="message-header">'
        f'<span class="author">{html.escape(display_name(user))}</span>'
        f'<span class="username">@{html.escape(user.get("username",""))}</span>'
        f'<span class="timestamp" title="{html.escape(created)}">{fmt_time(created)}</span>'
        f'{edited_badge}'
        f'</div>'
        f'<div class="message-text">{render_message(msg.get("message",""))}</div>'
        f'{render_files(msg.get("files",[]))}'
        f'{render_links(msg.get("links",[]))}'
        f'{render_reactions(msg.get("reactions",[]))}'
        f'{thread_html}'
        f'</div>'
        f'</div>'
    )


def group_by_date(messages: list[dict]) -> list[tuple[str, list[dict]]]:
    groups: list[tuple[str, list[dict]]] = []
    current_date = ""
    current_msgs: list[dict] = []
    for msg in messages:
        d = fmt_date(msg.get("created_at", ""))
        if d != current_date:
            if current_msgs:
                groups.append((current_date, current_msgs))
            current_date = d
            current_msgs = []
        current_msgs.append(msg)
    if current_msgs:
        groups.append((current_date, current_msgs))
    return groups


# ---------------------------------------------------------------------------
# Full HTML document
# ---------------------------------------------------------------------------

CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg: #1e1f22;
  --bg2: #2b2d31;
  --bg3: #313338;
  --surface: #383a40;
  --border: #3f4147;
  --text: #dbdee1;
  --text-muted: #80848e;
  --text-link: #00a8fc;
  --accent: #5865f2;
  --thread-bg: #2e3035;
  --reply-border: #5865f2;
  --code-bg: #1e1f22;
  --radius: 8px;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}

body {
  font-family: var(--font);
  font-size: 15px;
  line-height: 1.5;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
}

/* Layout */
.layout { display: flex; min-height: 100vh; }

.sidebar {
  width: 260px;
  flex-shrink: 0;
  background: var(--bg2);
  border-right: 1px solid var(--border);
  padding: 24px 16px;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
}

.main {
  flex: 1;
  max-width: 900px;
  padding: 0 24px 60px;
}

/* Sidebar */
.sidebar-title { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; color: var(--text-muted); margin-bottom: 12px; }
.channel-name { font-size: 16px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
.channel-name::before { content: "# "; color: var(--text-muted); }
.channel-meta { font-size: 12px; color: var(--text-muted); line-height: 1.8; margin-top: 8px; }
.channel-meta span { display: block; }
.channel-purpose { margin-top: 12px; font-size: 13px; color: var(--text-muted); border-top: 1px solid var(--border); padding-top: 12px; }
.stat-box { background: var(--bg3); border-radius: var(--radius); padding: 12px; margin-top: 16px; }
.stat-num { font-size: 28px; font-weight: 800; color: var(--accent); }
.stat-label { font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .06em; }
.toc { margin-top: 20px; }
.toc-item { display: block; font-size: 12px; color: var(--text-muted); text-decoration: none; padding: 3px 0; }
.toc-item:hover { color: var(--text); }

/* Channel header */
.channel-header {
  padding: 28px 0 20px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}
.channel-header h1 { font-size: 22px; font-weight: 800; }
.channel-header h1::before { content: "# "; color: var(--text-muted); font-weight: 400; }
.channel-header .meta { font-size: 13px; color: var(--text-muted); margin-top: 4px; }

/* Date divider */
.date-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 0 8px;
}
.date-divider::before, .date-divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--border);
}
.date-divider span {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  white-space: nowrap;
}

/* Message */
.message {
  display: flex;
  gap: 14px;
  padding: 6px 8px;
  border-radius: var(--radius);
  transition: background .1s;
}
.message:hover { background: var(--bg2); }

/* Avatar */
.avatar {
  flex-shrink: 0;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  color: #fff;
  font-size: 13px;
  user-select: none;
}
.avatar-md { width: 40px; height: 40px; font-size: 13px; }
.avatar-sm { width: 28px; height: 28px; font-size: 10px; }

/* Message body */
.message-body { flex: 1; min-width: 0; }
.message-header { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; margin-bottom: 2px; }
.author { font-weight: 700; font-size: 15px; }
.username { font-size: 12px; color: var(--text-muted); }
.timestamp { font-size: 11px; color: var(--text-muted); margin-left: auto; }
.edited { font-size: 11px; color: var(--text-muted); }

.message-text { color: var(--text); word-break: break-word; }
.message-text a { color: var(--text-link); text-decoration: none; }
.message-text a:hover { text-decoration: underline; }
.message-text code { background: var(--code-bg); padding: 1px 5px; border-radius: 4px; font-family: var(--mono); font-size: 13px; }
.message-text pre { background: var(--code-bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 16px; overflow-x: auto; margin: 8px 0; }
.message-text pre code { background: none; padding: 0; font-size: 13px; }
.message-text blockquote { border-left: 4px solid var(--accent); padding-left: 12px; color: var(--text-muted); margin: 6px 0; }
.message-text h4, .message-text h5, .message-text h6 { margin: 8px 0 4px; }
.message-text hr { border: none; border-top: 1px solid var(--border); margin: 8px 0; }
.table-wrap { overflow-x: auto; margin: 8px 0; }
table { border-collapse: collapse; font-size: 13px; min-width: 100%; }
th, td { border: 1px solid var(--border); padding: 6px 12px; text-align: left; }
th { background: var(--surface); font-weight: 600; color: var(--text); }
td { background: var(--bg3); color: var(--text); }
tr:nth-child(even) td { background: var(--bg2); }

/* Reactions */
.reactions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.reaction {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 2px 10px;
  font-size: 13px;
  cursor: default;
  transition: background .1s;
}
.reaction:hover { background: var(--bg3); }

/* Files */
.files { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.file-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 12px;
  font-size: 13px;
}
.file-name { font-weight: 500; }
.file-size { color: var(--text-muted); font-size: 11px; }

/* Embeds */
.embed {
  border-left: 4px solid var(--accent);
  background: var(--surface);
  border-radius: 0 var(--radius) var(--radius) 0;
  padding: 10px 14px;
  margin-top: 8px;
  max-width: 520px;
}
.embed-title { color: var(--text-link); font-weight: 600; font-size: 14px; text-decoration: none; display: block; }
.embed-title:hover { text-decoration: underline; }
.embed-desc { font-size: 13px; color: var(--text-muted); margin-top: 4px; }

/* Thread */
.thread { margin-top: 8px; }
.thread-toggle {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--accent);
  font-size: 13px;
  font-weight: 600;
  padding: 4px 0;
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font);
}
.thread-toggle:hover { text-decoration: underline; }
.thread-icon { font-size: 10px; transition: transform .2s; }
.thread-toggle.open .thread-icon { transform: rotate(90deg); }

.thread-replies {
  border-left: 2px solid var(--reply-border);
  margin-left: 4px;
  padding-left: 16px;
  margin-top: 8px;
}
.thread-replies.hidden { display: none; }

.reply { display: flex; gap: 10px; padding: 4px 0; }
.reply-body { flex: 1; min-width: 0; }
.reply-author { font-weight: 700; font-size: 13px; }
.reply-time { font-size: 11px; color: var(--text-muted); margin-left: 8px; }
.reply-text { font-size: 14px; word-break: break-word; }
.reply-text a { color: var(--text-link); text-decoration: none; }

/* Search */
.search-wrap { padding: 20px 0 0; position: sticky; top: 0; background: var(--bg); z-index: 10; border-bottom: 1px solid var(--border); margin-bottom: 0; }
.search-input {
  width: 100%;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 14px;
  color: var(--text);
  font-size: 14px;
  font-family: var(--font);
  outline: none;
  margin-bottom: 12px;
}
.search-input:focus { border-color: var(--accent); }
.search-input::placeholder { color: var(--text-muted); }
#search-count { font-size: 12px; color: var(--text-muted); padding: 0 2px 10px; min-height: 20px; }
.highlight { background: #faa61a55; border-radius: 2px; }

/* Footer */
.footer { font-size: 11px; color: var(--text-muted); text-align: center; padding: 24px 0 12px; border-top: 1px solid var(--border); margin-top: 24px; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
"""

JS = """
function toggleThread(btn) {
  btn.classList.toggle('open');
  const replies = btn.nextElementSibling;
  replies.classList.toggle('hidden');
}

(function() {
  const input = document.getElementById('search-input');
  const count = document.getElementById('search-count');
  if (!input) return;

  input.addEventListener('input', function() {
    const q = input.value.trim().toLowerCase();
    const messages = document.querySelectorAll('.message');
    let visible = 0;

    messages.forEach(function(msg) {
      const textEl = msg.querySelector('.message-text');
      const authorEl = msg.querySelector('.author');
      const rawText = (textEl ? textEl.textContent : '') + ' ' + (authorEl ? authorEl.textContent : '');

      if (!q) {
        msg.style.display = '';
        if (textEl) textEl.innerHTML = textEl.innerHTML.replace(/<mark class="highlight">([^<]+)<\\/mark>/g, '$1');
        visible++;
        return;
      }

      if (rawText.toLowerCase().includes(q)) {
        msg.style.display = '';
        visible++;
        if (textEl) {
          // simple highlight — replace text nodes only
          const re = new RegExp('(' + q.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&') + ')', 'gi');
          textEl.innerHTML = textEl.innerHTML
            .replace(/<mark class="highlight">([^<]+)<\\/mark>/g, '$1')
            .replace(/(<[^>]+>)|([^<]+)/g, function(m, tag, text) {
              return tag ? tag : text.replace(re, '<mark class="highlight">$1</mark>');
            });
        }
      } else {
        msg.style.display = 'none';
      }
    });

    count.textContent = q ? visible + ' message' + (visible !== 1 ? 's' : '') + ' matched' : '';
  });
})();
"""


def build_html(data: dict) -> str:
    channel = data.get("channel", {})
    messages = data.get("messages", [])
    exported_at = data.get("exported_at", "")
    ch_name = html.escape(channel.get("display_name") or channel.get("name", "Channel"))
    ch_handle = html.escape(channel.get("name", ""))
    team = html.escape(channel.get("team", ""))
    purpose = html.escape(channel.get("purpose", "") or channel.get("header", ""))
    msg_count = len(messages)

    # Sidebar TOC — one entry per month
    month_anchors: dict[str, str] = {}
    for msg in messages:
        d = msg.get("created_at", "")
        try:
            dt = datetime.fromisoformat(d)
            key = dt.strftime("%Y-%m")
            label = dt.strftime("%B %Y")
            if key not in month_anchors:
                month_anchors[key] = label
        except Exception:
            pass

    toc_html = "\n".join(
        f'<a class="toc-item" href="#month-{k}">▸ {v}</a>'
        for k, v in month_anchors.items()
    )

    # Message groups
    groups = group_by_date(messages)
    body_parts: list[str] = []

    prev_month = ""
    for date_label, msgs in groups:
        # Month anchor for TOC
        if msgs:
            d = msgs[0].get("created_at", "")
            try:
                dt = datetime.fromisoformat(d)
                month_key = dt.strftime("%Y-%m")
                if month_key != prev_month:
                    body_parts.append(f'<div id="month-{month_key}"></div>')
                    prev_month = month_key
            except Exception:
                pass

        body_parts.append(
            f'<div class="date-divider"><span>{html.escape(date_label)}</span></div>'
        )
        for msg in msgs:
            body_parts.append(render_message_card(msg))

    body_html = "\n".join(body_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>#{ch_handle} — Mattermost Archive</title>
<style>{CSS}</style>
</head>
<body>
<div class="layout">
  <nav class="sidebar">
    <div class="sidebar-title">Archive</div>
    <div class="channel-name">{ch_name}</div>
    <div class="channel-meta">
      {'<span>Team: ' + team + '</span>' if team else ''}
      <span>Exported: {html.escape(fmt_datetime(exported_at))}</span>
    </div>
    {'<div class="channel-purpose">' + purpose + '</div>' if purpose else ''}
    <div class="stat-box">
      <div class="stat-num">{msg_count:,}</div>
      <div class="stat-label">Messages</div>
    </div>
    <div class="toc">{toc_html}</div>
  </nav>

  <div class="main">
    <div class="channel-header">
      <h1>{ch_name}</h1>
      <div class="meta">{html.escape(fmt_datetime(exported_at))} · {msg_count:,} messages</div>
    </div>

    <div class="search-wrap">
      <input id="search-input" class="search-input" type="search" placeholder="Search messages…" autocomplete="off">
      <div id="search-count"></div>
    </div>

    {body_html}

    <div class="footer">
      Mattermost channel archive — #{ch_handle}<br>
      Generated {html.escape(fmt_datetime(exported_at))}
    </div>
  </div>
</div>
<script>{JS}</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]
    input_file = Path(args[0]) if args else Path("channel_export.json")
    output_file = Path(args[1]) if len(args) > 1 else Path("channel_archive.html")

    if not input_file.exists():
        sys.exit(f"ERROR: input file not found: {input_file}")

    print(f"Reading {input_file} …")
    with input_file.open(encoding="utf-8") as f:
        data = json.load(f)

    print(f"Rendering HTML …")
    html_content = build_html(data)

    output_file.write_text(html_content, encoding="utf-8")
    size_kb = output_file.stat().st_size // 1024
    print(f"Done. Written to {output_file} ({size_kb} KB)")


if __name__ == "__main__":
    main()
