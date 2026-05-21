"""Talkatoo% sphere-safe ordering — Gap #3 (Phase 5).

Produces a per-kingdom ordered list of moon shine_ids such that as the
player collects moons in order, the next 3 entries always contain at
least one moon reachable from items earned by collecting the prior
entries + the slot's starting inventory.

Why: without this, fresh-start Talkatoo% seeds soft-lock when Talkatoo's
first 3 picks in a kingdom are all gated behind Capture/Cap items the
player hasn't received. The bridge ships the ordered list to the Switch
in slot_data["talkatoo_order"]; the Switch picks Talkatoo's bubble from
the cursor-window of 3.

Algorithm
~~~~~~~~~
Greedy with random tie-breaking. At each step, pick uniformly at random
from currently-reachable AP-pool moons in this kingdom, collect that
location's item to advance state, repeat. The resulting order is
window=1-safe (each position is reachable AT THE TIME), which trivially
implies window=3-safe (next 3 always has ≥1 reachable — itself).

Greedy beats the handoff doc's "random permutation + verify" sketch on
two axes: it's O(N²) per kingdom (vs O(retries × N²) for retry-shuffle),
and it ALWAYS finds an order when one exists (vs a retry budget that
caps out probabilistically). The randomness lives in the tie-break, so
different seeds still produce different orders.

Reachability model
~~~~~~~~~~~~~~~~~~
The validator does a per-kingdom sweep:

  1. Build a fresh CollectionState (starting inventory applied).
  2. Run `sweep_for_advancements` over all of this slot's locations
     EXCEPT the kingdom's non-progression pool. This represents
     "player has done everything else they can reach" — other kingdoms,
     captures elsewhere, plus the kingdom's own progression-flagged
     moons (Multi Moons, scenario clears, seals) which always collect
     via isProgressionShine. The result is the state the player would
     have when first interacting with Talkatoo in this kingdom.
  3. Greedy over the kingdom's pool from that swept state.

This is the right pessimism level: NOT "start from scratch" (over-
strict; Bowser's depends on earlier kingdoms' moons), NOT "fully end-
game advanced" (over-optimistic; would auto-collect this kingdom's
own non-progression moons before validating). Sphere-safe under this
model matches the player's actual experience.

The sweep is bounded to this slot's locations (`multiworld.get_locations(player)`).
Other slots' items don't enter our state — they'd need to be sent to us
via AP at runtime, and the validator can't predict that schedule.
Conservative side: real multi-world play can advance us faster.

Progression filter
~~~~~~~~~~~~~~~~~~
Excludes locations flagged `progression: true` in locations.json (Multi
Moons, scenario-advance bosses, Seaside seals, Bowser's chain). Those
bypass the Talkatoo% block via isProgressionShine on the Switch, so
they're handled outside the cursor-window mechanism — and Gap #1 already
filters them out of the bridge-side talkatoo_pool.
"""

from __future__ import annotations

import logging
import random
import re
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:  # pragma: no cover
    from BaseClasses import MultiWorld
    from . import SMOWorld

log = logging.getLogger(__name__)


# Mirror of client/datapackage.py's _LOC_PREFIX_RE. Stays decoupled
# because this module runs at generation time and shouldn't drag the
# client subpackage (which lazy-imports Kivy via its sibling gui.py)
# into the gen-host's import graph.
_LOC_PREFIX_RE = re.compile(r"^([A-Za-z' ]+):\s*(.+)$")

# Window size from the design doc. At any cursor position, the next 3
# entries must contain at least one reachable moon.
WINDOW = 3


class TalkatooOrderError(Exception):
    """Raised when the validator can't find a sphere-safe order for a
    kingdom. Surfaces in the AP generator's "InvalidWorld" output with a
    description of which kingdom over-constrained.

    Subclasses Exception (not Archipelago's OptionError or similar) so
    callers can either catch this specifically or let it propagate up
    to AP's generic generation-failure path. The message is the
    actionable bit — phrased to point at option toggles the user can
    relax."""


def _split_kingdom_prefix(name: str) -> tuple[str, str] | None:
    m = _LOC_PREFIX_RE.match(name)
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def collect_pool_per_kingdom(
    world: "SMOWorld",
    multiworld: "MultiWorld",
    player: int,
    progression_names: set[str],
) -> dict[str, list[str]]:
    """Walks this slot's filled locations and groups moon-kind entries by
    kingdom, skipping progression-flagged names and captures.

    Returns {kingdom: [full_location_name, ...]}. Captures (no `:` in
    name) and the victory location (item == "__Victory__") are dropped.
    Order within each kingdom is location-table order (deterministic);
    randomization happens in _find_safe_permutation_for_kingdom.
    """
    by_kingdom: dict[str, list[str]] = {}
    for loc in multiworld.get_locations(player):
        name = loc.name
        if name in progression_names:
            continue
        if loc.item is not None and loc.item.name == "__Victory__":
            continue
        split = _split_kingdom_prefix(name)
        if split is None:
            continue
        kingdom, _shine = split
        # "Capture: <enemy>" parses as kingdom="Capture" — drop.
        if kingdom == "Capture":
            continue
        by_kingdom.setdefault(kingdom, []).append(name)
    return by_kingdom


def is_sphere_safe_with_oracle(
    order: list[str],
    can_reach: Callable[[str], bool],
    collect: Callable[[str], None],
    *,
    window: int = WINDOW,
) -> bool:
    """Pure-data invariant check. For every prefix i, order[i:i+window]
    must contain ≥1 location for which `can_reach(loc)` is true given
    the prior `collect()` calls.

    `can_reach(loc)` answers "is loc reachable in current state?"
    `collect(loc)` advances state by collecting loc's placed item.
    Stub-friendly; exposed for unit tests. The AP-aware wrapper is
    `is_sphere_safe`.
    """
    for i in range(len(order)):
        upcoming = order[i:i + window]
        if not any(can_reach(loc) for loc in upcoming):
            return False
        collect(order[i])
    return True


