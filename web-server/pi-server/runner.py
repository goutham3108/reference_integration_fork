#!/usr/bin/env python3
"""Execute an installed application as the dedicated SDV application user."""

import json
import os
import re
import sys
from pathlib import Path

APP_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
APPS_ROOT = Path("/var/lib/sdv-deployer/apps").resolve()


def main() -> int:
    if len(sys.argv) != 2 or not APP_ID_RE.fullmatch(sys.argv[1]):
        print("Usage: runner.py <application-id>", file=sys.stderr)
        return 2

    app_id = sys.argv[1]
    app_root = (APPS_ROOT / app_id / "current").resolve(strict=True)
    try:
        app_root.relative_to(APPS_ROOT)
    except ValueError:
        print("Application path escapes the deployment directory", file=sys.stderr)
        return 2

    manifest_path = app_root / "manifest.json"
    with manifest_path.open("r", encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    entrypoint = Path(manifest["entrypoint"])
    if entrypoint.is_absolute():
        raise ValueError("Entrypoint must be relative to the application package")
    executable = (app_root / entrypoint).resolve(strict=True)
    try:
        executable.relative_to(app_root)
    except ValueError as error:
        raise ValueError("Entrypoint escapes the application directory") from error

    arguments = manifest.get("args", [])
    if not isinstance(arguments, list) or not all(isinstance(arg, str) for arg in arguments):
        raise ValueError("Manifest args must be a list of strings")

    runtime = manifest["runtime"]
    if runtime == "python":
        command = [sys.executable, str(executable), *arguments]
    elif runtime == "native":
        if not os.access(executable, os.X_OK):
            raise PermissionError(f"Entrypoint is not executable: {executable.name}")
        command = [str(executable), *arguments]
    else:
        raise ValueError(f"Unsupported runtime: {runtime}")

    os.chdir(app_root)
    os.execvpe(command[0], command, os.environ.copy())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Application launch failed: {error}", file=sys.stderr)
        raise SystemExit(1)
