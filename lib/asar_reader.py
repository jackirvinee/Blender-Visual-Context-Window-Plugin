"""
Pure Python ASAR archive extractor.

The ASAR format (used by Electron) consists of:
  - 4 bytes: UInt32LE — size of the header pickle (including the next 4 bytes)
  - 4 bytes: UInt32LE — size of the header string + 4
  - 4 bytes: UInt32LE — size of the header string
  - 4 bytes: UInt32LE — size of the header string (repeated)
  - Header JSON string (describes file tree with offsets and sizes)
  - Concatenated file data

No Node.js or npm dependencies required.
"""

import json
import os
import struct


def read_header(asar_path):
    """Read and parse the ASAR header JSON from an archive file."""
    with open(asar_path, "rb") as f:
        # Read the pickle header (16 bytes total)
        # Bytes 0-3: pickle size
        # Bytes 4-7: header data size (header_string_size + 4 + 4)
        # Bytes 8-11: header string size
        # Bytes 12-15: header string size (repeated)
        data = f.read(16)
        if len(data) < 16:
            raise ValueError("Invalid ASAR file: too short for header")

        _pickle_size = struct.unpack("<I", data[0:4])[0]
        _header_data_size = struct.unpack("<I", data[4:8])[0]
        header_string_size = struct.unpack("<I", data[8:12])[0]
        _header_string_size2 = struct.unpack("<I", data[12:16])[0]

        header_json = f.read(header_string_size).decode("utf-8")
        # Data offset is where file contents start (after the header)
        # Aligned to 4 bytes
        data_offset = 16 + header_string_size
        padding = (4 - (data_offset % 4)) % 4
        data_offset += padding

    header = json.loads(header_json)
    return header, data_offset


def extract(asar_path, dest_dir):
    """
    Extract all files from an ASAR archive into dest_dir.

    Args:
        asar_path: Path to the .asar file
        dest_dir: Directory to extract files into (created if needed)
    """
    header, data_offset = read_header(asar_path)

    os.makedirs(dest_dir, exist_ok=True)

    with open(asar_path, "rb") as f:
        _extract_node(f, header, data_offset, dest_dir)


def _extract_node(f, node, data_offset, current_path):
    """Recursively extract files/directories from the ASAR file tree."""
    if "files" in node:
        # This is a directory node
        os.makedirs(current_path, exist_ok=True)
        for name, child in node["files"].items():
            child_path = os.path.join(current_path, name)
            _extract_node(f, child, data_offset, child_path)
    elif "offset" in node:
        # This is a file node with data in the archive
        offset = int(node["offset"]) + data_offset
        size = int(node["size"])

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(current_path), exist_ok=True)

        f.seek(offset)
        remaining = size
        with open(current_path, "wb") as out:
            while remaining > 0:
                chunk_size = min(remaining, 65536)
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                out.write(chunk)
                remaining -= len(chunk)

        # Preserve executable bit if indicated
        if node.get("executable", False):
            os.chmod(current_path, 0o755)
    elif "link" in node:
        # This is a symbolic link
        link_target = node["link"]
        parent = os.path.dirname(current_path)
        os.makedirs(parent, exist_ok=True)
        # Create relative symlink
        if os.path.exists(current_path) or os.path.islink(current_path):
            os.remove(current_path)
        os.symlink(link_target, current_path)


def list_files(asar_path):
    """List all files in an ASAR archive. Returns a list of relative paths."""
    header, _ = read_header(asar_path)
    files = []
    _list_node(header, "", files)
    return files


def _list_node(node, prefix, files):
    """Recursively collect file paths from the ASAR header tree."""
    if "files" in node:
        for name, child in node["files"].items():
            path = os.path.join(prefix, name) if prefix else name
            _list_node(child, path, files)
    else:
        files.append(prefix)
