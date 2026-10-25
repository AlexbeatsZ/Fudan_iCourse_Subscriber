import contextlib
import io
import os
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call, patch

import requests

from desktop import downloader
from scripts import check_new_replays as check


API_URL = "https://api.github.com/repos/owner/repo/git/ref/heads/data"


def http_error(status, url=API_URL, headers=None):
    response = requests.Response()
    response.status_code = status
    response.url = url
    response.headers.update(headers or {})
    return requests.HTTPError(f"secret diagnostic: {url}", response=response)


class ReplayProbeTests(unittest.TestCase):
    def run_main(self, output, outcomes):
        with (patch.object(check, "settings", return_value={"courses": ["1"]}),
              patch.object(check, "probe", side_effect=outcomes) as probe,
              patch.object(check.time, "sleep") as sleep,
              patch.dict(os.environ, {"COURSE_IDS": "1", "GITHUB_OUTPUT": str(output)}),
              contextlib.redirect_stdout(io.StringIO()) as logs):
            check.main()
        return probe, sleep, logs.getvalue()

    def test_transient_failure_recovers_without_skipping_work(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            probe, sleep, logs = self.run_main(output, [http_error(502), True])
            self.assertEqual(probe.call_count, 2)
            sleep.assert_called_once_with(5)
            self.assertEqual(output.read_text(), "needed=true\n")
            self.assertIn("HTTP 502, api.github.com", logs)
            self.assertNotIn("secret diagnostic", logs)

    def test_repeated_failure_never_publishes_no_work(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            with self.assertRaises(requests.HTTPError):
                self.run_main(output, [http_error(503)] * 3)
            self.assertFalse(output.exists())

    def test_permanent_permission_error_is_not_retried(self):
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(check, "probe", side_effect=http_error(403)) as probe,
              patch.object(check, "settings", return_value={"courses": ["1"]}),
              patch.dict(os.environ, {"COURSE_IDS": "1", "GITHUB_OUTPUT": str(Path(directory) / "output")}),
              self.assertRaises(requests.HTTPError)):
            check.main()
        probe.assert_called_once()

    def test_rate_limit_and_network_failures_can_retry(self):
        for error in [http_error(403, headers={"X-RateLimit-Remaining": "0"}),
                      http_error(429), requests.Timeout(), requests.ConnectionError(),
                      requests.exceptions.JSONDecodeError("Invalid JSON", "<html>", 0)]:
            with self.subTest(error=type(error).__name__):
                self.assertTrue(check.transient_error(error))

    def test_missing_course_ids_skips_probe_until_subscription_initialized(self):
        with tempfile.TemporaryDirectory() as directory:
            for value in ("", "  "):
                output = Path(directory) / "output"
                with (self.subTest(value=value),
                      patch.dict(os.environ, {"COURSE_IDS": value, "GITHUB_OUTPUT": str(output)}),
                      patch.object(check, "probe") as probe):
                    check.main()
                probe.assert_not_called()
                self.assertEqual(output.read_text(), "needed=false\n")
                output.unlink()

    def test_invalid_course_ids_fail_before_login(self):
        with (patch.dict(os.environ, {"COURSE_IDS": "40243,not-a-course"}),
              patch.object(check, "probe") as probe,
              self.assertRaises(ValueError)):
            check.main()
        probe.assert_not_called()

    def test_probe_requests_rekey_even_without_new_lectures(self):
        client = Mock()
        client.get_course_detail.return_value = {"lectures": []}
        with tempfile.TemporaryDirectory() as directory:
            dbpath = Path(directory) / "empty.db"
            sqlite3.connect(dbpath).close()
            with (patch.object(check, "login", return_value=client),
                  patch.object(check, "cloud_database",
                               side_effect=lambda cfg: cfg.update(_needs_rekey=True) or dbpath)):
                self.assertTrue(check.probe({"repository": "owner/repo", "courses": ["1"]}))

    def test_error_summary_omits_signed_paths_and_query(self):
        error = http_error(502, "https://webvpn.fudan.edu.cn/private/ticket?token=secret")
        self.assertEqual(check.error_summary(error), "HTTPError (HTTP 502, webvpn.fudan.edu.cn)")
        self.assertEqual(check.error_summary(requests.Timeout("token=secret")), "Timeout")
        self.assertIn("COURSE_IDS", check.error_summary(RuntimeError("COURSE_IDS is not set")))
        self.assertEqual(check.error_summary(RuntimeError("token=secret")), "RuntimeError")

    def test_only_missing_data_branch_is_first_run(self):
        config = {"repository": "owner/repo", "courses": ["1"]}
        for url, first_run in [(API_URL, True), ("https://codeload.github.com/owner/repo/zip/sha", False)]:
            client = Mock()
            with (self.subTest(url=url), patch.object(check, "login", return_value=client),
                  patch.object(check, "cloud_database", side_effect=http_error(404, url)),
                  contextlib.redirect_stdout(io.StringIO())):
                if first_run:
                    self.assertTrue(check.probe(config))
                else:
                    with self.assertRaises(requests.HTTPError):
                        check.probe(config)
            client.vpn.session.close.assert_called_once()

    def test_github_token_is_scoped_to_api_request(self):
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(downloader, "RUNTIME", Path(directory)),
              patch.object(downloader, "credentials", return_value=("student", "uis")),
              patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}),
              patch("requests.get", side_effect=[Mock(json=lambda: {"object": {"sha": "abc"}}),
                                                Mock(raise_for_status=Mock(side_effect=http_error(503)))]) as get):
            with self.assertRaises(requests.HTTPError):
                downloader.cloud_database({"repository": "owner/repo"})
        self.assertEqual(get.call_args_list, [
            call(API_URL, headers={"Accept": "application/vnd.github+json",
                                   "Authorization": "Bearer test-token"}, timeout=30),
            call("https://codeload.github.com/owner/repo/zip/abc", timeout=120),
        ])

    def test_public_api_still_works_without_token(self):
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(downloader, "RUNTIME", Path(directory)),
              patch.dict(os.environ, {"GITHUB_TOKEN": ""}),
              patch("requests.get", side_effect=http_error(404)) as get,
              self.assertRaises(requests.HTTPError)):
            downloader.cloud_database({"repository": "owner/repo"})
        self.assertNotIn("Authorization", get.call_args.kwargs["headers"])


if __name__ == "__main__":
    unittest.main()
