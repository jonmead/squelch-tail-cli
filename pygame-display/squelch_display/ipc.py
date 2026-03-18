"""IPC — reads JSON state lines from stdin, writes command lines to stdout."""

import json
import queue
import sys
import threading


class IpcReader:
    """Background thread that reads newline-delimited JSON from stdin."""

    def __init__(self):
        self._q = queue.Queue()
        self._thread = threading.Thread(target=self._run, name='ipc-reader', daemon=True)

    def start(self) -> None:
        self._thread.start()

    def poll(self) -> list:
        """Drain all pending messages (non-blocking). Returns a list of dicts."""
        msgs = []
        while True:
            try:
                msgs.append(self._q.get_nowait())
            except queue.Empty:
                break
        return msgs

    def has_pending(self) -> bool:
        """Return True if there are unread messages in the queue."""
        return not self._q.empty()

    def _run(self) -> None:
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            try:
                self._q.put(json.loads(line))
            except json.JSONDecodeError:
                pass
        # stdin closed — signal shutdown
        self._q.put({'type': 'quit'})


def send_command(cmd: dict) -> None:
    """Write a command as a JSON line to stdout (read by the CLI plugin)."""
    print(json.dumps(cmd), flush=True)
