# HAKKUN.md — exlaunch → Hakkun migration runbook

This is the operational runbook for migrating `switch-mod/` off exlaunch + lunakit-vendor and onto LibHakkun + OdysseyHeaders + sail. It is the successor to the de-risking spike plan at `C:/Users/maxwe/.claude/plans/hakkun-is-the-successor-drifting-wall.md` (which proved the migration is tractable) and the higher-level migration plan at `C:/Users/maxwe/.claude/plans/hakkun-cutover-the-old-tenant-packs-out.md` (which laid out the phasing and decisions).

This doc is **execution-oriented**: each phase has concrete commands, exact file paths, and a deliverable that gates the next phase.

## Locked-in decisions (2026-05-20)

1. **Worktree-isolated.** Migration lives on branch `claude/hakkun-cutover` in worktree `.claude/worktrees/hakkun-migration/`. `main` stays shippable; the worktree merges in one PR when phase 6 passes.
2. **Stay on subsdk9 at cutover.** During phases 1–5 the new build emits **subsdk8** (so it can coexist with the production subsdk9 mod in Ryujinx + on SD); phase 6 flips `MODULE_BINARY` from `subsdk8` to `subsdk9` as part of the rename + replace.
3. **LibHakkun Windows-port patches: upstream-first, fork fallback.** Submodule pins upstream `github.com/fruityloops1/LibHakkun`. Patches are applied locally via `scripts/patch_hakkun.py` while upstream PRs are in flight. If a PR review stalls > 1 week, fork to `github.com/mdietz94/LibHakkun-smo` and re-pin.
4. **SMO 1.0.0 only at cutover.** Sail supports `@smo:100,101,110,120,130` in one binary, but offsets for 1.0.1+ are unresearched. Multi-version is a follow-up PR.
5. **Functional parity is the cutover gate.** Phase 5 must show: the loopback test passes against the new subsdk; a Ryujinx manual play session collects 5 moons via AP location checks and applies an AP item to the running game; the same passes on real Switch FW22. Strict log-byte-equivalence is NOT required.

## Spike artifacts you'll reuse

These already exist (gitignored under `third_party/`) and are the templates for phase 0–2:

- [third_party/hakkun-spike/](third_party/hakkun-spike/) — pinned LibHakkun snapshot we built against.
- [third_party/hakkun-example/](third_party/hakkun-example/) — full working SMO 1.0.0 Hakkun mod (subsdk4 = moonjump + HUD).
- [third_party/hakkun-example/build_winpath.py](third_party/hakkun-example/build_winpath.py) — Windows PATH-fixing CMake wrapper.
- [third_party/hakkun-example/setup_sail_winpath.py](third_party/hakkun-example/setup_sail_winpath.py) — sail host-compile wrapper.
- [third_party/hakkun-example/fix_symlinks.py](third_party/hakkun-example/fix_symlinks.py) — Git-on-Windows symlink-to-junction converter for OdysseyHeaders.
- [third_party/hakkun-example/syms/game/SmoApSymbols.sym](third_party/hakkun-example/syms/game/SmoApSymbols.sym) — all 37 mangled symbols from `HookSymbols.hpp` (verified by llvm-nm in Gate 6).
- [third_party/hakkun-example/config/npdm.json](third_party/hakkun-example/config/npdm.json) — NPDM template that works for SMO + bsd:u.
- [third_party/hakkun-example/config/VersionList.sym](third_party/hakkun-example/config/VersionList.sym) — SMO 1.0.0 build ID = `3ca12dfaaf9c82da064d1698df79cda1`.

The 10 Windows-port patches discovered during the spike (re-applied via `scripts/patch_hakkun.py` in phase 0):

