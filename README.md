# Claude Context Window Usage — MCP Server

A lightweight MCP server that shows you how much of the context window has been used in your Claude desktop app conversations. Helps you know when to compact a chat or start a new one.

**Zero risk** — read-only, doesn't modify the Claude app. Just adds a config entry.

## What It Does

When you ask Claude to "check my context usage", it calls the `check_context_usage` tool and shows you:

```
## Context Window Usage 🟡

  ████████████████░░░░░░░░░░░░░░  53.2%

108,450 / 200,000 tokens used
Model: claude-sonnet-4-20250514
Status: Getting used

ℹ️ This chat is about half full. You have room for more exchanges.
```

The progress bar color tells you at a glance:
- 🟢 **Green** (0-50%): Plenty of room
- 🟡 **Yellow** (50-75%): Getting used
- 🟠 **Orange** (75-90%): Consider compacting soon
- 🔴 **Red** (90-100%): Chat is full — compact or start new

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

This is an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that the Claude desktop app connects to natively. It provides a single tool — `check_context_usage` — that Claude calls when you ask about context usage.

The server:
1. Accepts token count estimates from Claude (which has awareness of conversation length)
2. Tries to read actual token data from the Claude app's local storage (if accessible)
3. Returns a formatted progress bar with actionable advice

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

Any of these will make Claude call the tool:
- "Check my context usage"
- "How full is this chat?"
- "Should I start a new conversation?"
- "How much context is left?"
- "Am I running out of context?"

## License

MIT
