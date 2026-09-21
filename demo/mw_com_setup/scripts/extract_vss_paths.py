#!/usr/bin/env python3
"""
Extract leaf VSS paths from a VSS JSON and print one path per line.
Usage:
  ./extract_vss_paths.py input_vss.json > vss_paths.txt
Generates lines like: Vehicle.Speed
"""
import json
import sys

if len(sys.argv) < 2:
    print("usage: extract_vss_paths.py <vss.json>", file=sys.stderr)
    sys.exit(2)

with open(sys.argv[1], 'r', encoding='utf-8') as f:
    data = json.load(f)

paths = []

def walk(node, prefix=""):
    if not isinstance(node, dict):
        return
    children = node.get('children')
    if children and isinstance(children, dict):
        for name, child in children.items():
            new_prefix = f"{prefix}.{name}" if prefix else name
            walk(child, new_prefix)
    else:
        # leaf node
        if prefix:
            paths.append(prefix)

# Many VSS files start with a top-level object that contains the top-level
# named branches (e.g. "Vehicle"). Walk each top-level entry.
for key, val in data.items():
    walk(val, key)

# Deduplicate and sort
for p in sorted(set(paths)):
    print(p)
