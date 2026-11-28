"""Offline regression checks for the profile contribution generator."""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parent / "scripts" / "update_contributions.py"
spec = importlib.util.spec_from_file_location("update_contributions", SCRIPT)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(["gh", "api"], returncode, stdout, stderr)


def fixture_pr():
    return {
        "repository": {"nameWithOwner": "example/project"},
        "number": 12,
        "title": "Fix metadata",
        "url": "https://github.com/example/project/pull/12",
        "closedAt": "2026-10-26T00:00:00Z",
    }


class StarsTests(unittest.TestCase):
    def test_valid_counts_keep_existing_gh_command(self):
        for count in (0, 42):
            with self.subTest(count=count):
                with patch.object(
                    updater.subprocess, "run", return_value=completed(stdout=str(count))
                ) as run:
                    self.assertEqual(updater.stars("example/project"), count)
                    run.assert_called_once_with(
                        ["gh", "api", "repos/example/project", "--jq", ".stargazers_count"],
                        capture_output=True,
                        text=True,
                    )

    def test_http_404_retains_missing_repository_fallback(self):
        for stderr in ("gh: Not Found (HTTP 404)", "HTTP 404: Not Found"):
            with self.subTest(stderr=stderr):
                with patch.object(
                    updater.subprocess, "run", return_value=completed(1, stderr=stderr)
                ):
                    self.assertIsNone(updater.stars("example/deleted"))

    def test_http_403_and_429_fail_closed(self):
        for status in (403, 429):
            with self.subTest(status=status):
                with patch.object(
                    updater.subprocess,
                    "run",
                    return_value=completed(1, stderr=f"gh: failure (HTTP {status})"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "example/project"):
                        updater.stars("example/project")

    def test_other_transport_failures_fail_closed(self):
        with patch.object(
            updater.subprocess, "run", return_value=completed(128, stderr="network error")
        ):
            with self.assertRaises(RuntimeError):
                updater.stars("example/project")

    def test_invalid_successful_responses_fail_closed(self):
        for body in ("", "null", "-1", "1.5", "not-a-number"):
            with self.subTest(body=body):
                with patch.object(
                    updater.subprocess, "run", return_value=completed(stdout=body)
                ):
                    with self.assertRaises(ValueError):
                        updater.stars("example/project")

    def test_api_failure_never_writes_readme(self):
        with (
            patch.object(updater, "merged_prs", return_value=[fixture_pr()]),
            patch.object(
                updater.subprocess,
                "run",
                return_value=completed(1, stderr="gh: rate limit (HTTP 429)"),
            ),
            patch.object(Path, "write_text") as write_text,
            patch.object(sys, "argv", ["update_contributions.py"]),
        ):
            with self.assertRaises(RuntimeError):
                updater.main()
            write_text.assert_not_called()

    def test_valid_data_preserves_readme_row_format(self):
        with patch.object(updater.subprocess, "run", return_value=completed(stdout="42")):
            rendered = updater.section([fixture_pr()])
        self.assertIn(
            "| [example/project](https://github.com/example/project) · ★ 42 "
            "| [#12 Fix metadata](https://github.com/example/project/pull/12) |",
            rendered,
        )

    def test_missing_repository_preserves_readme_row_format(self):
        with patch.object(
            updater.subprocess, "run", return_value=completed(1, stderr="HTTP 404")
        ):
            rendered = updater.section([fixture_pr()])
        self.assertIn(
            "| [example/project](https://github.com/example/project) "
            "| [#12 Fix metadata](https://github.com/example/project/pull/12) |",
            rendered,
        )


if __name__ == "__main__":
    unittest.main()