1. `winget install LLVM.LLVM --version 19.1.7` (must be on PATH or invoked via wrapper).
2. `pip install --user pyelftools mmh3 lz4` (README typo says "mmh"; actual import is `mmh3`).
3. `git submodule update --init --recursive` is mandatory after submodule add.
4. In `lib/OdysseyHeaders/`, ten `include/` symlinks land as text-files on Git-for-Windows; convert each to a directory junction.
5. In `sys/sail/CMakeLists.txt`, delete the `set(CMAKE_C_COMPILER clang)` / `set(CMAKE_CXX_COMPILER clang++)` lines — they fight CMake's compiler detection. Use mingw64 g++ as host compiler instead.
6. In `sys/sail/src/main.cpp:36`, `entry.path().c_str()` returns `wchar_t*` on MSVC/MinGW. Use `entry.path().string().c_str()`.
7. In `sys/sail/src/fakelib.cpp:13`, quote `clangBinary` in the `popen` cmdline (Windows path may contain spaces, `cmd.exe` splits on unquoted spaces).
8. In `sys/cmake/sail.cmake:42`, the literal `sys/addons/*/syms` is passed verbatim to sail; expand the glob with `file(GLOB ADDONS_SYM_DIRS ...)` first.
9. In `sys/cmake/generate_exefs.cmake:16,21`, prefix `python ${PROJECT_SOURCE_DIR}/sys/tools/elf2nso.py` (Windows doesn't always have `.py` as executable).
10. Copy `sys/sail/build/sail.exe` → `sys/sail/build/sail` (no-extension); `sail.cmake` checks for the no-extension path before invoking `setup_sail.py`.

Patches 5–10 are local source edits; `scripts/patch_hakkun.py` applies them. Patches 1–4 are environment setup; the build wrapper handles them.

## Phase 0 — Worktree + submodules + Windows-port wrappers  *(0.5 day)*

**Goal:** Migration worktree is ready, LibHakkun + OdysseyHeaders are submoduled, Windows-port patches script exists, build wrappers exist.

### Commands

```pwsh
# 0.1 Create the migration worktree off main.
cd C:\Users\maxwe\Documents\smo_archipelago
git worktree add .claude\worktrees\hakkun-migration -b claude/hakkun-cutover main

# 0.2 Add submodules. Pin commit hashes the spike validated against.
cd .claude\worktrees\hakkun-migration
git submodule add https://github.com/fruityloops1/LibHakkun.git switch-mod\hakkun
git submodule add https://github.com/MonsterDruide1/OdysseyHeaders.git switch-mod\odyssey-headers
git submodule update --init --recursive switch-mod\hakkun switch-mod\odyssey-headers

# 0.3 Pin the OdysseyHeaders nested submodule for NintendoSDK (the example used it).
# OdysseyHeaders has a NintendoSDK submodule that needs init'ing.
git submodule update --init --recursive switch-mod\odyssey-headers

# 0.4 Apply Windows-port patches.
python scripts\patch_hakkun.py

# 0.5 Validate: build a Hello-World subsdk that does nothing.
python scripts\build_switchmod_hk.py
# Expected: switch-mod-hk\build\sd\atmosphere\contents\0100000000010000\exefs\subsdk8 produced.
```

### Files to add in phase 0

| Path | Source | Purpose |
|---|---|---|
| `scripts/patch_hakkun.py` | New | Re-applies patches 5–10 to `switch-mod/hakkun/` after submodule init. Idempotent. |
| `scripts/build_switchmod_hk.py` | Port of [third_party/hakkun-example/build_winpath.py](third_party/hakkun-example/build_winpath.py) | One-call build: ensures LLVM + Ninja + CMake on PATH, runs cmake config + build, post-processes outputs. |
| `scripts/setup_sail_winpath.py` | Port of [third_party/hakkun-example/setup_sail_winpath.py](third_party/hakkun-example/setup_sail_winpath.py) | One-time sail host-binary compile (mingw64 g++). |
| `scripts/fix_hakkun_symlinks.py` | Port of [third_party/hakkun-example/fix_symlinks.py](third_party/hakkun-example/fix_symlinks.py) | Convert OdysseyHeaders text-symlinks to directory junctions. |

### Done when

- `git submodule status` shows `switch-mod/hakkun` and `switch-mod/odyssey-headers` pinned.
- `python scripts/patch_hakkun.py` reports all 6 patches applied or already applied.
- The 3 wrapper scripts are in `scripts/`.

## Phase 1 — Skeleton build  *(0.5 day)*

**Goal:** A `switch-mod-hk/` tree builds a no-op subsdk8 .nso that loads in Ryujinx without crashing SMO. Proves the toolchain end-to-end.

### Commands

```pwsh
# 1.1 Initialize switch-mod-hk/ from the spike template.
# (Files listed below; create them one at a time.)

# 1.2 Build.
python scripts\build_switchmod_hk.py
# Expected output: switch-mod-hk\build\sd\atmosphere\contents\0100000000010000\exefs\subsdk8

# 1.3 Deploy to Ryujinx alongside production subsdk9 (different mod folder).
$dst = "$env:APPDATA\Ryujinx\mods\contents\0100000000010000\smo-archipelago-hk\exefs"
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item -Force switch-mod-hk\build\sd\atmosphere\contents\0100000000010000\exefs\subsdk8 $dst\subsdk8

# 1.4 Boot SMO in Ryujinx. Expect: clean boot, title screen, normal gameplay.
#     Both subsdks load (production subsdk9 in smo-archipelago, new subsdk8 in smo-archipelago-hk).
#     The new subsdk8 does nothing — hkMain is empty.
```

### Files to add in phase 1

| Path | Content |
|---|---|
| `switch-mod-hk/CMakeLists.txt` | Adapted from [hakkun-example CMakeLists.txt](third_party/hakkun-example/CMakeLists.txt). `PROJECT_NAME` = `smo_archipelago_hk`. Includes `src/*.cpp`. |
| `switch-mod-hk/config/config.cmake` | `TITLE_ID 0x0100000000010000`, `MODULE_NAME smo_archipelago_hk`, `MODULE_BINARY subsdk8` (NB: subsdk8 during phases 1–5; flipped to subsdk9 at phase 6 cutover). `HAKKUN_ADDONS HeapSourceDynamic` only (no Nvn/DebugRenderer in production; those were spike-only). `USE_SAIL TRUE`. |
| `switch-mod-hk/config/npdm.json` | Copy from [hakkun-example npdm.json](third_party/hakkun-example/config/npdm.json) verbatim. |
| `switch-mod-hk/config/VersionList.sym` | `@smo = main` + `100 = 3ca12dfaaf9c82da064d1698df79cda1`. |
| `switch-mod-hk/syms/.gitkeep` | Placeholder; phase 2 populates. |
| `switch-mod-hk/src/main.cpp` | `extern "C" void hkMain() {}` — empty until phase 4. |

### Done when

- Build succeeds; `subsdk8` artifact is ~10–20 KiB.
- Ryujinx boots SMO with the new subsdk8 in `mods/contents/0100000000010000/smo-archipelago-hk/exefs/subsdk8` and the existing production subsdk9 unchanged in `mods/contents/0100000000010000/smo-archipelago/exefs/subsdk9`. No `[rtld]` errors in the Ryujinx log.

## Phase 2 — Sail symbol DB  *(1 day)*

**Goal:** All 37 mangled symbols from [switch-mod/src/hooks/HookSymbols.hpp](switch-mod/src/hooks/HookSymbols.hpp) are in sail `.sym` files. `llvm-nm --dynamic` confirms all 37 appear in `fakesymbols.so`.

### Commands

```pwsh
# 2.1 Copy the spike's sail file verbatim — already proven in Gate 6.
Copy-Item third_party\hakkun-example\syms\game\SmoApSymbols.sym `
    switch-mod-hk\syms\game\SmoApSymbols.sym

# 2.2 Rebuild.
python scripts\build_switchmod_hk.py

# 2.3 Validate.
& "C:\Program Files\LLVM\bin\llvm-nm.exe" --dynamic `
    switch-mod-hk\build\fakesymbols.so | Select-String "_Z" | Measure-Object -Line
# Expected: at least 37 lines (the 37 SMO symbols + any sail-self symbols).
```

### Done when

- llvm-nm shows all 37 names from `SmoApSymbols.sym` in `fakesymbols.so`.
- Build is still clean (no link errors from `main.cpp` referencing missing symbols — there's nothing to reference yet).

## Phase 3 — AP subsystem port  *(1 day)*

**Goal:** `switch-mod/src/ap/` (5 .cpp + 5 .hpp files) is rewritten in `switch-mod-hk/src/ap/` using `hk::socket::Socket` for sockets, `hk::os::Thread` for the worker, `hk::os::Mutex` where threading mutexes are needed. Bridge connects in Ryujinx loopback.

### Per-file mapping

| Old file (`switch-mod/src/ap/`) | New file (`switch-mod-hk/src/ap/`) | Key changes |
|---|---|---|
| `ApClient.cpp` (~600 lines) | `ApClient.cpp` | `nn::socket::Initialize/Socket/Connect/Send/Recv/Close` → `hk::socket::Socket::initialize<"bsd:u">`, `.socket()`, `.connect()`, `.send()`, `.recv()`, `.close()`. Drop the manual sockaddr workaround (use `hk::socket::SocketAddrIpv4::parse(host, port)`). Worker thread: replace `nn::os::CreateThread` with `hk::os::Thread`. Drop `FlatHashSet` usage → `std::set<u32> locations_checked`. Drop atomic-published `pending_moon_label` → `std::string` directly. |
| `ApConfig.cpp` | `ApConfig.cpp` | No changes — still compile-time `-DBRIDGE_HOST=...`. |
| `ApFrameBridge.cpp` | `ApFrameBridge.cpp` | No changes — callbacks just get re-bound to new HkTrampoline hooks in phase 4. |
| `ApProtocol.cpp` | `ApProtocol.cpp` | No changes — wire format is byte-equivalent contract. |
| `ApState.cpp` | `ApState.cpp` | Use `std::set` / `std::vector` / `std::string` freely (Gate 4 cleared this). Retire the `FlatHashSet<256>` workaround. |

### Files to remove (deferred until phase 6, but listed here for the audit trail)

- `switch-mod/src/util/FlatHashSet.hpp` — obsolete.
- M6.1 hardening in `switch-mod/src/util/Log.cpp` (the `snprintf`-to-stack-char-array pattern) — obsolete; can use `std::string` on worker thread.

### Commands

```pwsh
# 3.1 Port each file by hand. Pattern:
#   - Replace #include "lib.hpp" with #include "hk/socket/service.h", "hk/os/Thread.h", etc.
#   - Replace nn::socket::*  → hk::socket::Socket::instance()->*
#   - Replace nn::os::CreateThread → hk::os::Thread ctor + .start()
#   - Replace FlatHashSet<N>     → std::set<u32>
#   - Replace atomic-string game → std::string

# 3.2 Build.
python scripts\build_switchmod_hk.py

# 3.3 Deploy.
$dst = "$env:APPDATA\Ryujinx\mods\contents\0100000000010000\smo-archipelago-hk\exefs"
Copy-Item -Force switch-mod-hk\build\sd\atmosphere\contents\0100000000010000\exefs\subsdk8 $dst\subsdk8

# 3.4 Run loopback test (the smo-loopback-test skill is the canonical flow).
#     Probe: subsdk8 connects to the loopback bridge, exchanges HELLO, the bridge sees
#     the connect from the new mod even though there are no hooks yet.
```

### Risk to probe in phase 3

`nn::socket::Initialize` is called by SMO itself; the spike used `hk::socket::Socket::initialize<"bsd:u">` alongside SMO's bsd:u use without conflict (separate SM session, separate IPC channel). If a probe shows interference (SMO loses network, e.g.), mirror lunakit's pattern: replace-hook SMO's `nn::socket::Initialize` to no-op, then open our own pool. Not expected, but worth a probe.

### Done when

- `switch-mod-hk/src/ap/` has 5 .cpp + 5 .hpp files matching the old structure.
- The new subsdk8 connects to the loopback bridge (visible in the bridge's log: a connection from our new client).
- No `[rtld]` errors at boot.

## Phase 4 — Hook ports  *(2 days)*

**Goal:** All 14 hook files in `switch-mod/src/hooks/` are rewritten in `switch-mod-hk/src/hooks/`. 26 trampoline hooks become `HkTrampoline<...>` + `installAtSym<...>()`. The 1 inline-at-offset hook (`CreditsStartHook`) is refactored to a trampoline on the enclosing `StaffRollScene::init` (Strategy B per spike Gate 3).

### Hook-by-hook checklist

Estimate: 5–10 min mechanical per trampoline (proven in Gate 5); ~30 min for `CreditsStartHook` (Strategy B refactor).

| File | Old macro × count | New form |
|---|---|---|
| `AddHackDictionaryHook.cpp` | TRAMPOLINE × 1 | `HkTrampoline<...> g_xxx` + lambda + `.installAtSym<"...">()` in `hkMain` |
| `AddPayShineHook.cpp` | TRAMPOLINE × 2 | same |
| `CappyMessageHook.cpp` | TRAMPOLINE × 4 | same |
| `CaptureStartHook.cpp` | TRAMPOLINE × 1 | same |
| **`CreditsStartHook.cpp`** | **INLINE @ 0x4C54A4** | **Strategy B: HkTrampoline on `StaffRollScene::init`.** Symbol candidate: `_ZN15StaffRollScene4initERKN2al13ActorInitInfoE`. Verify against main.nso before commit. If false-positive (credits-from-menu), add a guard or fall back to Strategy A (naked-trampoline @ 0x4C54A4 via `writeBranchLinkAtMainOffset`). |
| `DeathHook.cpp` | TRAMPOLINE × 1 | mechanical |
| `MoonGetHook.cpp` | TRAMPOLINE × 2 | mechanical — [spike_gate5.cpp](third_party/hakkun-example/src/spike_gate5.cpp) is the canonical template |
| `MoonLabelHook.cpp` | TRAMPOLINE × 4 | mechanical |
| `SaveLoadHook.cpp` | TRAMPOLINE × 1 | mechanical |
| `ScenarioFlagHook.cpp` | TRAMPOLINE × 1 | mechanical |
| `ShineAppearanceHook.cpp` | TRAMPOLINE × 1 | mechanical (already trampoline on `Shine::init`, not inline) |
| `ShineNumByWorldGetHook.cpp` | TRAMPOLINE × 1 | mechanical |
| `ShineNumGetHook.cpp` | TRAMPOLINE × 2 | mechanical |
| `WorldMapSelectHook.cpp` | TRAMPOLINE × 5 | mechanical |

### Files to remove (deferred until phase 6)

- `switch-mod/src/hooks/HookSymbols.hpp` — sail .sym replaces it.
- `switch-mod/src/hooks/SoftInstall.hpp` — `installAtSym<"...">()` IS the soft install equivalent.

### Done when

- All 14 hook files exist in `switch-mod-hk/src/hooks/`.
- All hooks install in `hkMain` via `xxxHook.installAtSym<"...">()` calls.
- Build is clean, sail resolves every symbol referenced.

## Phase 5 — End-to-end validation  *(1 day)*

**Goal:** Functional parity with production. Three gates, sequential.

### 5.1 Ryujinx loopback test  *(~30 min)*

```pwsh
# Use the smo-loopback-test skill canonical flow.
# Probe: bridge sees HELLO, scout pre-warm runs, fake moon collections route through,
# capture-lock-deny rejection fires. Same observed wire-protocol output as production.
```

### 5.2 Ryujinx manual play  *(~1 hour)*

```pwsh
# Boot Ryujinx, run apworld AP server, connect SMOClient.
# Collect ≥5 moons in Cap Kingdom; verify each appears as an AP location check on the server.
# Receive an AP item (most easily: a Moon); verify it applies to the running game.
# Verify capture-lock denies a Frog capture if the AP Frog item hasn't been received.
# Verify CreditsStartHook fires on real game-end (not on credits-from-menu).
```

### 5.3 Real-Switch FW22  *(~1 hour)*

```pwsh
# Deploy: copy subsdk8 (still subsdk8, not yet subsdk9) to SD card alongside production subsdk9.
# Copy switch-mod-hk\build\sd\atmosphere\contents\0100000000010000\exefs\subsdk8
#  to D:\atmosphere\contents\0100000000010000\exefs\subsdk8  (confirm SD drive letter first)
# Boot SMO on real Switch. Same play sequence as 5.2.
```

### Done when

All three gates pass. If 5.3 reveals a divergence Ryujinx didn't show: stop, diagnose, fix, re-validate.

## Phase 6 — Cutover  *(0.5 day)*

**Goal:** `switch-mod-hk/` becomes `switch-mod/`. `subsdk8` flips to `subsdk9`. CI, skills, and docs are updated. exlaunch + lunakit-vendor submodules are gone.

### Commands

```pwsh
# 6.1 In the migration worktree:
cd .claude\worktrees\hakkun-migration

# 6.2 Move the old switch-mod aside, then rename the new one into place.
git mv switch-mod switch-mod-old
git mv switch-mod-hk switch-mod

# 6.3 Flip MODULE_BINARY from subsdk8 to subsdk9 in switch-mod\config\config.cmake.
# Edit by hand or via sed-equivalent.

# 6.4 Remove the old switch-mod submodules.
git submodule deinit switch-mod-old\lunakit-vendor
git submodule deinit switch-mod-old\exlaunch
git rm -rf switch-mod-old

# 6.5 Rebuild to confirm the rename + subsdk9 flip works.
python scripts\build_switchmod_hk.py
# Expected output: switch-mod\build\sd\atmosphere\contents\0100000000010000\exefs\subsdk9
```

### Files to update outside switch-mod/

| Path | Change |
|---|---|
| `.github/workflows/release.yml` | Build step now calls `python scripts/build_switchmod_hk.py`. Output path `switch-mod/build/...` for the .nso. Drop devkitPro / lunakit setup steps; add LLVM 19 install + LibHakkun submodule init. |
| `.github/workflows/test.yml` | If `smo-host-tests` C++ tests reference lunakit headers, update to LibHakkun equivalents. |
| `.claude/skills/smo-build/SKILL.md` | Full rewrite. Toolchain (LLVM 19, prepackaged libc++ via Hakkun setup), build command (`scripts/build_switchmod_hk.py`), deploy path (still subsdk9 in Ryujinx mods folder). |
| `.claude/skills/smo-symbol-discovery/SKILL.md` | Sail-based now: add to `.sym` file → build → verify by `llvm-nm --dynamic fakesymbols.so`. `check_nso_symbols.py` retired. |
| `.claude/skills/smo-host-tests/SKILL.md` | Minor — LibHakkun headers replace lunakit. |
| `.claude/skills/smo-loopback-test/SKILL.md` | No change (bridge-side, implementation-agnostic). |
| `.claude/skills/smo-extract-data/SKILL.md` | No change. |
| `.claude/skills/smo-poptracker/SKILL.md` | No change. |
| `CLAUDE.md` | Architecture section, Decisions table, Repository layout. Annotate M6.1 in Pattern Invariants: "*was* an issue under exlaunch; Hakkun retired it 2026-05-20." |
| `docs/architecture.md` | Switch-side stack swap. |
| `docs/build-windows.md` | LLVM 19 + mingw64 + prepackaged libc++. |
| `docs/install-switch.md` | subsdk filename unchanged (still subsdk9). |
| `docs/milestones.md` | Append M9 entry: "exlaunch → Hakkun migration, 2026-05-DD." |
| `docs/release-process.md` | Build command in the release flow. |
| `scripts/check_nso_symbols.py` | DELETE. |

### Memory annotations

| Memory | Annotation |
|---|---|
| [project_subsdk9_no_thread_local.md](memory/project_subsdk9_no_thread_local.md) | Add: "This was an exlaunch-era pattern. Retired post-Hakkun migration 2026-05-DD — Hakkun's musl + LLVM libc++ + HeapSourceDynamic does NOT have this restriction." |
| [project_nintendo_sockaddr_layout.md](memory/project_nintendo_sockaddr_layout.md) | Add: "Retired post-Hakkun migration. `hk::socket::SocketAddrIpv4` encapsulates the layout; manual sockaddr construction no longer happens in our code." |

### Done when

- `git submodule status | grep -E "lunakit|exlaunch"` returns nothing.
- `grep -r "exlaunch\|lunakit" switch-mod/src` returns nothing.
- CI workflow runs green on a push to the migration branch.
- The smo-loopback-test passes against the new subsdk9.
- A real-Switch FW22 manual play session collects ≥ 5 moons via AP location checks.
- CLAUDE.md no longer mentions exlaunch or lunakit-vendor as current dependencies (historical references in `docs/milestones.md` are fine).
- The two memories above are annotated.

## Phase 7 — Optional polish  *(deferred PR)*

Not in scope for the cutover. Tracked here for the follow-up:

- **Multi-version SMO support** — add `@smo:101,110,120,130` blocks to `VersionList.sym` and per-version `.sym` blocks for the 37 symbols.
- **In-game tracker overlay (M8 deferred)** — `hk::gfx::DebugRenderer` via the Hakkun addon.
- **Drop legacy `Log.cpp` workarounds** — `std::string` + `std::format` on the worker thread.

## Rollback

If phase 5 reveals a > 1-day blocker:
1. Don't merge. The migration branch stays a branch; main is unchanged.
2. File the symptom (creport, log, HUD state) for follow-up.
3. Either fix on the migration branch, or shelve. Shelving costs nothing — spike artifacts + this runbook stay in the repo.

## Glossary

- **Sail** — LibHakkun's symbol DB / resolver. Reads `.sym` files at build time, emits `symboldb.o` + `fakesymbols.so` + `datablocks.o` into the build dir, links them into the .nso. At module load, looks up each symbol against the main module's dynsym and patches in the address.
- **HeapSourceDynamic** — LibHakkun addon that re-exports `operator new` / `malloc` / `free` from the host process (SMO) to subsdk code. This is what makes worker-thread `std::vector::push_back` safe (Gate 4).
- **HkTrampoline** — LibHakkun's trampoline-hook primitive. File-scope `HkTrampoline<Ret, Args...>` variable + lambda body that calls `hook.orig(args)` for the original behavior, installed via `installAtSym<"mangled_name">()`.
- **subsdk8 vs subsdk9** — Atmosphère exefs slot. Phases 1–5 use subsdk8 (avoids collision with production subsdk9). Phase 6 flips to subsdk9.
- **fakesymbols.so** — Sail-generated synthetic library. Each .sym entry becomes a stub. The link uses the stubs; at runtime hk::ro resolves real addresses.
