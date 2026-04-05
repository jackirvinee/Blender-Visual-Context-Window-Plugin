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
                {
                    "name": "summarize_for_new_chat",
                    "description": (
                        "Generate a portable summary of the current conversation that the user can paste into a new chat "
                        "to continue where they left off. Call this when the context is getting full and the user wants to "
                        "start a new conversation without losing progress. Also call this proactively when check_context_usage "
                        "shows >75% usage."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "conversation_summary": {
                                "type": "string",
                                "description": (
                                    "A thorough summary of the entire conversation so far. Include: "
                                    "1) The original goal/task the user is working on. "
                                    "2) Key decisions made and why. "
                                    "3) Current state of progress (what's done, what's left). "
                                    "4) Any important code snippets, file paths, or configurations discussed. "
                                    "5) Open questions or blockers. "
                                    "Make this detailed enough that a new Claude instance can pick up seamlessly."
                                ),
                            },
                            "key_files": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of file paths that were created or modified in this conversation.",
                            },
                            "current_task": {
                                "type": "string",
                                "description": "What the user is currently working on or what was about to happen next.",
                            },
                        },
                        "required": ["conversation_summary"],
                    },
                },
                {
                    "name": "export_key_info",
                    "description": (
                        "Extract and organize the most important information from the conversation: "
                        "decisions made, code snippets, action items, links, and configuration details. "
                        "Produces a clean reference document the user can save. "
                        "Call this when the user wants to save important info before compacting or starting a new chat."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "decisions": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Key decisions made during the conversation and their rationale.",
                            },
                            "code_snippets": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "description": {"type": "string"},
                                        "language": {"type": "string"},
                                        "code": {"type": "string"},
                                        "file_path": {"type": "string"},
                                    },
                                },
                                "description": "Important code snippets from the conversation.",
                            },
                            "action_items": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Remaining action items or TODOs.",
                            },
                            "links_and_references": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Any URLs, documentation references, or external resources mentioned.",
                            },
                            "configuration": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Configuration details, environment variables, settings, etc.",
                            },
                        },
                        "required": [],
                    },
                },
                {
                    "name": "suggest_compaction",
                    "description": (
                        "Analyze the conversation and suggest which parts could be compacted or dropped "
                        "to free up context space without losing important information. "
                        "Call this when the user wants to optimize their context usage or when usage is >75%."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "message_categories": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "category": {"type": "string"},
                                        "message_count": {"type": "number"},
                                        "estimated_tokens": {"type": "number"},
                                        "can_compact": {"type": "boolean"},
                                        "reason": {"type": "string"},
                                    },
                                },
                                "description": (
                                    "Break down the conversation into categories like: "
                                    "exploratory back-and-forth, error debugging, successful code, "
                                    "setup/config, planning, etc. For each, estimate token count "
                                    "and whether it can be safely compacted."
                                ),
                            },
                            "total_estimated_tokens": {
                                "type": "number",
                                "description": "Total estimated tokens in the conversation.",
                            },
                            "potential_savings": {
                                "type": "number",
                                "description": "Estimated tokens that could be freed by compacting the suggested categories.",
                            },
                        },
                        "required": ["message_categories"],
                    },
                },
            ]
        }

    def handle_tools_call(self, request: dict) -> dict:
        params = request.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        tool_handlers = {
            "check_context_usage": self.check_context_usage,
            "summarize_for_new_chat": self.summarize_for_new_chat,
            "export_key_info": self.export_key_info,
            "suggest_compaction": self.suggest_compaction,
        }

        handler = tool_handlers.get(tool_name)
        if handler:
            return handler(arguments)

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

    def summarize_for_new_chat(self, args: dict) -> dict:
        """Generate a portable summary to carry over into a new chat."""
        summary = args.get("conversation_summary", "")
        key_files = args.get("key_files", [])
        current_task = args.get("current_task", "")

        lines = []
        lines.append("## Conversation Carry-Over Summary")
        lines.append("")
        lines.append("Copy everything below and paste it as your first message in a new chat:")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("**Continue from previous conversation:**")
        lines.append("")
        lines.append(summary)

        if key_files:
            lines.append("")
            lines.append("**Key files involved:**")
            for f in key_files:
                lines.append(f"- `{f}`")

        if current_task:
            lines.append("")
            lines.append(f"**Next step:** {current_task}")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("*Paste the above into a new Claude chat to continue where you left off.*")

        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    def export_key_info(self, args: dict) -> dict:
        """Export decisions, code, action items, and references from the conversation."""
        decisions = args.get("decisions", [])
        code_snippets = args.get("code_snippets", [])
        action_items = args.get("action_items", [])
        links = args.get("links_and_references", [])
        config = args.get("configuration", [])

        lines = []
        lines.append("## Conversation Export")
        lines.append("")

        if decisions:
            lines.append("### Decisions Made")
            for i, d in enumerate(decisions, 1):
                lines.append(f"{i}. {d}")
            lines.append("")

        if code_snippets:
            lines.append("### Code Snippets")
            for snippet in code_snippets:
                desc = snippet.get("description", "")
                lang = snippet.get("language", "")
                code = snippet.get("code", "")
                path = snippet.get("file_path", "")
                if desc:
                    lines.append(f"**{desc}**" + (f" (`{path}`)" if path else ""))
                elif path:
                    lines.append(f"**`{path}`**")
                lines.append(f"```{lang}")
                lines.append(code)
                lines.append("```")
                lines.append("")

        if action_items:
            lines.append("### Action Items")
            for item in action_items:
                lines.append(f"- [ ] {item}")
            lines.append("")

        if links:
            lines.append("### References")
            for link in links:
                lines.append(f"- {link}")
            lines.append("")

        if config:
            lines.append("### Configuration")
            for c in config:
                lines.append(f"- {c}")
            lines.append("")

        if not any([decisions, code_snippets, action_items, links, config]):
            lines.append("No key information was provided to export.")
            lines.append("Ask Claude to call this tool again with the conversation details filled in.")

        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    def suggest_compaction(self, args: dict) -> dict:
        """Suggest which conversation parts can be compacted to free context."""
        categories = args.get("message_categories", [])
        total_tokens = args.get("total_estimated_tokens", 0)
        potential_savings = args.get("potential_savings", 0)

        lines = []
        lines.append("## Context Compaction Analysis")
        lines.append("")

        if not categories:
            lines.append("No conversation breakdown was provided.")
            lines.append("Ask Claude to analyze the conversation and call this tool again.")
            return {"content": [{"type": "text", "text": "\n".join(lines)}]}

        # Summary table
        lines.append("| Category | Messages | ~Tokens | Compactable? | Notes |")
        lines.append("|----------|----------|---------|--------------|-------|")

        compactable_tokens = 0
        keep_tokens = 0

        for cat in categories:
            name = cat.get("category", "Unknown")
            count = cat.get("message_count", 0)
            tokens = cat.get("estimated_tokens", 0)
            can_compact = cat.get("can_compact", False)
            reason = cat.get("reason", "")

            status = "Yes" if can_compact else "No (keep)"
            lines.append(f"| {name} | {count} | {format_tokens(tokens)} | {status} | {reason} |")

            if can_compact:
                compactable_tokens += tokens
            else:
                keep_tokens += tokens

        lines.append("")
        lines.append(f"**Total tokens:** {format_tokens(total_tokens)}")
        if potential_savings > 0:
            savings_pct = (potential_savings / total_tokens * 100) if total_tokens > 0 else 0
            lines.append(f"**Potential savings:** {format_tokens(potential_savings)} tokens ({savings_pct:.0f}%)")
        elif compactable_tokens > 0:
            savings_pct = (compactable_tokens / total_tokens * 100) if total_tokens > 0 else 0
            lines.append(f"**Potential savings:** {format_tokens(compactable_tokens)} tokens ({savings_pct:.0f}%)")

        lines.append("")
        lines.append("### Recommendations")
        lines.append("")

        if compactable_tokens > 0 or potential_savings > 0:
            lines.append("**What to do:**")
            lines.append("1. Use **\"summarize for new chat\"** to generate a carry-over summary")
            lines.append("2. Start a new conversation and paste the summary")
            lines.append("3. You'll have a fresh context window with all the important context preserved")
            lines.append("")
            lines.append("**What gets dropped (safely):**")
            for cat in categories:
                if cat.get("can_compact", False):
                    lines.append(f"- {cat.get('category', '?')}: {cat.get('reason', 'can be summarized')}")
        else:
            lines.append("This conversation is efficiently using its context. No compaction needed yet.")

        lines.append("")
        lines.append("### Quick Tips to Save Context")
        lines.append("- Avoid re-pasting large code blocks Claude has already seen")
        lines.append("- Ask Claude to focus on specific sections instead of entire files")
        lines.append("- Use short, direct prompts instead of lengthy explanations")
        lines.append("- If debugging, share only the relevant error + surrounding code")

        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

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
