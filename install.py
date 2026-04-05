#!/usr/bin/env python3
"""
Installer for the Claude Context Usage MCP Server.

Configures the Claude desktop app to connect to this MCP server
by adding it to the app's MCP configuration file.

Safe and reversible — only adds a config entry, doesn't modify the app.
Run uninstall.py to remove.
"""

import json
import os
import sys
import shutil
from pathlib import Path


def get_claude_config_path() -> Path:
    """Get the path to the Claude desktop app's MCP config file."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    else:
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def get_server_path() -> str:
    """Get the absolute path to the MCP server script."""
    return str(Path(__file__).parent.resolve() / "server.py")


def get_python_path() -> str:
    """Get the path to the Python interpreter."""
    return sys.executable


def install():
    """Add the context-usage MCP server to the Claude desktop config."""
    config_path = get_claude_config_path()
    server_path = get_server_path()
    python_path = get_python_path()

    print("=" * 60)
    print("  Claude Context Usage — MCP Server Installer")
    print("=" * 60)
    print()
    print(f"  Config file:  {config_path}")
    print(f"  Server:       {server_path}")
    print(f"  Python:       {python_path}")
    print()

    # Load or create config
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            print(f"  ✓ Found existing config file")
        except json.JSONDecodeError:
            print(f"  ⚠ Config file exists but is invalid JSON, creating backup...")
            backup = config_path.with_suffix(".json.backup")
            shutil.copy2(config_path, backup)
            print(f"  ✓ Backup saved to {backup}")
            config = {}
    else:
        print(f"  Creating new config file...")
        config_path.parent.mkdir(parents=True, exist_ok=True)

    # Add MCP server entry
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    if "context-usage" in config["mcpServers"]:
        print(f"  ⚠ 'context-usage' server already configured. Updating...")

    config["mcpServers"]["context-usage"] = {
        "command": python_path,
        "args": [server_path],
    }

    # Write config
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    print(f"  ✓ MCP server configured successfully!")
    print()
    print("=" * 60)
    print("  NEXT STEPS")
    print("=" * 60)
    print()
    print("  1. Quit the Claude desktop app (Cmd+Q)")
    print("  2. Reopen Claude")
    print('  3. In any chat, type: "check my context usage"')
    print()
    print("  Claude will call the context-usage tool and show you")
    print("  a progress bar of how full your chat is.")
    print()
    print("  To uninstall: python3 uninstall.py")
    print()


if __name__ == "__main__":
    install()
