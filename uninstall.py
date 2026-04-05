#!/usr/bin/env python3
"""
Uninstaller for the Claude Context Usage MCP Server.

Removes the context-usage MCP server entry from the Claude desktop config.
"""

import json
import sys
import os
from pathlib import Path


def get_claude_config_path() -> Path:
    """Get the path to the Claude desktop app's MCP config file."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    else:
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def uninstall():
    """Remove the context-usage MCP server from the Claude desktop config."""
    config_path = get_claude_config_path()

    print("=" * 60)
    print("  Claude Context Usage — Uninstaller")
    print("=" * 60)
    print()

    if not config_path.exists():
        print("  Config file not found. Nothing to uninstall.")
        return

    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError:
        print("  ⚠ Config file is invalid JSON. Cannot uninstall automatically.")
        print(f"  Please manually edit: {config_path}")
        return

    servers = config.get("mcpServers", {})
    if "context-usage" not in servers:
        print("  'context-usage' server not found in config. Nothing to uninstall.")
        return

    del servers["context-usage"]

    # Clean up empty mcpServers key
    if not servers:
        del config["mcpServers"]

    config_path.write_text(json.dumps(config, indent=2) + "\n")

    print("  ✓ Removed 'context-usage' MCP server from config")
    print()
    print("  Restart the Claude desktop app to complete uninstall.")
    print()


if __name__ == "__main__":
    uninstall()
