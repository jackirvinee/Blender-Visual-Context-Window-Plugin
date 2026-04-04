#!/usr/bin/env python3
"""
Claude Context Bar — Uninstaller

Removes the context bar injection from the Claude desktop app by deleting
the extracted app/ directory. Electron will then fall back to the original
unmodified app.asar.
"""

import os
import shutil
import sys

CLAUDE_APP_PATH = "/Applications/Claude.app"
RESOURCES_DIR = os.path.join(CLAUDE_APP_PATH, "Contents", "Resources")
EXTRACTED_DIR = os.path.join(RESOURCES_DIR, "app")
INSTALL_MARKER = os.path.join(EXTRACTED_DIR, ".context_bar_installed")


def main():
    print("=" * 60)
    print("Claude Context Bar — Uninstaller")
    print("=" * 60)
    print()

    if not os.path.exists(EXTRACTED_DIR):
        print("Nothing to uninstall — app/ directory does not exist.")
        print("The Claude app is using its original app.asar.")
        sys.exit(0)

    # Safety check: only remove if we installed it
    if not os.path.exists(INSTALL_MARKER):
        print(f"WARNING: {EXTRACTED_DIR} exists but was NOT created by our installer.")
        print("This directory may contain important data.")
        response = input("Remove it anyway? (y/N) ").strip().lower()
        if response != "y":
            print("Aborted.")
            sys.exit(0)

    print("Removing injected app/ directory...")
    try:
        shutil.rmtree(EXTRACTED_DIR)
        print("  Done.")
    except PermissionError:
        print("  ERROR: Permission denied. Try running with sudo:")
        print(f"  sudo python3 {sys.argv[0]}")
        sys.exit(1)
    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    print()
    print("=" * 60)
    print("Uninstall complete!")
    print()
    print("Next steps:")
    print("  1. Quit Claude desktop app completely (Cmd+Q)")
    print("  2. Reopen Claude — it will use the original app.asar")
    print("=" * 60)


if __name__ == "__main__":
    main()
