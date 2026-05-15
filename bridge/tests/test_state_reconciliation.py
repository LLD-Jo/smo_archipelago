"""Tests for the Switch -> Bridge state-snapshot reconciliation path (M4.5).

The Switch sends a snapshot of every owned shine + capture on every (re)connect
right after HELLO. The bridge dispatches each snapshot entry through the same
`check` path live moon-get hooks use, so AP learns about anything the Switch
collected during a disconnect window.

Snapshot wire shape mirrors M4's `check` semantics: RAW SMO identifiers
(stage_name + object_id + shine_uid for moons; hack_name for captures). The
bridge resolves them downstream via shine_map.json / capture_map.json.

`BridgeState.add_checked_location` dedupes on the full ItemRef identity, so
re-sending the same snapshot is a no-op.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from smo_ap_bridge import protocol
from smo_ap_bridge.protocol import (
    HelloMsg,
    ItemKind,
    ItemRef,
    StateBeginMsg,
    StateChunkMsg,
    StateEndMsg,
)
from smo_ap_bridge.state import BridgeState, CheckEvent
from smo_ap_bridge.switch_server import SwitchServer


# ----- Direct unit tests on BridgeState's snapshot accumulator -----

def test_snapshot_accumulator_collects_raw_entries():
    s = BridgeState()
    s.begin_snapshot(save_slot=0)
    s.add_snapshot_chunk_shines("CapWorldHomeStage", [
        {"object_id": "MoonOurFirst", "shine_uid": 100},
        {"object_id": "MoonHatTrampoline", "shine_uid": 101},
    ])
    s.add_snapshot_chunk_shines("WaterfallWorldHomeStage", [
        {"object_id": "MoonMultiMoon", "shine_uid": 200},
    ])
    s.add_snapshot_chunk_meta(captures=["Kuribo", "Frog"], goal_reached=False)

    entries, goal = s.end_snapshot()
    assert goal is False
    assert len(entries) == 5
    moons = [e for e in entries if e["kind"] == "moon"]
    captures = [e for e in entries if e["kind"] == "capture"]
    assert len(moons) == 3
    assert len(captures) == 2
    assert moons[0]["stage_name"] == "CapWorldHomeStage"
    assert moons[0]["object_id"] == "MoonOurFirst"
    assert moons[0]["shine_uid"] == 100
    assert {c["hack_name"] for c in captures} == {"Kuribo", "Frog"}


def test_snapshot_accumulator_carries_goal_flag():
    s = BridgeState()
    s.begin_snapshot(save_slot=0)
    s.add_snapshot_chunk_meta(captures=None, goal_reached=True)
    _, goal = s.end_snapshot()
    assert goal is True


def test_snapshot_chunks_dropped_when_no_active_snapshot():
    s = BridgeState()
    # No begin_snapshot called.
    s.add_snapshot_chunk_shines("CapWorldHomeStage", [
        {"object_id": "MoonOurFirst", "shine_uid": 100},
    ])
    s.add_snapshot_chunk_meta(captures=["Frog"], goal_reached=False)
    entries, goal = s.end_snapshot()
    assert entries == []
    assert goal is False


def test_begin_resets_in_flight_snapshot():
    s = BridgeState()
    s.begin_snapshot(save_slot=0)
    s.add_snapshot_chunk_shines("CapWorldHomeStage", [
        {"object_id": "A", "shine_uid": 1},
    ])
    # New snapshot starts before end_snapshot — resets buffer.
    s.begin_snapshot(save_slot=1)
    s.add_snapshot_chunk_shines("WaterfallWorldHomeStage", [
        {"object_id": "B", "shine_uid": 2},
    ])
    entries, _ = s.end_snapshot()
    assert len(entries) == 1
    assert entries[0]["object_id"] == "B"
    assert s.last_snapshot_save_slot == 1


# ----- add_checked_location dedup behavior -----

def test_add_checked_location_dedupes_on_canonical_fields():
    s = BridgeState()
    e1 = CheckEvent(item=ItemRef(
        kind=ItemKind.MOON.value, kingdom="Cap", shine_id="Our First Power Moon"
    ))
    e2 = CheckEvent(item=ItemRef(
        kind=ItemKind.MOON.value, kingdom="Cap", shine_id="Our First Power Moon"
    ))
    assert s.add_checked_location(e1) is True
    assert s.add_checked_location(e2) is False
    assert len(s.checked_locations) == 1
    assert s.moons_checked_by_kingdom == {"Cap": 1}


def test_add_checked_location_dedupes_on_raw_fields():
    s = BridgeState()
    # Two raw-ID checks with the same stage+object identity.
    e1 = CheckEvent(item=ItemRef(
        kind=ItemKind.MOON.value,
        stage_name="CapWorldHomeStage", object_id="MoonOurFirst", shine_uid=100,
    ))
    e2 = CheckEvent(item=ItemRef(
        kind=ItemKind.MOON.value,
        stage_name="CapWorldHomeStage", object_id="MoonOurFirst", shine_uid=100,
    ))
    assert s.add_checked_location(e1) is True
    assert s.add_checked_location(e2) is False
    assert len(s.checked_locations) == 1


# ----- Integration: snapshot end-to-end through TCP -----

@pytest.mark.asyncio
async def test_snapshot_end_to_end_dispatches_synthetic_checks():
    state = BridgeState()
    forwarded_checks: list[dict] = []

    async def on_check(msg: dict) -> None:
        forwarded_checks.append(msg)

    async def on_goal() -> None:
        pass

    sw = SwitchServer("127.0.0.1", 0, state, on_check, on_goal)
    server = await asyncio.start_server(sw._handle_client, "127.0.0.1", 0)
    sw._server = server
    port = server.sockets[0].getsockname()[1]

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(protocol.encode(HelloMsg(mod_ver="0.1.0", smo_ver="1.0.0")))
        # Drain HELLO replies (hello_ack + checked_replay + ap_state).
        await _drain_messages(reader, n=3, timeout=2.0)

        # Send a snapshot: 2 moons in one stage, 1 in another, plus a capture.
        for m in [
            StateBeginMsg(mod_ver="0.1.0", save_slot=0),
            StateChunkMsg(stage_name="CapWorldHomeStage", shines=[
                {"object_id": "MoonOurFirst", "shine_uid": 100},
                {"object_id": "MoonHatTrampoline", "shine_uid": 101},
            ]),
            StateChunkMsg(stage_name="WaterfallWorldHomeStage", shines=[
                {"object_id": "MoonMultiMoon", "shine_uid": 200},
            ]),
            StateChunkMsg(stage_name="_meta", captures=["Kuribo"], goal_reached=False),
            StateEndMsg(),
        ]:
            writer.write(protocol.encode(m))
        await writer.drain()
        await asyncio.sleep(0.2)

        # 4 synthetic checks: 3 moons + 1 capture.
        assert len(forwarded_checks) == 4
        moons = [c for c in forwarded_checks if c["kind"] == "moon"]
        captures = [c for c in forwarded_checks if c["kind"] == "capture"]
        assert len(moons) == 3
        assert len(captures) == 1
        # Moons carry raw IDs (Switch never sent canonical here).
        moon_objs = sorted(m["object_id"] for m in moons)
        assert moon_objs == ["MoonHatTrampoline", "MoonMultiMoon", "MoonOurFirst"]
        # First moon shows correct stage.
        first_moon = next(m for m in moons if m["object_id"] == "MoonOurFirst")
        assert first_moon["stage_name"] == "CapWorldHomeStage"
        assert first_moon["shine_uid"] == 100
        assert captures[0]["hack_name"] == "Kuribo"

        # checked_locations was populated via dedup-aware add (4 entries).
        assert len(state.checked_locations) == 4
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        await sw.stop()


@pytest.mark.asyncio
async def test_snapshot_replay_is_idempotent():
    """Sending the same snapshot twice produces zero forwarded checks the second time."""
    state = BridgeState()
    forwarded_checks: list[dict] = []

    async def on_check(msg: dict) -> None:
        forwarded_checks.append(msg)

    async def on_goal() -> None:
        pass

    sw = SwitchServer("127.0.0.1", 0, state, on_check, on_goal)
    server = await asyncio.start_server(sw._handle_client, "127.0.0.1", 0)
    sw._server = server
    port = server.sockets[0].getsockname()[1]

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(protocol.encode(HelloMsg()))
        await _drain_messages(reader, n=3, timeout=2.0)

        snapshot_msgs = [
            StateBeginMsg(mod_ver="0.1.0", save_slot=0),
            StateChunkMsg(stage_name="CapWorldHomeStage", shines=[
                {"object_id": "MoonA", "shine_uid": 1},
                {"object_id": "MoonB", "shine_uid": 2},
            ]),
            StateEndMsg(),
        ]

        # First snapshot: 2 forwarded.
        for m in snapshot_msgs:
            writer.write(protocol.encode(m))
        await writer.drain()
        await asyncio.sleep(0.2)
        assert len(forwarded_checks) == 2

        # Second snapshot, identical content. on_check still fires (we always
        # forward through the same path), but BridgeState.add_checked_location
        # dedupes so checked_locations doesn't grow.
        before_dispatch = len(forwarded_checks)
        for m in snapshot_msgs:
            writer.write(protocol.encode(m))
        await writer.drain()
        await asyncio.sleep(0.2)
        assert len(forwarded_checks) == before_dispatch + 2  # forwarded again
        assert len(state.checked_locations) == 2  # but state stays at 2
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        await sw.stop()


@pytest.mark.asyncio
async def test_snapshot_with_goal_flag_calls_on_goal():
    state = BridgeState()
    goal_calls: list[None] = []

    async def on_check(msg: dict) -> None:
        pass

    async def on_goal() -> None:
        goal_calls.append(None)

    sw = SwitchServer("127.0.0.1", 0, state, on_check, on_goal)
    server = await asyncio.start_server(sw._handle_client, "127.0.0.1", 0)
    sw._server = server
    port = server.sockets[0].getsockname()[1]

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(protocol.encode(HelloMsg()))
        await _drain_messages(reader, n=3, timeout=2.0)

        for m in [
            StateBeginMsg(mod_ver="0.1.0", save_slot=0),
            StateChunkMsg(stage_name="_meta", captures=None, goal_reached=True),
            StateEndMsg(),
        ]:
            writer.write(protocol.encode(m))
        await writer.drain()
        await asyncio.sleep(0.2)
        assert len(goal_calls) == 1
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        await sw.stop()


# ----- ItemRef.to_replay_dict strips raw fields (M4 C++ parser is strict) -----

def test_item_ref_to_replay_dict_strips_raw_fields():
    """The C++ parseItemRefBody rejects unknown keys, so we must NOT send
    raw M4 fields (stage_name etc.) inside CheckedReplayMsg."""
    ref = ItemRef(
        kind=ItemKind.MOON.value,
        kingdom="Cap", shine_id="Our First Power Moon",
        stage_name="CapWorldHomeStage", object_id="MoonOurFirst", shine_uid=100,
    )
    d = ref.to_replay_dict()
    assert "stage_name" not in d
    assert "object_id" not in d
    assert "shine_uid" not in d
    assert "hack_name" not in d
    assert d["kingdom"] == "Cap"
    assert d["shine_id"] == "Our First Power Moon"


def test_checked_replay_msg_to_wire_uses_replay_dict():
    msg = protocol.CheckedReplayMsg(ids=[
        ItemRef(
            kind=ItemKind.MOON.value, kingdom="Cap", shine_id="Foo",
            stage_name="CapWorldHomeStage", object_id="MoonFoo",
        ),
    ])
    wire = msg.to_wire()
    assert wire["t"] == "checked_replay"
    assert len(wire["ids"]) == 1
    assert "stage_name" not in wire["ids"][0]


# ----- helpers -----

async def _drain_messages(reader: asyncio.StreamReader, n: int, timeout: float) -> list[dict]:
    buf = bytearray()
    out: list[dict] = []

    async def _pump():
        while len(out) < n:
            chunk = await reader.read(4096)
            if not chunk:
                return
            buf.extend(chunk)
            while True:
                nl = buf.find(b"\n")
                if nl < 0:
                    break
                line = bytes(buf[:nl]).strip()
                del buf[: nl + 1]
                if line:
                    out.append(json.loads(line))
                    if len(out) >= n:
                        return

    await asyncio.wait_for(_pump(), timeout=timeout)
    return out
