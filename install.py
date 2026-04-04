#!/usr/bin/env python3
"""
Claude Context Bar — Installer

Injects a context window usage progress bar into the Claude desktop app (macOS).

How it works:
  1. Extracts the Electron app's app.asar into an app/ directory
     (Electron automatically prefers app/ over app.asar)
  2. Finds the main renderer HTML file
  3. Injects <script> and <link> tags for the context bar code
  4. Copies context_bar.js and context_bar.css into the extracted app

To uninstall: run uninstall.py (or just delete the app/ directory and restart Claude)
"""

import glob
import hashlib
import os
import shutil
import sys

# Add lib/ to path for the asar reader
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import asar_reader  # noqa: E402

# ── Configuration ─────────────────────────────────────────────────────
CLAUDE_APP_PATH = "/Applications/Claude.app"
RESOURCES_DIR = os.path.join(CLAUDE_APP_PATH, "Contents", "Resources")
ASAR_PATH = os.path.join(RESOURCES_DIR, "app.asar")
EXTRACTED_DIR = os.path.join(RESOURCES_DIR, "app")
INSTALL_MARKER = os.path.join(EXTRACTED_DIR, ".context_bar_installed")

SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
JS_FILE = "context_bar.js"
CSS_FILE = "context_bar.css"

# Tags injected into the HTML
SCRIPT_TAG = '<script src="context_bar.js" defer></script>'
CSS_TAG = '<link rel="stylesheet" href="context_bar.css">'
MARKER_COMMENT = "<!-- claude-context-bar -->"


def compute_checksum(path):
    """Compute SHA-256 of a file for version tracking."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def find_html_files(directory):
    """Find HTML files in the extracted app that are likely renderer entry points."""
    html_files = []
    for root, _, files in os.walk(directory):
        for name in files:
            if name.endswith(".html"):
                html_files.append(os.path.join(root, name))
    return html_files


def inject_into_html(html_path):
    """Inject our script and CSS tags into an HTML file. Returns True if modified."""
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    if MARKER_COMMENT in content:
        return False  # Already injected

    modified = False

    # Inject CSS link before </head>
    if "</head>" in content:
        content = content.replace(
            "</head>",
            f"  {MARKER_COMMENT}\n  {CSS_TAG}\n  {SCRIPT_TAG}\n</head>",
        )
        modified = True
    elif "</body>" in content:
        # Fallback: inject before </body>
        content = content.replace(
            "</body>",
            f"  {MARKER_COMMENT}\n  {CSS_TAG}\n  {SCRIPT_TAG}\n</body>",
        )
        modified = True
    elif "<html" in content.lower():
        # Last resort: append to end
        content += f"\n{MARKER_COMMENT}\n{CSS_TAG}\n{SCRIPT_TAG}\n"
        modified = True

    if modified:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(content)

    return modified


def copy_assets(dest_dir):
    """Copy context_bar.js and context_bar.css to the destination directory."""
    for filename in [JS_FILE, CSS_FILE]:
        src = os.path.join(SRC_DIR, filename)
        dst = os.path.join(dest_dir, filename)
        if not os.path.exists(src):
            print(f"  ERROR: Source file not found: {src}")
            return False
        shutil.copy2(src, dst)
        print(f"  Copied {filename}")
    return True


def main():
    print("=" * 60)
    print("Claude Context Bar — Installer")
    print("=" * 60)
    print()

    # Check Claude app exists
    if not os.path.exists(CLAUDE_APP_PATH):
        print(f"ERROR: Claude desktop app not found at {CLAUDE_APP_PATH}")
        print("Make sure Claude is installed in /Applications/")
        sys.exit(1)

    if not os.path.exists(ASAR_PATH):
        print(f"ERROR: app.asar not found at {ASAR_PATH}")
        print("The Claude app structure may have changed.")
        sys.exit(1)

    # Check if already installed
    if os.path.exists(INSTALL_MARKER):
        print("Context bar is already installed!")
        print("Run uninstall.py first if you want to reinstall.")
        sys.exit(0)

    # If app/ directory exists but wasn't installed by us, warn
    if os.path.exists(EXTRACTED_DIR) and not os.path.exists(INSTALL_MARKER):
        print(f"WARNING: {EXTRACTED_DIR} already exists but wasn't created by us.")
        response = input("Overwrite it? (y/N) ").strip().lower()
        if response != "y":
            print("Aborted.")
            sys.exit(0)
        shutil.rmtree(EXTRACTED_DIR)

    # Record asar checksum for version tracking
    checksum = compute_checksum(ASAR_PATH)
    print(f"app.asar checksum: {checksum[:16]}...")
    print()

    # Step 1: Extract app.asar
    print("[1/4] Extracting app.asar → app/ ...")
    print("       This may take a minute for large apps...")
    try:
        asar_reader.extract(ASAR_PATH, EXTRACTED_DIR)
    except Exception as e:
        print(f"  ERROR extracting asar: {e}")
        # Clean up partial extraction
        if os.path.exists(EXTRACTED_DIR):
            shutil.rmtree(EXTRACTED_DIR)
        sys.exit(1)
    print("  Done.")
    print()

    # Step 2: Find and inject into HTML files
    print("[2/4] Finding renderer HTML files...")
    html_files = find_html_files(EXTRACTED_DIR)
    if not html_files:
        print("  ERROR: No HTML files found in extracted app.")
        print("  The Claude app structure may have changed.")
        shutil.rmtree(EXTRACTED_DIR)
        sys.exit(1)

    injected_count = 0
    for html_path in html_files:
        rel_path = os.path.relpath(html_path, EXTRACTED_DIR)
        if inject_into_html(html_path):
            print(f"  Injected into: {rel_path}")
            injected_count += 1
        else:
            print(f"  Skipped (already injected): {rel_path}")

    if injected_count == 0:
        print("  WARNING: No HTML files were modified.")
    print()

    # Step 3: Copy JS and CSS assets
    print("[3/4] Copying context bar assets...")

    # Copy assets to same directory as each injected HTML file
    # Also copy to the root of the extracted app as fallback
    asset_dirs = set()
    for html_path in html_files:
        asset_dirs.add(os.path.dirname(html_path))
    asset_dirs.add(EXTRACTED_DIR)

    for dest_dir in asset_dirs:
        if not copy_assets(dest_dir):
            print("  ERROR: Failed to copy assets.")
            shutil.rmtree(EXTRACTED_DIR)
            sys.exit(1)
    print()

    # Step 4: Write install marker
    print("[4/4] Writing install marker...")
    with open(INSTALL_MARKER, "w") as f:
        f.write(f"asar_checksum={checksum}\n")
        f.write(f"installed_at={os.popen('date').read().strip()}\n")
    print("  Done.")
    print()

    print("=" * 60)
    print("Installation complete!")
    print()
    print("Next steps:")
    print("  1. Quit Claude desktop app completely (Cmd+Q)")
    print("  2. Reopen Claude")
    print("  3. Start a conversation — the progress bar will appear")
    print("     at the top of the chat window after the first message")
    print()
    print("To uninstall: python uninstall.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
