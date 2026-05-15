"""Tests for the DeathLink wiring in SmoApBridgeContext.

We don't have the Archipelago checkout in CI, so these tests avoid calling
`SmoApBridgeContext.start()` (which imports CommonClient). Instead they
construct the context, plug a stub `_ctx` with the bits we care about, and
exercise `report_death` and `_handle_ap_package` directly.
"""

from __future__ import annotations

import pytest

from smo_ap_bridge.ap_client import SmoApBridgeContext
from smo_ap_bridge.datapackage import DataPackage
from smo_ap_bridge.protocol import KillMsg
from smo_ap_bridge.state import BridgeState


class _StubCtx:
    """Minimum surface area of CommonContext that our report_death uses."""
    def __init__(self, slot: str):
        self.auth = slot
        self.locations_checked: set = set()
        self.player_names: dict = {}
        self.sent: list = []

    async def send_msgs(self, msgs: list) -> None:
        self.sent.extend(msgs)


def _make_ctx(*, deathlink: bool, slot: str = "Mario") -> tuple[SmoApBridgeContext, BridgeState, list]:
    state = BridgeState()
    kill_buffer: list = []

    async def stub_send_item(_): ...
    async def stub_send_print(_): ...
    async def stub_send_ap_state(_): ...
    async def stub_send_kill(k: KillMsg):
        kill_buffer.append(k)

    ctx = SmoApBridgeContext(
        server_addr="localhost:0",
        slot=slot,
        password="",
        items_handling=0,
        switch_send_item=stub_send_item,
        switch_send_print=stub_send_print,
        switch_send_ap_state=stub_send_ap_state,
        switch_send_kill=stub_send_kill,
        state=state,
        datapackage=DataPackage(),
        deathlink_enabled=deathlink,
    )
    ctx._ctx = _StubCtx(slot)
    return ctx, state, kill_buffer


@pytest.mark.asyncio
async def test_report_death_disabled_only_bumps_state():
    ctx, state, _ = _make_ctx(deathlink=False)
    await ctx.report_death(ts_ms=1234)
    assert state.death_count == 1
    assert ctx._ctx.sent == []


@pytest.mark.asyncio
async def test_report_death_enabled_sends_bounce():
    ctx, state, _ = _make_ctx(deathlink=True)
    await ctx.report_death(ts_ms=42_000)
    assert state.death_count == 1
    assert len(ctx._ctx.sent) == 1
    pkt = ctx._ctx.sent[0]
    assert pkt["cmd"] == "Bounce"
    assert "DeathLink" in pkt["tags"]
    assert pkt["data"]["source"] == "Mario"
    assert pkt["data"]["time"] == pytest.approx(42.0)


@pytest.mark.asyncio
async def test_inbound_bounce_forwards_kill():
    ctx, _, kill_buffer = _make_ctx(deathlink=True)
    await ctx._handle_ap_package(
        cmd="Bounce",
        args={"tags": ["DeathLink"],
              "data": {"source": "OtherSlot", "cause": "Fell off the world"}},
        ctx=ctx._ctx,
    )
    assert len(kill_buffer) == 1
    assert kill_buffer[0].source == "OtherSlot"
    assert kill_buffer[0].cause == "Fell off the world"


@pytest.mark.asyncio
async def test_inbound_bounce_own_source_is_swallowed():
    ctx, _, kill_buffer = _make_ctx(deathlink=True, slot="Mario")
    await ctx._handle_ap_package(
        cmd="Bounce",
        args={"tags": ["DeathLink"], "data": {"source": "Mario"}},
        ctx=ctx._ctx,
    )
    assert kill_buffer == []  # don't echo our own death


@pytest.mark.asyncio
async def test_inbound_bounce_ignored_when_deathlink_off():
    ctx, _, kill_buffer = _make_ctx(deathlink=False)
    await ctx._handle_ap_package(
        cmd="Bounce",
        args={"tags": ["DeathLink"], "data": {"source": "OtherSlot"}},
        ctx=ctx._ctx,
    )
    assert kill_buffer == []
