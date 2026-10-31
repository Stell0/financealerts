import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/commit_runtime.sh"
PUSH_SCRIPT = SCRIPT.with_name("push_runtime.sh")


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
            (root / "config/securities.csv").write_text("security_id,ticker\npublic,AAPL\n")
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
                {"config/tickers.txt", "config/securities.csv", "data/TSLA.csv", "data/alert_state.json"},
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

    def remote_fixture(self, directory):
        root = Path(directory)
        upstream = root / "upstream"
        upstream.mkdir()
        self.seed(upstream)
        self.git(upstream, "branch", "-M", "main")
        remote = root / "remote.git"
        self.git(root, "init", "--bare", "--initial-branch=main", str(remote))
        self.git(upstream, "remote", "add", "origin", str(remote))
        self.git(upstream, "push", "origin", "main")
        runner = root / "runner"
        self.git(root, "clone", str(remote), str(runner))
        (runner / "data/TSLA.csv").write_text("Date,Close\n2026-10-19,101\n")
        subprocess.run(["bash", str(SCRIPT)], cwd=runner, check=True, capture_output=True)
        return upstream, remote, runner

    def push_runtime(self, runner):
        return subprocess.run(
            ["bash", str(PUSH_SCRIPT)], cwd=runner, capture_output=True, text=True,
            env={**os.environ, "TARGET_BRANCH": "main"},
        )

    def commit_upstream(self, upstream):
        self.git(upstream, "add", ".")
        self.git(
            upstream, "-c", "user.name=Test", "-c",
            "user.email=test@example.invalid", "commit", "-qm", "Upstream update",
        )
        self.git(upstream, "push", "origin", "main")

    def test_runtime_push_preserves_new_upstream_source_and_local_state(self):
        with tempfile.TemporaryDirectory() as directory:
            upstream, remote, runner = self.remote_fixture(directory)
            (upstream / "README.md").write_text("New source documentation\n")
            self.commit_upstream(upstream)
            upstream_head = self.git(upstream, "rev-parse", "HEAD")
            result = self.push_runtime(runner)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.git(runner, "rev-parse", "HEAD^"), upstream_head)
            self.assertEqual((runner / "README.md").read_text(), "New source documentation\n")
            self.assertEqual(
                self.git(remote, "show", "main:data/TSLA.csv"),
                "Date,Close\n2026-10-19,101",
            )
            head = self.git(runner, "rev-parse", "HEAD")
            self.assertEqual(self.push_runtime(runner).returncode, 0)
            self.assertEqual(self.git(runner, "rev-parse", "HEAD"), head)

    def test_runtime_push_conflict_preserves_local_recovery_and_upstream(self):
        with tempfile.TemporaryDirectory() as directory:
            upstream, remote, runner = self.remote_fixture(directory)
            local_head = self.git(runner, "rev-parse", "HEAD")
            (upstream / "data/TSLA.csv").write_text("Date,Close\n2026-10-19,102\n")
            self.commit_upstream(upstream)
            upstream_head = self.git(remote, "rev-parse", "main")
            result = self.push_runtime(runner)
            self.assertEqual(result.returncode, 1)
            self.assertIn("retained locally for recovery", result.stderr)
            self.assertEqual(self.git(runner, "rev-parse", "HEAD"), local_head)
            self.assertEqual(self.git(remote, "rev-parse", "main"), upstream_head)
            self.assertEqual((runner / "data/TSLA.csv").read_text(), "Date,Close\n2026-10-19,101\n")
            self.assertEqual(self.git(runner, "status", "--porcelain"), "")

    def test_runtime_push_retries_a_transient_push_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            _, remote, runner = self.remote_fixture(directory)
            hook = remote / "hooks/pre-receive"
            hook.write_text(
                '#!/bin/sh\nif [ ! -f rejected-once ]; then\n'
                '  touch rejected-once\n  exit 1\nfi\n'
            )
            hook.chmod(0o755)
            result = self.push_runtime(runner)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Runtime push attempt 1 failed", result.stderr)
            self.assertEqual(
                self.git(remote, "rev-parse", "main"), self.git(runner, "rev-parse", "HEAD")
            )

    def test_runtime_push_stops_after_three_rejections_without_losing_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            _, remote, runner = self.remote_fixture(directory)
            local_head = self.git(runner, "rev-parse", "HEAD")
            upstream_head = self.git(remote, "rev-parse", "main")
            hook = remote / "hooks/pre-receive"
            hook.write_text('#!/bin/sh\necho rejected >> rejected-attempts\nexit 1\n')
            hook.chmod(0o755)
            result = self.push_runtime(runner)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len((remote / "rejected-attempts").read_text().splitlines()), 3)
            self.assertEqual(self.git(runner, "rev-parse", "HEAD"), local_head)
            self.assertEqual(self.git(remote, "rev-parse", "main"), upstream_head)
