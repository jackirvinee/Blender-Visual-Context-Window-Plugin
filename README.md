# Claude Context Window Progress Bar

A small, unobtrusive progress bar injected into the **Claude desktop app** (macOS) that shows how much of the context window has been used in each conversation. Helps you know when to compact a chat or start a new one.

![Usage levels: green → yellow → orange → red](https://img.shields.io/badge/0--50%25-green-22c55e) ![](https://img.shields.io/badge/50--75%25-yellow-eab308) ![](https://img.shields.io/badge/75--90%25-orange-f97316) ![](https://img.shields.io/badge/90--100%25-red-ef4444)

## What It Does

- Adds a **thin 3px bar** at the top of the chat window
- **Color-coded** so you can tell at a glance: green (plenty of room) → yellow → orange → red (full)
- **Hover** to see exact token counts: `42.1k / 200k tokens (21%) · claude-sonnet-4`
- **Pulses** when context is >85% full as a nudge to compact or start fresh
- Tracks each conversation separately
- Works across Chat, Cowork, and Code modes in the Claude desktop app

## How It Works

The Claude desktop app is an Electron app. This tool:

1. Extracts the app's `app.asar` archive into an `app/` directory (Electron automatically prefers the directory over the archive)
2. Injects a small JavaScript + CSS file into the app's HTML
3. The JavaScript intercepts streaming API responses to read real token usage data — no estimation or guessing

**Fully reversible** — uninstalling just deletes the `app/` directory and the original `app.asar` takes over.

## Requirements

- **macOS** with Claude desktop app installed at `/Applications/Claude.app`
- **Python 3.6+** (no additional packages needed — pure Python, zero dependencies)

## Installation

```bash
# Clone the repository
git clone https://github.com/jackirvinee/Blender-Visual-Context-Window-Plugin.git
cd Blender-Visual-Context-Window-Plugin

# Install (may need sudo depending on /Applications permissions)
python3 install.py

# Restart Claude (Cmd+Q, then reopen)
```

The progress bar will appear at the top of the chat window after you send your first message.

## Uninstallation

```bash
python3 uninstall.py

# Restart Claude (Cmd+Q, then reopen)
```

This removes the injected `app/` directory. The Claude app falls back to its original `app.asar` — completely restored.

## How the Progress Bar Looks

| Usage Level | Color  | Meaning                        |
|-------------|--------|--------------------------------|
| 0–50%       | Green  | Plenty of room                 |
| 50–75%      | Yellow | Getting used                   |
| 75–90%      | Orange | Consider compacting soon       |
| 90–100%     | Red    | Chat is full — compact or new  |

The bar is just **3px tall** — barely visible until you need it. Hover to expand and see details.

## File Structure

```
├── install.py          # Installer script
├── uninstall.py        # Uninstaller script
├── lib/
│   ├── __init__.py
│   └── asar_reader.py  # Pure Python ASAR archive extractor
├── src/
│   ├── context_bar.js  # Fetch interceptor + progress bar renderer
│   └── context_bar.css # Progress bar styling
└── README.md
```

## Notes

- **App updates**: When the Claude app updates, it replaces `app.asar`. If an `app/` directory exists, Electron still uses it — but it will be running old code. Re-run `install.py` after Claude updates to re-extract the new version.
- **No data leaves your machine**: The plugin only reads token counts from API responses that are already flowing through the app. It doesn't make any additional network requests.
- **Error isolation**: All injected code is wrapped in try/catch blocks. If anything goes wrong, the original app functionality is never affected.

## License

MIT
