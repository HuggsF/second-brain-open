"""Lock do sistema operacional para escritores unicos.

Um arquivo de lock por recurso; o lock e do processo e some com ele, entao um processo que
morre nunca deixa o lock preso. Windows usa `msvcrt.locking` no byte 0; os demais, `flock`.
"""
import sys
import time
from contextlib import contextmanager
from pathlib import Path

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

__all__ = ["SyncBusy", "sync_lock"]


class SyncBusy(RuntimeError):
    """Outro processo segura o lock."""


def _try_lock(fh) -> bool:
    if sys.platform == "win32":
        fh.seek(0)
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(fh) -> None:
    if sys.platform == "win32":
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextmanager
def sync_lock(path: Path, wait_seconds: float = 0.0, poll_seconds: float = 0.2):
    """Segura o lock exclusivo de `path`; levanta `SyncBusy` se nao obtiver em `wait_seconds`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+b")
    try:
        fh.seek(0, 2)
        if fh.tell() < 1:
            fh.write(b"\0")
            fh.flush()
        deadline = time.monotonic() + max(0.0, wait_seconds)
        while not _try_lock(fh):
            if time.monotonic() >= deadline:
                raise SyncBusy(f"sync em andamento: {path.name}")
            time.sleep(poll_seconds)
        try:
            yield
        finally:
            _unlock(fh)
    finally:
        fh.close()
