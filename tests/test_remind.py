"""CLI tests (standard library only): python3 -m unittest discover tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parent.parent / "backend" / "remind.py"


class Remind(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("REMIND_PANE_")}
        self.env.update(REMIND_PANE_DATA=self.tmp.name, REMIND_PANE_TZ="Europe/Berlin")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, ok=True, env=None):
        r = subprocess.run([sys.executable, "-I", str(CLI), *args], capture_output=True, text=True, env=env or self.env)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def items(self):
        return json.loads(self.run_cli("list", "--json").stdout)

    def test_data_dir_expands_tilde(self):
        env = dict(self.env, HOME=self.tmp.name, REMIND_PANE_DATA="~/rem")
        self.run_cli("add", "--text", "x", env=env)
        self.assertTrue((Path(self.tmp.name) / "rem" / "reminders.json").exists())

    def test_add_list_done_del(self):
        self.run_cli("add", "--text", "buy milk")
        self.run_cli("add", "--text", "call Anna", "--when", "+1d", "--repeat", "daily")
        items = self.items()
        self.assertEqual([i["text"] for i in items], ["call Anna", "buy milk"])  # dated first
        self.assertEqual(items[0]["repeat"], "daily")
        self.assertIsNone(items[1]["due"])
        self.run_cli("done", items[1]["id"])
        self.assertIn("~~buy milk~~", self.run_cli("list").stdout)
        self.run_cli("undone", items[1]["id"])
        self.run_cli("del", "1")
        self.assertEqual([i["text"] for i in self.items()], ["buy milk"])

    def test_errors(self):
        self.assertEqual(self.run_cli("add", "--text", "x", "--repeat", "daily", ok=False).returncode, 1)
        self.assertEqual(self.run_cli("add", "--text", "x", "--when", "2001-01-01 10:00", ok=False).returncode, 1)
        self.assertEqual(self.run_cli("add", "--text", "x", "--when", "soon", ok=False).returncode, 1)
        self.assertEqual(self.run_cli("done", "nope", ok=False).returncode, 1)

    def test_absolute_time_uses_zone(self):
        self.run_cli("add", "--text", "x", "--when", "2099-01-01 12:00")
        self.assertEqual(self.items()[0]["due"], "2099-01-01 12:00 CET")

    def test_shift(self):
        self.run_cli("add", "--text", "x", "--when", "+1h")
        before = self.items()[0]["due"]
        self.run_cli("shift", "1", "--by=+1d")
        self.assertNotEqual(self.items()[0]["due"], before)

    def test_tick_needs_telegram(self):
        r = self.run_cli("tick", ok=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not configured", r.stderr)


if __name__ == "__main__":
    unittest.main()
