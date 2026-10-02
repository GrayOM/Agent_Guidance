import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class OperationLockedError(RuntimeError):
    pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # os.kill(pid, 0) is not a side-effect-free existence probe on Windows.
        import ctypes

        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
            process_query_limited_information, False, pid,
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class OperationLock:
    def __init__(self, path: Path, operation: str) -> None:
        self.path = path
        self.operation = operation
        self.owner = uuid4().hex
        self.acquired = False

    def _read(self) -> dict[str, object]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1, "pid": os.getpid(), "operation": self.operation,
            "started_at": datetime.now(timezone.utc).isoformat(), "owner": self.owner,
        }
        for _ in range(2):
            try:
                descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                current = self._read()
                raw_pid = current.get("pid", -1)
                pid = int(str(raw_pid)) if str(raw_pid).lstrip("-").isdigit() else -1
                if _pid_alive(pid):
                    raise OperationLockedError(
                        f"another Agent Guidance operation is running (PID {pid}, "
                        f"started {current.get('started_at', 'unknown')})"
                    )
                try:
                    self.path.unlink()
                except OSError as exc:
                    raise OperationLockedError("a stale Agent Guidance lock could not be removed") from exc
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream)
                stream.flush()
                os.fsync(stream.fileno())
            self.acquired = True
            return
        raise OperationLockedError("could not acquire the Agent Guidance operation lock")

    def release(self) -> None:
        if not self.acquired:
            return
        if self._read().get("owner") == self.owner:
            self.path.unlink(missing_ok=True)
        self.acquired = False

    def __enter__(self) -> "OperationLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()
