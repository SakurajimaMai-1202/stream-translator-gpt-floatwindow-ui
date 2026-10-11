#!/usr/bin/env python
"""Compare build-Python distributions with a shipped runtime's pins."""

import argparse
from importlib import metadata
from pathlib import Path
import re


def normalize_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def read_pins(path):
    pins = {}
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s=]+)", line)
        if not match:
            raise ValueError(f"{path}:{number}: expected Name==version")
        name, version = match.groups()
        key = normalize_name(name)
        if key in pins and pins[key][1] != version:
            raise ValueError(f"{path}:{number}: conflicting pins for {name}")
        pins[key] = (name, version)
    return pins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("constraints", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        pins = read_pins(args.constraints)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    installed = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            installed.setdefault(normalize_name(name), set()).add(distribution.version)
    rows = []
    for key, (name, expected) in sorted(pins.items()):
        versions = installed.get(key)
        if versions != {expected}:
            rows.append((name, expected, ", ".join(sorted(versions)) if versions else "MISSING"))
    if rows:
        table = [("Package", "Pinned", "Installed"), *rows]
        widths = [max(len(row[i]) for row in table) for i in range(3)]
        for row in table:
            print("  ".join(value.ljust(width) for value, width in zip(row, widths)).rstrip())
    extras = len(installed.keys() - pins.keys())
    print(f"Constraints: {len(pins)} pinned, {len(rows)} drifted/missing; {extras} extra installed (not pinned).")
    return 1 if args.strict and rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
