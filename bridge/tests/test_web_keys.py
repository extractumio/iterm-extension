# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
"""AC-52: special keys for a tmux pane go by tmux's names, so tmux encodes them for the pane's
cursor mode (application cursor keys in mc and vim); text goes as it is."""
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("iterm2", types.ModuleType("iterm2"))

import asyncio  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from unittest import mock  # noqa: E402

from fbbridge.web import tmuxkeys  # noqa: E402
from fbbridge.web.tmuxkeys import key_names, parts  # noqa: E402


class KeyNamesTest(unittest.TestCase):
    def test_keys_by_name(self):
        self.assertEqual(key_names("\x1b[A"), ["Up"])
        self.assertEqual(key_names("\x1bOD\x1bOD"), ["Left", "Left"])
        self.assertEqual(key_names("\x1b[1;2D\x1b[1;5C"), ["S-Left", "C-Right"])
        self.assertEqual(key_names("\x1bOP\x1b[15~\x1b[24~"), ["F1", "F5", "F12"])
        self.assertEqual(key_names("\x1b[5~\x1b[6~\x1b[3~\x1b[H\x1b[F\x1b[Z"), ["PPage", "NPage", "DC", "Home", "End", "BTab"])

    def test_text_pastes_and_unnamed_keys_go_as_they_are(self):
        for data in ["ls\r", "\x1b", "\x1b[13;2u", "\x1b[200~text\x1b[201~", "\x1b[A ls", "", "\x1b[99~", "\x03"]:
            self.assertIsNone(key_names(data), repr(data))


    def test_a_batch_splits_into_runs_of_keys_and_the_text_between_in_order(self):
        self.assertEqual(parts("\x1b[A\x1b[Ahi \x1b[B"),
                         [(["Up", "Up"], "\x1b[A\x1b[A"), (None, "hi "), (["Down"], "\x1b[B")])
        self.assertEqual(parts("    "), [(None, "    ")], "held spaces are one piece of text")


class Tmux:
    def __init__(self):
        self.sent = []

    async def async_send_command(self, cmd):
        self.sent.append(("cmd", cmd))


class Pane:
    """A tmux -CC pane, or (tmux=None) a plain one; each send takes `delay` seconds."""

    def __init__(self, tmux=None, delay=0.0):
        self.tmux, self.delay, self.sent, self.session_id = tmux, delay, [], "s1"
        self.tab = types.SimpleNamespace(tmux_window_id="@1" if tmux else None, tmux_connection_id="c1", tab_id="t1")
        self.window = types.SimpleNamespace(current_tab=self.tab)

    async def async_get_variable(self, name):
        return "%3"

    async def async_send_text(self, text, suppress_broadcast=False):
        await asyncio.sleep(self.delay)
        self.sent.append(("text", text))
        if self.tmux:
            self.tmux.sent.append(("text", text))


class TypeIntoTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_tmux_pane_gets_each_run_of_keys_as_one_send_keys_in_order(self):
        tmux = Tmux()
        with mock.patch.object(tmuxkeys.iterm2, "async_get_tmux_connection_by_connection_id", lambda conn, cid: asyncio.sleep(0, tmux), create=True):
            via = await tmuxkeys.type_into(None, Pane(tmux), "\x1b[A\x1b[A\x1b[Ax\x1b[B")
        self.assertEqual(via, "keys")
        self.assertEqual(tmux.sent, [("cmd", "send-keys -t %3 Up Up Up"), ("text", "x"), ("cmd", "send-keys -t %3 Down")])


class BatchTest(unittest.TestCase):
    def test_keys_that_arrive_while_the_last_ones_are_typed_go_together(self):
        from fbbridge.web import mirror

        class Ws:
            async def send(self, text):
                pass

        client = mirror.Client(None, types.SimpleNamespace(app=None, suspect=lambda sid: False), Ws(), 1000, None)
        client.session, client.show_in_iterm = Pane(delay=0.1), False      # every send takes 100 ms

        async def hold():
            t = time.perf_counter()
            for k in range(30):                           # a key held for 1 s: 30 repeats
                await client.handle({"t": "in", "data": "\x1b[B" if k % 2 else " "})
                await asyncio.sleep(1 / 30)
            await client.typer
            return time.perf_counter() - t
        took = asyncio.run(hold())
        sent = client.session.sent
        self.assertEqual("".join(t for _, t in sent), "".join("\x1b[B" if k % 2 else " " for k in range(30)), "all of it, in order")
        self.assertLessEqual(len(sent), 12, f"{len(sent)} sends for 30 keys")
        self.assertLess(took, 1.4, "not 30 round trips of 100 ms")


if __name__ == "__main__":
    unittest.main()
