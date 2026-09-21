"""Engine entry point.

Started by the Tauri shell as a child process. Two things make that
relationship work:

  - The engine picks its own port by binding 0 and reporting the result on
    stdout. Having the shell pre-bind a socket, read the port and close it
    is a race: anything on the machine can take the port in between.
  - The engine watches its parent and exits when the parent does. Tauri does
    not reliably reap child processes (tauri#5611), so on a crash or a Task
    Manager kill this is what stops an orphaned engine holding the GPU and
    the database.

The shell also sets NOT3_TOKEN; requests without it are refused.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time


def _handshake(port: int) -> None:
    """Tell the parent where we are. One line, flushed, then nothing else."""
    print(json.dumps({
        "event": "ready",
        "port": port,
        "pid": os.getpid(),
        "version": "0.1.0",
    }), flush=True)


def _watch_parent(parent_pid: int, interval: float = 2.0) -> None:
    """Exit when the parent process goes away."""
    import psutil

    def loop() -> None:
        while True:
            time.sleep(interval)
            try:
                if not psutil.pid_exists(parent_pid):
                    break
                # pid_exists alone is not enough on Windows, where a pid can
                # be recycled; if it is alive but no longer our parent, the
                # original is gone.
                proc = psutil.Process(parent_pid)
                if proc.status() == psutil.STATUS_ZOMBIE:
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
        print(json.dumps({"event": "parent-gone", "parent_pid": parent_pid}),
              file=sys.stderr, flush=True)
        os._exit(0)

    threading.Thread(target=loop, name="not3-parent-watchdog", daemon=True).start()


def _watch_stdin() -> None:
    """Exit when stdin closes.

    Belt and braces alongside the pid watchdog: when the parent dies, the
    pipe closes immediately, which is faster than the polling interval.
    """
    def loop() -> None:
        try:
            while sys.stdin.readline():
                pass
        except (OSError, ValueError):
            pass
        os._exit(0)

    if sys.stdin and not sys.stdin.closed:
        threading.Thread(target=loop, name="not3-stdin-watchdog", daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="not3-engine")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=0, help="0 picks a free port")
    p.add_argument("--parent-pid", type=int, default=0,
                   help="exit when this process exits")
    p.add_argument("--watch-stdin", action="store_true",
                   help="also exit when stdin closes")
    p.add_argument("--log-level", default="warning")
    args = p.parse_args(argv)

    import uvicorn

    try:
        from .api import create_app
        from .config import Settings
    except ImportError:
        from not3.api import create_app
        from not3.config import Settings

    settings = Settings.load()
    settings.ensure_dirs()

    # Bind before uvicorn so the port is known and never released in between.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    sock.listen(128)
    port = sock.getsockname()[1]

    if args.parent_pid:
        _watch_parent(args.parent_pid)
    if args.watch_stdin:
        _watch_stdin()

    _handshake(port)

    app = create_app(settings)
    config = uvicorn.Config(app, log_level=args.log_level, access_log=False)
    server = uvicorn.Server(config)
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
