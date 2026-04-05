#!/usr/bin/env python3
"""
Claude Context Window Usage — MCP Server

An MCP server that provides a context usage checking tool for the Claude desktop app.
Reads the Claude app's local conversation data to estimate token usage and returns
a visual progress bar showing how full the current chat is.

Zero risk: read-only, doesn't modify the Claude app in any way.
"""

import json
import os
import sys
import sqlite3
import struct
import glob
import time
from pathlib import Path
from datetime import datetime

# MCP protocol constants
JSONRPC_VERSION = "2.0"

# Model context window limits (tokens)
MODEL_LIMITS = {
    "claude-opus-4": 200_000,
    "claude-sonnet-4": 200_000,
    "claude-haiku-4": 200_000,
    "claude-sonnet-3.5": 200_000,
    "claude-haiku-3.5": 200_000,
    "claude-opus-3": 200_000,
    "claude-sonnet-3": 200_000,
    "default": 200_000,
}

# Color thresholds for the progress bar
THRESHOLDS = [
    (0.50, "🟢", "green",  "Plenty of room"),
    (0.75, "🟡", "yellow", "Getting used"),
    (0.90, "🟠", "orange", "Consider compacting soon"),
    (1.00, "🔴", "red",    "Chat is full — compact or start new"),
]


def get_model_limit(model_name: str) -> int:
    """Get the context window limit for a given model."""
    if not model_name:
        return MODEL_LIMITS["default"]
    name = model_name.lower()
    for key, limit in MODEL_LIMITS.items():
        if key in name:
            return limit
    return MODEL_LIMITS["default"]


def get_color_info(ratio: float):
    """Get the color/status info for a given usage ratio."""
    for threshold, emoji, color, status in THRESHOLDS:
        if ratio <= threshold:
            return emoji, color, status
    return THRESHOLDS[-1][1], THRESHOLDS[-1][2], THRESHOLDS[-1][3]


def format_tokens(n: int) -> str:
    """Format a token count with commas."""
    return f"{n:,}"


def build_progress_bar(used: int, limit: int, model: str = "", width: int = 30) -> str:
    """Build a text-based progress bar showing context usage."""
    ratio = min(used / limit, 1.0) if limit > 0 else 0
    pct = ratio * 100
    emoji, color, status = get_color_info(ratio)

    filled = int(width * ratio)
    empty = width - filled
    bar = "█" * filled + "░" * empty

    lines = []
    lines.append(f"## Context Window Usage {emoji}")
    lines.append("")
    lines.append(f"```")
    lines.append(f"  {bar}  {pct:.1f}%")
    lines.append(f"```")
    lines.append("")
    lines.append(f"**{format_tokens(used)}** / **{format_tokens(limit)}** tokens used")
    if model:
        lines.append(f"**Model:** {model}")
    lines.append(f"**Status:** {status}")
    lines.append("")

    # Actionable advice based on usage level
    if ratio > 0.90:
        lines.append("⚠️ **Action needed:** This chat is nearly full. Start a new conversation or compact this one to avoid degraded responses.")
    elif ratio > 0.75:
        lines.append("💡 **Tip:** Consider compacting this chat soon. Long conversations can reduce response quality.")
    elif ratio > 0.50:
        lines.append("ℹ️ This chat is about half full. You have room for more exchanges.")
    else:
        lines.append("✅ This chat has plenty of context window remaining.")

    return "\n".join(lines)