def find_safe_permutation_with_oracle(
    locs: list[str],
    rng: random.Random,
    can_reach: Callable[[str], bool],
    collect: Callable[[str], None],
) -> list[str] | None:
    """Pure-data greedy permutation builder. At each step pick a
    uniformly random location from those currently reachable, collect
    its item to advance state, repeat. Returns the order, or None if
    at some step zero locations are reachable.

    Greedy beats retry-shuffle on two axes: O(N²) per kingdom (vs
    O(retries × N²)), and guaranteed to find a sphere-safe order when
    one exists (vs probabilistic retry budget). Window=1 safety here
    auto-implies window=k safety for any k ≥ 1.

    The randomness lives in the tie-break — sorting reachable first
    keeps the rng's choice deterministic for a given seed and
    independent of set iteration order.
    """
    remaining = list(locs)
    order: list[str] = []
    while remaining:
        reachable = sorted(loc for loc in remaining if can_reach(loc))
        if not reachable:
            return None
        pick = rng.choice(reachable)
        order.append(pick)
        remaining.remove(pick)
        collect(pick)
    return order


def _make_ap_oracles(multiworld: "MultiWorld", player: int,
                     exclude_pool: set[str] | None = None):
    """Build (can_reach, collect) callables backed by a CollectionState.

    State is pre-swept over this slot's locations EXCEPT names in
    `exclude_pool` — represents the player's items at the moment they
    first interact with this kingdom's Talkatoo. See the module docstring
    for why this sweep-then-greedy model is the right pessimism level.

    Imported lazily — pure tests don't need AP on sys.path.
    """
    from BaseClasses import CollectionState
    state = CollectionState(multiworld)
    if exclude_pool:
        sweep_locs = [
            loc for loc in multiworld.get_locations(player)
            if loc.name not in exclude_pool
        ]
        state.sweep_for_advancements(locations=sweep_locs)

    def can_reach(loc_name: str) -> bool:
        return state.can_reach_location(loc_name, player)

    def collect(loc_name: str) -> None:
        loc_obj = multiworld.get_location(loc_name, player)
        if loc_obj.item is not None:
            state.collect(loc_obj.item)

    return can_reach, collect


def is_sphere_safe(
    multiworld: "MultiWorld",
    player: int,
    order: list[str],
    *,
    window: int = WINDOW,
) -> bool:
    """AP-aware variant of is_sphere_safe_with_oracle. Sweeps state over
    locations outside `order` first (see module docstring)."""
    can_reach, collect = _make_ap_oracles(
        multiworld, player, exclude_pool=set(order))
    return is_sphere_safe_with_oracle(order, can_reach, collect, window=window)


def _find_safe_permutation_for_kingdom(
    multiworld: "MultiWorld",
    player: int,
    locs: list[str],
    rng: random.Random,
) -> list[str] | None:
    """AP-aware variant of find_safe_permutation_with_oracle. Sweeps
    state over locations outside `locs` first so the player's "entry to
    this kingdom" items are accounted for; see module docstring."""
    can_reach, collect = _make_ap_oracles(
        multiworld, player, exclude_pool=set(locs))
    return find_safe_permutation_with_oracle(locs, rng, can_reach, collect)


def _shine_id_for(name: str) -> str:
    """Strip the 'Kingdom: ' prefix to get the bridge-side shine_id."""
    split = _split_kingdom_prefix(name)
    assert split is not None, f"unreachable: pool entry without prefix: {name!r}"
    return split[1]


def build_talkatoo_order(
    world: "SMOWorld",
    multiworld: "MultiWorld",
    player: int,
    progression_names: set[str],
) -> dict[str, list[str]]:
    """Top-level entry: returns {kingdom: [shine_id, ...]} sphere-safe.

    Raises TalkatooOrderError when some kingdom's pool can't be ordered
    sphere-safely on this slot's option set (typically: a kingdom whose
    only-reachable moons are pinned behind a Capture/Cap item the slot
    has neither in starting inventory nor at any of its own locations
    that could be collected first).

    Single-kingdom failure aborts the whole build — the per-kingdom
    description in the error narrows the diagnosis.
    """
    pool_per_kingdom = collect_pool_per_kingdom(
        world, multiworld, player, progression_names)
    rng = random.Random(world.random.getrandbits(64))

    result: dict[str, list[str]] = {}
    for kingdom in sorted(pool_per_kingdom):
        locs = pool_per_kingdom[kingdom]
        if not locs:
            continue
        order = _find_safe_permutation_for_kingdom(
            multiworld, player, locs, rng)
        if order is None:
            raise TalkatooOrderError(
                f"talkatoo_mode: kingdom {kingdom!r} has no sphere-safe "
                f"ordering for its {len(locs)} AP-pool moons (window={WINDOW}). "
                "This means none of the moons here are reachable from the "
                "slot's starting inventory — typically because captures or "
                "cap items the kingdom depends on were excluded by option "
                "toggles. Enable more captures (capturesanity: true), allow "
                "more peace moon toggles, or relax the kingdom's "
                "annoying-cluster filters."
            )
        result[kingdom] = [_shine_id_for(loc) for loc in order]
        log.info("[talkatoo-order] kingdom=%s ordered %d moons", kingdom, len(order))
    return result
