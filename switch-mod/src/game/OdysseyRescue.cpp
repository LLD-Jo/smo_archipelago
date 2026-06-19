// See OdysseyRescue.hpp for design context.

#include "OdysseyRescue.hpp"

#include <cstring>

#include <hk/ro/RoUtil.h>

#include "../ap/ApState.hpp"
#include "../hooks/HookSymbols.hpp"
#include "../util/Log.hpp"

namespace smoap::game {

namespace {

// Match the GameDataHolderAccessor/Writer layout used by other hooks in this
// codebase (see ShineNumGetHook.cpp, AddHackDictionaryHook.cpp). Both are a
// single void* wrapper; the Itanium ABI passes them by value as a single
// pointer-sized argument in x0 on aarch64.
struct GameDataHolderAccessor { void* mData; };
struct GameDataHolderWriter   { void* mData; };

using IsCrashHomeFn               = bool        (*)(GameDataHolderAccessor);
using RepairHomeFn                = void        (*)(GameDataHolderWriter);
using UnlockWorldFn               = void        (*)(GameDataHolderWriter, int);
using GetWorldIndexFn             = int         (*)();
using GetCurrentStageNameFn       = const char* (*)(GameDataHolderAccessor);

struct ResolvedFns {
    IsCrashHomeFn               isCrashHome               = nullptr;
    RepairHomeFn                repairHome                = nullptr;
    UnlockWorldFn               unlockWorld               = nullptr;
    GetWorldIndexFn             getWorldIndexClash        = nullptr;
    GetCurrentStageNameFn       getCurrentStageName       = nullptr;
};

ResolvedFns g_fns;
bool        g_ready = false;

template <typename Fn>
bool resolveOne(Fn& slot, const char* mangled, const char* tag) {
    const ptr addr = hk::ro::lookupSymbol(mangled);
    if (addr == 0) {
        SMOAP_LOG_ERROR("OdysseyRescue: %s lookup FAILED", tag);
        slot = nullptr;
        return false;
    }
    slot = reinterpret_cast<Fn>(addr);
    SMOAP_LOG_INFO("OdysseyRescue: %s @ 0x%lx", tag,
                   static_cast<unsigned long>(addr));
    return true;
}

}  // namespace

void installOdysseyRescueSymbols() {
    bool ok = true;
    ok &= resolveOne(g_fns.isCrashHome,
        smoap::sym::kGameDataFunctionIsCrashHome, "isCrashHome");
    ok &= resolveOne(g_fns.repairHome,
        smoap::sym::kGameDataFunctionRepairHome, "repairHome");
    ok &= resolveOne(g_fns.unlockWorld,
        smoap::sym::kGameDataFunctionUnlockWorld, "unlockWorld");
    ok &= resolveOne(g_fns.getWorldIndexClash,
        smoap::sym::kGameDataFunctionGetWorldIndexClash, "getWorldIndexClash");
    ok &= resolveOne(g_fns.getCurrentStageName,
        smoap::sym::kGameDataFunctionGetCurrentStageName,
        "getCurrentStageName");
    g_ready = ok;
    SMOAP_LOG_INFO("OdysseyRescue: symbol resolution %s",
                   ok ? "COMPLETE" : "PARTIAL (sweep disabled)");
}

void runOdysseySoftlockSweep() {
    if (!g_ready) return;
    void* gdh = smoap::ap::ApState::instance().game_data_holder_cache.load(
        std::memory_order_relaxed);
    if (!gdh) return;
    GameDataHolderAccessor acc{gdh};
    GameDataHolderWriter   wr {gdh};

    // Log throttle — the branch below is a no-op on virtually every call once
    // the player leaves Lost; only state transitions are worth logging.
    // Logging every 600 calls (≈10s at the caller's ~1 call/s throttle × 60
    // frames) gives a heartbeat without spam.
    static int s_lost_log = 0;

    // --- Lost Kingdom ---
    // Wrecked Odyssey state in Lost: force repair + unlock so a player who
    // rushed in with an unswept upstream can backtrack to Wooded and collect
    // the moons that gate this kingdom. unlockWorld(getWorldIndexClash())
    // unlocks the world Mario is already in (Lost), so it doesn't perturb the
    // post-kingdom autopilot the way pre-unlocking the *next* world would.
    //
    // Ruined Kingdom is deliberately NOT handled here. Ruined grounds the
    // Odyssey via the Lord of Lightning's boss-attack state, which vanilla
    // clears the moment the player beats the dragon and collects the Ruined
    // Multi-Moon. We keep that Multi-Moon pinned to its vanilla location (the
    // dragon) in AP fill — see apworld locations.json "place_item" on
    // "Ruined: Battle with the Lord of Lightning!" — so beating the dragon
    // always repairs the Odyssey and lets the player leave. No sweep needed,
    // and crucially no risk of the counter-overshoot bug that the old Ruined
    // backtrack path triggered (post-boss autopilot skipping Bowser → Moon).
    if (g_fns.isCrashHome(acc)) {
        const char* stage = g_fns.getCurrentStageName(acc);
        if (stage && std::strcmp(stage, "ClashWorldHomeStage") == 0) {
            if ((s_lost_log++ % 600) == 0) {
                SMOAP_LOG_INFO(
                    "OdysseyRescue: Lost crashHome → repair + unlock");
            }
            g_fns.repairHome(wr);
            g_fns.unlockWorld(wr, g_fns.getWorldIndexClash());
        } else {
            // Crashed home outside Lost: a stray mid-cinematic crash — repair
            // so the player isn't stranded.
            g_fns.repairHome(wr);
        }
    }
}

}  // namespace smoap::game