def estimate_tokens_from_text(text: str) -> int:
    """Rough token estimation: ~4 characters per token for English text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def find_claude_data_dir() -> Path | None:
    """Find the Claude desktop app's data directory."""
    candidates = [
        Path.home() / "Library" / "Application Support" / "Claude",
        Path.home() / "AppData" / "Roaming" / "Claude",
        Path.home() / ".config" / "Claude",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def find_conversation_databases(data_dir: Path) -> list[Path]:
    """Find SQLite databases that might contain conversation data."""
    db_files = []
    patterns = ["*.sqlite", "*.db", "*.sqlite3", "**/*.sqlite", "**/*.db"]
    for pattern in patterns:
        db_files.extend(data_dir.glob(pattern))

    # Also check for Electron's localStorage LevelDB
    local_storage = data_dir / "Local Storage" / "leveldb"
    if local_storage.exists():
        db_files.append(local_storage)

    # Check for IndexedDB
    indexeddb = data_dir / "IndexedDB"
    if indexeddb.exists():
        for db in indexeddb.glob("**/*.sqlite"):
            db_files.append(db)

    return db_files


def try_read_conversation_from_db(db_path: Path) -> dict | None:
    """Try to read conversation data from a SQLite database."""
    try:
        conn = sqlite3.connect(str(db_path), timeout=2)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        # Look for conversation-related tables
        for table in tables:
            lower = table.lower()
            if any(k in lower for k in ["conversation", "message", "chat", "token"]):
                cursor.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 5")
                rows = cursor.fetchall()
                if rows:
                    columns = [desc[0] for desc in cursor.description]
                    result = {
                        "table": table,
                        "columns": columns,
                        "rows": [dict(row) for row in rows],
                    }
                    conn.close()
                    return result

        conn.close()
    except Exception:
        pass
    return None


class MCPServer:
    """Simple MCP server implementing the context usage tool."""

    def __init__(self):
        self.conversation_cache = {}

    def handle_request(self, request: dict) -> dict:
        """Route an MCP JSON-RPC request to the appropriate handler."""
        method = request.get("method", "")
        req_id = request.get("id")

        handlers = {
            "initialize": self.handle_initialize,
            "notifications/initialized": self.handle_initialized,
            "tools/list": self.handle_tools_list,
            "tools/call": self.handle_tools_call,
            "resources/list": self.handle_resources_list,
            "ping": self.handle_ping,
        }

        handler = handlers.get(method)
        if handler:
            result = handler(request)
            if req_id is not None:
                return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": result}
            return None  # Notification, no response needed
        elif req_id is not None:
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        return None

    def handle_initialize(self, request: dict) -> dict:
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
            },
            "serverInfo": {
                "name": "context-usage",
                "version": "1.0.0",
            },
        }

    def handle_initialized(self, request: dict) -> dict:
        return {}

    def handle_ping(self, request: dict) -> dict:
        return {}

    def handle_tools_list(self, request: dict) -> dict:
        return {
            "tools": [
                {
                    "name": "check_context_usage",
                    "description": (
                        "Check how much of the context window has been used in the current conversation. "
                        "Shows a visual progress bar with token counts and advice on when to compact or start a new chat. "
                        "Call this when the user asks about context usage, chat length, or wants to know if they should start a new conversation."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "current_input_tokens": {
                                "type": "number",
                                "description": (
                                    "The approximate number of input tokens in this conversation. "
                                    "If you have access to usage metadata from the system, provide it. "
                                    "Otherwise, estimate based on the conversation length."
                                ),
                            },
                            "current_output_tokens": {
                                "type": "number",
                                "description": (
                                    "The approximate number of output tokens generated in this conversation. "
                                    "If you have access to usage metadata from the system, provide it. "
                                    "Otherwise, estimate based on your responses."
                                ),
                            },
                            "model_name": {
                                "type": "string",
                                "description": "The model being used (e.g. 'claude-sonnet-4-20250514').",
                            },
                            "message_count": {
                                "type": "number",
                                "description": "The total number of messages (user + assistant) in this conversation.",
                            },
                        },
                        "required": [],
                    },
                },
            ]
        }

    def handle_tools_call(self, request: dict) -> dict:
        params = request.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "check_context_usage":
            return self.check_context_usage(arguments)

        return {
            "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
            "isError": True,
        }

    def handle_resources_list(self, request: dict) -> dict:
        return {"resources": []}

    def check_context_usage(self, args: dict) -> dict:
        """Main tool: check context window usage and return a progress bar."""
        input_tokens = args.get("current_input_tokens", 0)
        output_tokens = args.get("current_output_tokens", 0)
        model = args.get("model_name", "")
        message_count = args.get("message_count", 0)

        # Try to read actual data from the Claude app's local storage
        local_data = self._try_read_local_data()
        if local_data and local_data.get("input_tokens"):
            input_tokens = local_data["input_tokens"]
            output_tokens = local_data.get("output_tokens", output_tokens)
            if local_data.get("model"):
                model = local_data["model"]

        total_tokens = int(input_tokens) + int(output_tokens)
        limit = get_model_limit(model)

        # If we have no token data at all, give a helpful fallback
        if total_tokens == 0:
            if message_count > 0:
                # Rough estimate: ~800 tokens per message exchange on average
                total_tokens = int(message_count * 800)
            else:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "## Context Window Usage\n\n"
                                "I couldn't determine the exact token usage for this conversation. "
                                "Try providing an estimate of the message count or token counts.\n\n"
                                f"**Context limit:** {format_tokens(limit)} tokens ({model or 'default model'})\n\n"
                                "💡 **Tip:** If this chat feels sluggish or responses seem less coherent, "
                                "it's probably time to compact or start a new conversation."
                            ),
                        }
                    ]
                }

        bar = build_progress_bar(total_tokens, limit, model)
        return {"content": [{"type": "text", "text": bar}]}

    def _try_read_local_data(self) -> dict | None:
        """Try to read token usage from the Claude desktop app's local data."""
        data_dir = find_claude_data_dir()
        if not data_dir:
            return None

        # Try to find and read conversation databases
        databases = find_conversation_databases(data_dir)
        for db_path in databases:
            if db_path.suffix in (".sqlite", ".db", ".sqlite3"):
                result = try_read_conversation_from_db(db_path)
                if result:
                    # Try to extract token info from the result
                    for row in result.get("rows", []):
                        tokens = {}
                        for key, value in row.items():
                            key_lower = str(key).lower()
                            if "input_token" in key_lower and isinstance(value, (int, float)):
                                tokens["input_tokens"] = int(value)
                            elif "output_token" in key_lower and isinstance(value, (int, float)):
                                tokens["output_tokens"] = int(value)
                            elif "model" in key_lower and isinstance(value, str):
                                tokens["model"] = value
                        if tokens.get("input_tokens"):
                            return tokens

        return None

    def run(self):
        """Run the MCP server on stdin/stdout."""
        # Read from stdin, write to stdout (MCP stdio transport)
        buffer = ""
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break  # EOF

                buffer += line

                # Try to parse complete JSON-RPC messages
                # MCP uses newline-delimited JSON
                while "\n" in buffer:
                    msg_str, buffer = buffer.split("\n", 1)
                    msg_str = msg_str.strip()
                    if not msg_str:
                        continue

                    try:
                        request = json.loads(msg_str)
                    except json.JSONDecodeError:
                        continue

                    response = self.handle_request(request)
                    if response is not None:
                        resp_str = json.dumps(response)
                        sys.stdout.write(resp_str + "\n")
                        sys.stdout.flush()

            except KeyboardInterrupt:
                break
            except Exception as e:
                # Never crash — log to stderr and continue
                sys.stderr.write(f"Error: {e}\n")
                sys.stderr.flush()


if __name__ == "__main__":
    server = MCPServer()
    server.run()
