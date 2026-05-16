"""Test path setup.

Tests import the client modules as a top-level package
(`from client.X import Y`) — to do that we put `apworld/smo_archipelago/`
on sys.path so `client/` is discovered as a top-level package.

We intentionally do NOT put vendor/Archipelago on sys.path here. Doing so
triggers Archipelago's apworld discovery machinery (worlds/__init__.py
walks custom_worlds/ at import time), which both pulls in unmet
dependencies of unrelated worlds (pyevermizer, requests, zilliandomizer)
AND collides our loose-source apworld with the zipped one in
custom_worlds/ on AutoWorldRegister. The two opt-in live-AP tests
(test_ap_loopback, test_apworld_generation, both gated on SMOAP_LIVE_AP=1)
handle their own Archipelago path setup via subprocess invocations of
scripts/ap_generate.py / scripts/ap_server.py — they don't need
Archipelago importable from this process.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_APWORLD_ROOT = _HERE.parent  # apworld/smo_archipelago/

s = str(_APWORLD_ROOT)
if _APWORLD_ROOT.exists() and s not in sys.path:
    sys.path.insert(0, s)
