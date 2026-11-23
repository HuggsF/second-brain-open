"""Lock do sistema operacional: um unico escritor por vez."""
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from core.sync_lock import SyncBusy, sync_lock

ROOT = Path(__file__).resolve().parent.parent
BUSY_EXIT = 42


class TestSyncLock(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "sub" / "sync.lock"

    def test_second_holder_gets_busy(self):  # CA-05
        with sync_lock(self.path):
            with self.assertRaises(SyncBusy):
                with sync_lock(self.path):
                    pass

    def test_released_after_exit(self):
        with sync_lock(self.path):
            pass
        with sync_lock(self.path):
            pass

    def test_released_after_exception(self):
        with self.assertRaises(RuntimeError):
            with sync_lock(self.path):
                raise RuntimeError("queda")
        with sync_lock(self.path):
            pass

    def test_wait_gives_up(self):
        with sync_lock(self.path):
            t0 = time.monotonic()
            with self.assertRaises(SyncBusy):
                with sync_lock(self.path, wait_seconds=0.3, poll_seconds=0.05):
                    pass
            self.assertGreaterEqual(time.monotonic() - t0, 0.3)

    def test_other_process_gets_busy(self):
        script = (
            "import sys\n"
            "from pathlib import Path\n"
            "from core.sync_lock import SyncBusy, sync_lock\n"
            "try:\n"
            "    with sync_lock(Path(sys.argv[1])):\n"
            "        sys.exit(0)\n"
            "except SyncBusy:\n"
            f"    sys.exit({BUSY_EXIT})\n"
        )
        with sync_lock(self.path):
            held = subprocess.run([sys.executable, "-c", script, str(self.path)], cwd=ROOT, timeout=60)
        self.assertEqual(held.returncode, BUSY_EXIT)
        free = subprocess.run([sys.executable, "-c", script, str(self.path)], cwd=ROOT, timeout=60)
        self.assertEqual(free.returncode, 0)


if __name__ == "__main__":
    unittest.main()
