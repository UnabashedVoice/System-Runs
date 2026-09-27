"""
console_supervisor.py — One console window per batch run.

Watches batch.log. Whenever a new run starts, opens a new console window
running watch_run.py for it; that window closes itself when its run ends.
Exits when the batch prints "all done". Read-only apart from opening windows.
"""

import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
START = re.compile(r"^\[\d\d:\d\d:\d\d\] (\S+) cycle (\d+) (q\d) \.\.\.$")


def current_run():
    lines = (HERE / "batch.log").read_text(encoding="utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        m = START.match(line.strip())
        if m:
            return m.group(1), m.group(2), m.group(3)
    return None


def main():
    launched = set()
    while True:
        log = (HERE / "batch.log").read_text(encoding="utf-8", errors="replace")
        run = current_run()
        if run and run not in launched:
            subprocess.Popen([sys.executable, str(HERE / "watch_run.py"), *run], cwd=HERE,
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
            launched.add(run)
            print(f"{time.strftime('%H:%M:%S')} opened console for {' '.join(run)}", flush=True)
        if "all done" in log:
            print("batch finished; supervisor exiting", flush=True)
            return
        time.sleep(5)


if __name__ == "__main__":
    main()
