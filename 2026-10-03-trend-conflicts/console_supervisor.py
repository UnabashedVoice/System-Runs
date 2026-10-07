"""
console_supervisor.py — A new console window for every run in the batch.

Watches batch.log. Whenever a run starts (one system on one question), opens
a new Windows Terminal window running watch_run.py for it. Each window stops
updating when its run ends and stays open until closed by hand, so finished
runs stay on screen. Exits when the batch prints "all done". Read-only apart
from opening windows.
"""

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
START = re.compile(r"^\[\d\d:\d\d:\d\d\] (\S+) ([qt]\d+) (arbitrator|actualizer) \.\.\.$")


def open_window(model, qid, system):
    title = f"{qid} {system} ({model})"
    args = [sys.executable, str(HERE / "watch_run.py"), model, qid, system]
    wt = shutil.which("wt")
    if wt:
        # "-w new" forces a separate window rather than a tab in an existing one.
        subprocess.Popen([wt, "-w", "new", "--title", title, "-d", str(HERE), *args])
    else:
        subprocess.Popen(args, cwd=HERE, creationflags=subprocess.CREATE_NEW_CONSOLE)


def current_run():
    log = HERE / "batch.log"
    if not log.exists():
        return None
    for line in reversed(log.read_text(encoding="utf-8", errors="replace").splitlines()):
        m = START.match(line.strip())
        if m:
            return m.groups()
    return None


def main():
    launched = set()
    while True:
        run = current_run()
        if run and run not in launched:
            open_window(*run)
            launched.add(run)
            print(f"{time.strftime('%H:%M:%S')} opened a window for {' '.join(run)}", flush=True)
        log = HERE / "batch.log"
        if log.exists() and "all done" in log.read_text(encoding="utf-8", errors="replace"):
            print("batch finished; supervisor exiting", flush=True)
            return
        time.sleep(5)


if __name__ == "__main__":
    main()
