"""Tests for the ItemMsg.from_ Cappy-suppression filter in SMOContext.

`shouldShowCappyMsg` (switch-mod/src/ui/CappyMessenger.cpp) treats an empty
`from` field as "do not surface a Cappy bubble." The bridge collapses
`from_` to "" only on the gameplay self-find path (AP routed the item we
just checked back to ourselves). Server-injected items (`/send`, releases,
collects) and items from other real players still get a bubble.

Run with the bridge venv:
  bridge/.venv/Scripts/python -m pytest \
      apworld/smo_archipelago/tests/test_cappy_from_filter.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add vendor/Archipelago BEFORE the import-skip so CommonClient is reachable.
_AP = Path(__file__).resolve().parents[3] / "vendor" / "Archipelago"
if _AP.exists() and str(_AP) not in sys.path:
    sys.path.insert(0, str(_AP))

try:  # pragma: no cover
    import ModuleUpdate  # type: ignore[import-not-found]
    ModuleUpdate.update_ran = True
except ImportError:
    pass

CommonClient = pytest.importorskip(
    "CommonClient",
    reason="Archipelago checkout not present; init the vendor/Archipelago submodule.",
)

from client.context import SMOContext  # noqa: E402
from client.datapackage import DataPackage  # noqa: E402
from client.maps import CaptureMap, ShineMap  # noqa: E402
from client.state import BridgeState  # noqa: E402


class _StubSwitch:
    def __init__(self) -> None:
        self.items: list = []

    async def send_item(self, item) -> None:
        self.items.append(item)

    async def send_kill(self, k) -> None:  # pragma: no cover - unused here
        pass

    async def send_print(self, text: str) -> None:  # pragma: no cover - unused here
        pass

    async def send_ap_state(self, conn: str) -> None:  # pragma: no cover - unused here
        pass


_ITEM_ID = 4242
_ITEM_NAME = "Goomba"


def _make_ctx(*, my_slot: int = 1) -> tuple[SMOContext, _StubSwitch]:
    """Build an SMOContext wired enough to receive a ReceivedItems packet
    and route the resulting ItemMsg to a stub switch.

    The DataPackage gets a single fabricated item registered under id
    `_ITEM_ID` so the classify path resolves to a known name (kind doesn't
    matter — the `from_` collapse runs regardless of item kind).
    """
    dp = DataPackage()
    dp.item_id_to_name[_ITEM_ID] = _ITEM_NAME
    dp.item_name_to_id[_ITEM_NAME] = _ITEM_ID
    dp._item_categories[_ITEM_NAME] = ["capture"]  # so classify_item -> CAPTURE
    ctx = SMOContext(
        server_address=None,
        password=None,
        state=BridgeState(),
        datapackage=dp,
        shine_map=ShineMap(),
        capture_map=CaptureMap(),
    )
    ctx.auth = "Mario"
    ctx.slot = my_slot
    ctx.team = 0
    # Stand in for what AP's Connected handler normally writes; covers the
    # three slot indices our scenarios reference.
    ctx.player_names = {0: "Archipelago", 1: "Mario", 2: "Player2"}
    sw = _StubSwitch()
    ctx.switch = sw  # type: ignore[assignment]
    return ctx, sw


async def _drive(ctx: SMOContext, sender_idx: int | None) -> None:
    ni = {"item": _ITEM_ID, "player": sender_idx, "flags": 0}
    await ctx._handle_ap_package("ReceivedItems", {"items": [ni]})


# ---------------------------------------------------------------- scenarios


@pytest.mark.asyncio
async def test_other_player_keeps_real_sender_name():
    """Real other-player check → bubble should fire → `from_` is the name."""
    ctx, sw = _make_ctx(my_slot=1)
    await _drive(ctx, sender_idx=2)
    assert len(sw.items) == 1
    assert sw.items[0].from_ == "Player2"


@pytest.mark.asyncio
async def test_self_find_collapses_to_empty():
    """Sender == our own slot → silence Cappy → `from_` is empty."""
    ctx, sw = _make_ctx(my_slot=1)
    await _drive(ctx, sender_idx=1)
    assert len(sw.items) == 1
    assert sw.items[0].from_ == ""


@pytest.mark.asyncio
async def test_server_grant_keeps_sender_name():
    """Admin /send / release / collect arrive with player == 0 and should
    still surface a Cappy bubble — only gameplay self-finds suppress."""
    ctx, sw = _make_ctx(my_slot=1)
    await _drive(ctx, sender_idx=0)
    assert len(sw.items) == 1
    assert sw.items[0].from_ == "Archipelago"


@pytest.mark.asyncio
async def test_unattributed_sender_passes_self_string_through():
    """`sender_idx is None` is a wire oddity (no `player` field on the
    NetworkItem) that should not be mistaken for a self-find. `_sender_name`
    returns "self" for None — bubble fires, the C++ side renders it."""
    ctx, sw = _make_ctx(my_slot=1)
    await _drive(ctx, sender_idx=None)
    assert len(sw.items) == 1
    assert sw.items[0].from_ == "self"


# ---------------------------------------------------------------- state side


@pytest.mark.asyncio
async def test_state_received_item_keeps_real_sender_for_logging():
    """ItemEvent recorded in BridgeState keeps the real sender name even
    when ItemMsg.from_ is collapsed for the self-find case — the in-app
    tracker UI and log lines rely on attribution."""
    ctx, _ = _make_ctx(my_slot=1)
    await _drive(ctx, sender_idx=1)
    evts = list(ctx.state.received_items)
    assert len(evts) == 1
    assert evts[0].sender == "Mario"
