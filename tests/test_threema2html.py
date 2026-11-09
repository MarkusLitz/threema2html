import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import threema2html


class Threema2HtmlTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="t2h_test_")
        self.orig_cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_input(self, content, filename="messages.txt"):
        path = os.path.join(self.tmpdir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _run_main(self, argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            threema2html.main(argv)
        return stdout.getvalue(), stderr.getvalue()

    def test_single_file_search_embedded_by_default(self):
        with open(os.path.join(self.tmpdir, "photo.jpg"), "wb") as f:
            f.write(b"fakejpg")
        inp = self._write_input(
            "[01.01.2026, 10:00:00] Ich: Hallo!\n"
            "[01.01.2026, 10:01:00] Du: Multi line 1\n"
            "Multi line 2 <photo.jpg>\n"
        )
        out, err = self._run_main([inp])

        self.assertIn("2 output messages.", err)
        self.assertIn('id="m1"', out)
        self.assertIn('id="m2"', out)
        self.assertIn(".t2h-search", out)
        self.assertIn("ensureIndex", out)
        self.assertIn("<br/>Multi line 2", out)
        self.assertNotIn("</br>", out)
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "media", "photo.jpg")))

        # Verify no unsafe DOM sinks appear in embedded script
        for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
            self.assertNotIn(forbidden, threema2html.CHAT_SEARCH_JS)
            self.assertNotIn(forbidden, threema2html.INDEX_SEARCH_JS)

    def test_no_search_flag_disables_embedded_js(self):
        inp = self._write_input("[01.01.2026, 10:00:00] Ich: Plain export\n")
        out, _ = self._run_main(["--no-search", inp])

        self.assertNotIn("<script>", out)
        self.assertNotIn(".t2h-search", out)
        self.assertIn('id="m1"', out)

    def test_split_month_generates_index_and_search_index_js(self):
        inp = self._write_input(
            "[01.01.2025, 10:00:00] Ich: First year\n"
            "[01.12.2025, 11:00:00] Du: End of 2025\n"
            "Second line in Dec\n"
            "[02.01.2026, 09:30:00] Ich: Happy 2026\n"
        )
        _, err = self._run_main(["--split", "month", "-n", "Markus", inp])

        self.assertIn("3 output messages.", err)
        for expected in (
            "index.html",
            "search_index.js",
            "chat_2025_01.html",
            "chat_2025_12.html",
            "chat_2026_01.html",
        ):
            self.assertTrue(os.path.exists(expected), f"Missing {expected}")

        with open("index.html", "r", encoding="utf-8") as f:
            idx_html = f.read()
        self.assertIn('id="t2h-index-search"', idx_html)
        self.assertIn("search_index.js", idx_html)

        with open("chat_2025_12.html", "r", encoding="utf-8") as f:
            dec_html = f.read()
        self.assertIn('href="index.html"', dec_html)
        self.assertIn(".t2h-search", dec_html)

        with open("search_index.js", "r", encoding="utf-8") as f:
            raw_js = f.read().strip()
        prefix = "window.__THREEMA_SEARCH_INDEX__ = "
        self.assertTrue(raw_js.startswith(prefix))
        self.assertTrue(raw_js.endswith(";"))
        payload = json.loads(raw_js[len(prefix) : -1])

        self.assertEqual(
            payload["files"],
            ["chat_2025_01.html", "chat_2025_12.html", "chat_2026_01.html"],
        )
        self.assertEqual(payload["senders"], ["Markus", "Du"])
        self.assertEqual(len(payload["messages"]), 3)
        self.assertEqual(payload["messages"][1][4], "End of 2025\nSecond line in Dec")

    def test_split_with_no_search_skips_search_index_js(self):
        inp = self._write_input("[01.01.2026, 10:00:00] Ich: Split without JS\n")
        self._run_main(["--split", "year", "--no-search", inp])

        self.assertTrue(os.path.exists("index.html"))
        self.assertTrue(os.path.exists("chat_2026.html"))
        self.assertFalse(os.path.exists("search_index.js"))
        with open("index.html", "r", encoding="utf-8") as f:
            self.assertNotIn("<script>", f.read())

    def test_filtered_multiline_message_does_not_leak_continuation(self):
        inp = self._write_input(
            "[01.01.2026, 10:00:00] Ich: Kept message\n"
            "Kept line 2\n"
            "[01.02.2026, 10:00:00] Du: Filtered out header\n"
            "Filtered out continuation line\n"
            "[01.03.2026, 10:00:00] Ich: Also filtered\n"
        )
        out, err = self._run_main(["-f", "20260101", "-t", "20260131", inp])

        self.assertIn("1 output messages.", err)
        self.assertIn("Kept message", out)
        self.assertIn("Kept line 2", out)
        self.assertNotIn("Filtered out", out)
        self.assertEqual(out.count('<div class="date">'), 1)

    def test_xss_and_path_traversal_hardening(self):
        secret_file = os.path.join(os.path.dirname(self.tmpdir), "outside_secret.jpg")
        inp = self._write_input(
            '[01.01.2026, 10:00:00] <img onerror=alert(1)>: </script><script>alert("xss")</script> <../outside_secret.jpg>\n'
        )
        out, _ = self._run_main(
            [
                "--split",
                "year",
                "-T",
                'My "</title><script>alert(1)</script>',
                "-s",
                'style.css" onload="alert(1)',
                inp,
            ]
        )
        with open("chat_2026.html", "r", encoding="utf-8") as f:
            chat_html = f.read()
        with open("search_index.js", "r", encoding="utf-8") as f:
            idx_js = f.read()

        self.assertNotIn("</title><script>", chat_html)
        self.assertNotIn('onload="alert(1)"', chat_html)
        self.assertNotIn("<img onerror=alert(1)>", chat_html)
        self.assertNotIn('</script><script>alert("xss")', chat_html)
        self.assertNotIn("</script>", idx_js)
        self.assertIn("\\u003c/script\\u003e", idx_js)
        self.assertFalse(os.path.exists(secret_file))

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_embedded_javascript_syntax(self):
        for label, script in (
            ("CHAT_SEARCH_JS", threema2html.CHAT_SEARCH_JS),
            ("INDEX_SEARCH_JS", threema2html.INDEX_SEARCH_JS),
        ):
            proc = subprocess.run(
                ["node", "--check"],
                input=script,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, f"{label} syntax error: {proc.stderr}")


if __name__ == "__main__":
    unittest.main()
