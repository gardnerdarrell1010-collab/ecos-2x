from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath


def verify_inventory(root: Path, manifest: dict):
    root = root.resolve(strict=True)
    paths = set()
    for entry in manifest["files"]:
        relative = entry["path"]
        posix = PurePosixPath(relative)
        if posix.is_absolute() or ".." in posix.parts or "\\" in relative or ":" in relative or str(posix) != relative:
            raise ValueError("Unsafe inventory path")
        normalized = relative.casefold()
        if normalized in paths:
            raise ValueError("Duplicate inventory path")
        paths.add(normalized)
        file = (root / relative).resolve(strict=True)
        if not file.is_relative_to(root) or not file.is_file():
            raise ValueError("Inventory escapes package")
        data = file.read_bytes()
        if len(data) != entry["size_bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError("Corrupt package entry: " + relative)
    for field in ("restore_instructions_path", "verification_queries_path"):
        if manifest[field].casefold() not in paths:
            raise ValueError("Required recovery file absent from inventory")
    return len(paths)
