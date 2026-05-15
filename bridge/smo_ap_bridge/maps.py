"""Bridge-side resolution of raw SMO identifiers to apworld-canonical names.

The Switch sends raw identifiers it can read off SMO's own structs:
  - moons:    {stage_name, object_id, shine_uid}
  - captures: {hack_name}

The bridge translates those into the names the AP DataPackage uses:
  - moons    -> (kingdom, shine_id)  e.g. ("Cap", "Our First Power Moon")
  - captures -> cap                  e.g. "Goomba"

The lookup tables live as JSON files alongside this module under data/ so they
can be hand-edited without rebuilding the Switch module. Unknown raw IDs are
logged loudly so the user knows what to add.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MoonResolution:
    kingdom: str
    shine_id: str


class ShineMap:
    """Resolve (stage_name, object_id) -> (kingdom, shine_id).

    JSON schema (a list of objects):
      [
        {"stage_name":"CapWorldHomeStage", "object_id":"MoonOurFirst",
         "kingdom":"Cap", "shine_id":"Our First Power Moon"}
      ]

    Lookup key is (stage_name, object_id). shine_uid is accepted for future
    fallback lookups but not part of the primary key today.
    """

    def __init__(self, path: Path | None = None):
        self._by_pair: dict[tuple[str, str], MoonResolution] = {}
        self._by_uid: dict[int, MoonResolution] = {}
        self._source = path
        if path is not None and path.exists():
            self.load(path)

    def load(self, path: Path) -> None:
        entries = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError(f"{path}: expected a JSON list")
        for e in entries:
            stage = e.get("stage_name")
            obj = e.get("object_id")
            kingdom = e.get("kingdom")
            shine = e.get("shine_id")
            if not (stage and obj and kingdom and shine):
                continue
            res = MoonResolution(kingdom=kingdom, shine_id=shine)
            self._by_pair[(stage, obj)] = res
            uid = e.get("shine_uid")
            if isinstance(uid, int):
                self._by_uid[uid] = res
        log.info("ShineMap loaded %d entries from %s", len(self._by_pair), path)

    def resolve(
        self,
        stage_name: str | None,
        object_id: str | None,
        shine_uid: int | None = None,
    ) -> MoonResolution | None:
        if stage_name and object_id:
            res = self._by_pair.get((stage_name, object_id))
            if res is not None:
                return res
        if isinstance(shine_uid, int) and shine_uid >= 0:
            res = self._by_uid.get(shine_uid)
            if res is not None:
                return res
        return None


class CaptureMap:
    """Resolve raw hack_name -> apworld-canonical cap name.

    Default pass-through: if a hack_name isn't in the table we return it
    unchanged (most match 1:1 between SMO internals and apworld items.json).

    JSON schema (a list of objects):
      [
        {"hack_name":"Kuribo", "cap":"Goomba"}
      ]
    """

    def __init__(self, path: Path | None = None):
        self._table: dict[str, str] = {}
        self._source = path
        if path is not None and path.exists():
            self.load(path)

    def load(self, path: Path) -> None:
        entries = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError(f"{path}: expected a JSON list")
        for e in entries:
            hack = e.get("hack_name")
            cap = e.get("cap")
            if hack and cap:
                self._table[hack] = cap
        log.info("CaptureMap loaded %d entries from %s", len(self._table), path)

    def resolve(self, hack_name: str | None) -> str | None:
        if not hack_name:
            return None
        return self._table.get(hack_name, hack_name)
