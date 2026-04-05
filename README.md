# Claude Context Window Manager — MCP Server

A lightweight MCP server that tracks, manages, and optimizes context window usage in your Claude desktop app conversations. Know when to compact, get carry-over summaries, and never lose important info.

**Zero risk** — read-only, doesn't modify the Claude app. Just adds a config entry.

## Tools

### 1. Check Context Usage
> "How full is this chat?"

```
## Context Window Usage 🟡

  ████████████████░░░░░░░░░░░░░░  53.2%

108,450 / 200,000 tokens used
Model: claude-sonnet-4-20250514
Status: Getting used

ℹ️ This chat is about half full. You have room for more exchanges.
```

Color-coded at a glance:
- 🟢 **Green** (0-50%): Plenty of room
- 🟡 **Yellow** (50-75%): Getting used
- 🟠 **Orange** (75-90%): Consider compacting soon
- 🔴 **Red** (90-100%): Chat is full — compact or start new

### 2. Summarize for New Chat
> "Summarize this chat so I can continue in a new one"

Generates a portable summary you can paste into a fresh conversation — includes the goal, decisions made, current progress, key files, and next steps. No more "where was I?" when starting over.

### 3. Export Key Info
> "Export the important stuff from this chat"

Extracts and organizes: decisions made, code snippets, action items, links, and configuration details into a clean reference doc you can save.

### 4. Suggest Compaction
> "What can I drop from this chat to free up space?"

Analyzes the conversation and categorizes it (debugging, setup, planning, etc.), showing which parts can be safely dropped vs. what needs to be kept. Includes token estimates and savings.

## Install

```bash
git clone https://github.com/jackirvinee/Blender-Visual-Context-Window-Plugin.git
cd Blender-Visual-Context-Window-Plugin
python3 install.py
```

Then:
1. **Quit** the Claude desktop app (Cmd+Q on Mac)
2. **Reopen** Claude
3. In any chat, type: **"check my context usage"**

## Uninstall

```bash
python3 uninstall.py
```

Then restart Claude. The config entry is removed and everything is back to normal.

## How It Works

This is an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that the Claude desktop app connects to natively. It provides 4 tools that Claude calls when you ask about context:

| Tool | Trigger | What it does |
|------|---------|-------------|
| `check_context_usage` | "How full is this chat?" | Shows progress bar + advice |
| `summarize_for_new_chat` | "Summarize for a new chat" | Generates carry-over summary |
| `export_key_info` | "Export the important stuff" | Extracts decisions, code, TODOs |
| `suggest_compaction` | "What can I drop?" | Analyzes what's safe to remove |

## Requirements

- Python 3.10+
- Claude desktop app (macOS, Windows, or Linux)
- No additional Python packages needed — uses only the standard library

## Manual Configuration

If you prefer to configure manually, add this to your Claude desktop config:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%/Claude/claude_desktop_config.json`
**Linux:** `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "context-usage": {
      "command": "python3",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```

## Phrases That Trigger It

**Check usage:**
- "Check my context usage"
- "How full is this chat?"
- "Am I running out of context?"

**Manage context:**
- "Summarize this chat so I can continue in a new one"
- "Export the important stuff from this conversation"
- "What can I drop from this chat to free up space?"
- "Help me compact this conversation"

## License

MIT
