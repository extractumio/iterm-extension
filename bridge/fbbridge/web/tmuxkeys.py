# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
"""Special keys for a tmux -CC pane (AC-52). The page sends keys as xterm bytes in normal
cursor mode; text sent to a tmux pane arrives unchanged, so a program that switched to
application cursor keys (mc, vim) gets the wrong ones. tmux's own key names are encoded by
tmux for the pane's current mode, so keys the page sends go to tmux by name."""
import re

import iterm2

BASE = {"A": "Up", "B": "Down", "C": "Right", "D": "Left", "H": "Home", "F": "End",
        "P": "F1", "Q": "F2", "R": "F3", "S": "F4"}
TILDE = {"2": "IC", "3": "DC", "5": "PPage", "6": "NPage", "15": "F5", "17": "F6", "18": "F7",
         "19": "F8", "20": "F9", "21": "F10", "23": "F11", "24": "F12"}
MODS = {"2": "S-", "3": "M-", "4": "M-S-", "5": "C-", "6": "C-S-", "7": "C-M-", "8": "C-M-S-"}
KEY = re.compile(r"\x1b(?:\[(?:1;([2-8]))?([ABCDHF])|O([ABCDHFPQRS])|\[(\d{1,2})(?:;([2-8]))?~|\[(Z))")


def _name(m):
    """tmux's name for one matched key, or None when tmux has none."""
    mod, csi, ss3, num, num_mod, back = m.groups()
    if back:
        return "BTab"
    if num:
        return MODS.get(num_mod, "") + TILDE[num] if num in TILDE else None
    return MODS.get(mod, "") + BASE[csi or ss3]


def parts(data):
    """`data` in order as [(names, text)]: runs of special keys tmux can name (names a list) and
    the text between them (names None: text, a paste, a key tmux could not name)."""
    out, text, i = [], "", 0
    while i < len(data):
        m = KEY.match(data, i)
        name = _name(m) if m else None
        if not name:
            text, i = text + data[i], i + 1
            continue
        if text:
            out.append((None, text))
            text = ""
        if out and out[-1][0] is not None:
            out[-1] = (out[-1][0] + [name], out[-1][1] + m.group(0))
        else:
            out.append(([name], m.group(0)))
        i = m.end()
    if text:
        out.append((None, text))
    return out


def key_names(data):
    """tmux key names for `data` when it is made only of special keys, else None."""
    p = parts(data)
    return p[0][0] if len(p) == 1 else None


async def type_into(conn, session, data):
    """Text as it is; special keys for a tmux pane by tmux's names, which tmux encodes for the
    pane's cursor mode (mc and vim switch to application cursor keys). `data` may hold many
    keys (typed while the last ones were on their way): each run of special keys goes as one
    "send-keys", the text between as it is, in order. Says which way it went."""
    tab = session.tab
    split = parts(data)
    if any(names for names, _ in split) and tab and tab.tmux_window_id not in (None, "-1"):
        pane = await session.async_get_variable("tmuxWindowPane")
        tc = await iterm2.async_get_tmux_connection_by_connection_id(conn, tab.tmux_connection_id)
        if tc and pane not in (None, ""):
            for names, text in split:
                if names:
                    await tc.async_send_command(f"send-keys -t %{str(pane).lstrip('%')} {' '.join(names)}")
                else:
                    await session.async_send_text(text, suppress_broadcast=True)
            return "keys"
    await session.async_send_text(data, suppress_broadcast=True)
    return "text"
