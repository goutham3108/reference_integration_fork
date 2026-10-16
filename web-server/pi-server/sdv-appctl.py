#!/usr/bin/python3
"""Narrow root controller for deployment-owned systemd application units."""

import os
import pwd
import re
import subprocess
import sys
from pathlib import Path

APP_ID = re.compile(r"^[A-Za-z0-9_-]+$")
STAGING_ID = re.compile(r"^upload_[A-Za-z0-9_-]+$")
ACTIONS = {"start", "stop", "restart", "is-active"}
STAGING_ROOT = Path("/var/lib/sdv-deployer/staging").resolve()


def main() -> int:
    if os.geteuid() != 0:
        print("sdv-appctl must be invoked through sudo", file=sys.stderr)
        return 1
    if len(sys.argv) == 2 and sys.argv[1] == "daemon-reload":
        command = ["/usr/bin/systemctl", "daemon-reload"]
    elif len(sys.argv) >= 5 and sys.argv[1] == "smoke-test":
        staging_id, runtime, entrypoint = sys.argv[2:5]
        if not STAGING_ID.fullmatch(staging_id) or runtime not in {"native", "python"}:
            print("Invalid smoke-test request", file=sys.stderr)
            return 2
        relative_entrypoint = Path(entrypoint)
        if relative_entrypoint.is_absolute() or ".." in relative_entrypoint.parts:
            print("Invalid smoke-test entrypoint", file=sys.stderr)
            return 2
        app_root = (STAGING_ROOT / staging_id / "unpacked").resolve(strict=True)
        target = (app_root / relative_entrypoint).resolve(strict=True)
        try:
            target.relative_to(app_root)
        except ValueError:
            print("Smoke-test entrypoint escapes staging directory", file=sys.stderr)
            return 2
        app_user = pwd.getpwnam("sdv-apps")
        arguments = sys.argv[5:]
        if runtime == "python":
            command = ["/usr/bin/python3", str(target), *arguments]
        else:
            if not os.access(target, os.X_OK):
                print("Native smoke-test entrypoint is not executable", file=sys.stderr)
                return 2
            command = [str(target), *arguments]

        def drop_identity():
            os.initgroups(app_user.pw_name, app_user.pw_gid)
            os.setgid(app_user.pw_gid)
            os.setuid(app_user.pw_uid)

        os.chdir(app_root)
        drop_identity()
        os.execvpe(command[0], command, os.environ.copy())
    elif len(sys.argv) == 3 and sys.argv[1] == "show-main-pid" and APP_ID.fullmatch(sys.argv[2]):
        command = ["/usr/bin/systemctl", "show", f"sdv-app@{sys.argv[2]}.service", "--property=MainPID"]
    elif len(sys.argv) == 3 and sys.argv[1] in ACTIONS and APP_ID.fullmatch(sys.argv[2]):
        command = ["/usr/bin/systemctl", sys.argv[1], f"sdv-app@{sys.argv[2]}.service"]
    else:
        print("Unsupported deployment service action", file=sys.stderr)
        return 2

    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
