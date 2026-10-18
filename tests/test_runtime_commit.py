import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/commit_runtime.sh"


class RuntimeCommitTests(unittest.TestCase):
    def git(self, directory, *args):
        return subprocess.check_output(
            ["git", "-C", str(directory), *args], text=True, stderr=subprocess.STDOUT
        ).strip()

    def seed(self, directory):
        root = Path(directory)
        (root / "data").mkdir()
        (root / "config").mkdir()
        (root / "data/TSLA.csv").write_text("Date,Close\n2026-10-16,100\n")
        (root / "config/tickers.txt").write_text("TSLA\n")
        self.git(root, "init", "-q")
        self.git(root, "add", "config", "data")
        self.git(
            root,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Initial fixture",
        )
        return root

    def test_no_change_run_does_not_attempt_empty_commit_and_only_runtime_paths_commit(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = self.seed(directory)
            before = self.git(root, "rev-parse", "HEAD")
            subprocess.run(
                ["bash", str(SCRIPT)], cwd=root, check=True, capture_output=True
            )
            self.assertEqual(before, self.git(root, "rev-parse", "HEAD"))
            (root / "data/alert_state.json").write_text(
                '{"version":1,"delivered":{}}\n'
            )
            (root / "data/TSLA.csv").write_text("Date,Close\n2026-10-19,101\n")
            (root / "config/tickers.txt").write_text("AAPL\nTSLA\n")
            (root / ".env").write_text("PRIVATE=must-not-be-committed\n")
            subprocess.run(
                ["bash", str(SCRIPT)], cwd=root, check=True, capture_output=True
            )
            self.assertNotEqual(before, self.git(root, "rev-parse", "HEAD"))
            self.assertEqual(
                set(
                    self.git(
                        root, "show", "--format=", "--name-only", "HEAD"
                    ).splitlines()
                ),
                {"config/tickers.txt", "data/TSLA.csv", "data/alert_state.json"},
            )
            after = self.git(root, "rev-parse", "HEAD")
            subprocess.run(
                ["bash", str(SCRIPT)], cwd=root, check=True, capture_output=True
            )
            self.assertEqual(after, self.git(root, "rev-parse", "HEAD"))

    def test_refuses_preexisting_unrelated_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.seed(directory)
            (root / "unrelated.txt").write_text("unrelated")
            self.git(root, "add", "unrelated.txt")
            result = subprocess.run(
                ["bash", str(SCRIPT)], cwd=root, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("Unexpected pre-existing", result.stderr)
