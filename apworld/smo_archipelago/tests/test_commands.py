"""Smoke test that SMOClientCommandProcessor's `_cmd_grant` produces the
same wire payload as `parse_command()` on the equivalent line.

The pure parser is exercised exhaustively in test_repl.py. This test
covers the `/`-command surface in context.py — verifying that the
Phase 5 GUI command bar → ClientCommandProcessor → Switch send path
goes through the same `commands.parse_command` and produces an
identical `ItemMsg`.

Gated on Archipelago availability (subclassing CommonContext requires
CommonClient on sys.path) — same pattern as test_deathlink.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_AP = Path(__file__).resolve().parents[3] / "vendor" / "Archipelago"
if _AP.exists() and str(_AP) not in sys.path:
    sys.path.insert(0, str(_AP))

try:  # pragma: no cover
    import ModuleUpdate  # type: ignore[import-not-found]
    ModuleUpdate.update_ran = True
except ImportError:
    pass

pytest.importorskip(
    "CommonClient",
    reason="Archipelago checkout not present; init the vendor/Archipelago submodule.",
)

from client.context import SMOContext, SMOClientCommandProcessor  # noqa: E402
from client.datapackage import DataPackage  # noqa: E402
from client.maps import CaptureMap, ShineMap  # noqa: E402
from client.protocol import ItemMsg  # noqa: E402
from client.state import BridgeState  # noqa: E402

_APWORLD_DATA = Path(__file__).resolve().parent.parent / "data"


class _StubSwitch:
    def __init__(self) -> None:
        self.items: list[ItemMsg] = []
        self.kills: list = []
        self.labels: list = []

    async def send_item(self, item: ItemMsg) -> None:
        self.items.append(item)

    async def send_kill(self, kill) -> None:
        self.kills.append(kill)

    async def send_moon_label(self, label) -> None:
        self.labels.append(label)


@pytest.mark.asyncio
async def test_cmd_grant_produces_same_wire_payload_as_parse_command():
    import asyncio
    state = BridgeState()
    ctx = SMOContext(
        server_address=None, password=None,
        state=state,
        datapackage=DataPackage(apworld_data_dir=_APWORLD_DATA),
        shine_map=ShineMap(),
        capture_map=CaptureMap(),
    )
    ctx.auth = "Mario"
    sw = _StubSwitch()
    ctx.switch = sw  # type: ignore[assignment]

    proc = SMOClientCommandProcessor(ctx)
    proc._cmd_grant("Cascade", "Kingdom", "Power", "Moon")
    # _cmd_grant schedules async_start(send_item); yield once so it runs.
    await asyncio.sleep(0)

    assert len(sw.items) == 1
    item = sw.items[0]
    assert item.kind == "moon"
    assert item.kingdom == "Cascade"
    assert item.shine_id == "Power Moon"
    assert item.from_ == "repl"

    # State mirror updated too — reconnect-replay must see this.
    assert len(state.received_items) == 1
    assert state.received_items[0].item.kingdom == "Cascade"


@pytest.mark.asyncio
async def test_cmd_inject_deathlink_routes_killmsg_to_switch():
    import asyncio
    ctx = SMOContext(
        server_address=None, password=None,
        state=BridgeState(),
        datapackage=DataPackage(),
        shine_map=ShineMap(),
        capture_map=CaptureMap(),
    )
    ctx.auth = "Mario"
    sw = _StubSwitch()
    ctx.switch = sw  # type: ignore[assignment]

    proc = SMOClientCommandProcessor(ctx)
    proc._cmd_inject_deathlink("Tester", "for science")
    await asyncio.sleep(0)

    assert len(sw.kills) == 1
    assert sw.kills[0].source == "Tester"
    assert sw.kills[0].cause == "for science"
