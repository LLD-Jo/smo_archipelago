// Hook on PlayerHackKeeper::startHack(al::HitSensor*, al::HitSensor*, al::LiveActor*).
//
// After Orig, the hack actor is bound and `self->getCurrentHackName()`
// returns the canonical hack name (e.g. "Goomba", "Kuribo", "Frog"). We
// forward the raw name to the bridge, which resolves it against
// capture_map.json into the apworld-canonical cap name.
//
// We resolve PlayerHackKeeper::getCurrentHackName via nn::ro::LookupSymbol
// at install time (storing the fn pointer) so we never depend on the
// link-time presence of SMO's internal symbols. M7 flips this hook into
// REPLACE-mode for cap gating.

#include "lib.hpp"
#include "lib/nx/nx.h"
#include "nn/ro.h"
#include "../ap/ApFrameBridge.hpp"
#include "../ap/ApState.hpp"
#include "../game/CaptureGate.hpp"
#include "../util/Log.hpp"
#include "HookSymbols.hpp"
#include "SoftInstall.hpp"

class PlayerHackKeeper;
namespace al { class HitSensor; class LiveActor; }

namespace smoap::hooks {

namespace {

// `const char* PlayerHackKeeper::getCurrentHackName() const`
// Mangled: _ZNK16PlayerHackKeeper18getCurrentHackNameEv
constexpr const char* kGetCurrentHackNameSym =
    "_ZNK16PlayerHackKeeper18getCurrentHackNameEv";

using GetCurrentHackNameFn = const char* (*)(const PlayerHackKeeper*);
GetCurrentHackNameFn s_getCurrentHackName = nullptr;

HOOK_DEFINE_TRAMPOLINE(CaptureStartHook) {
    static void Callback(PlayerHackKeeper* self,
                         al::HitSensor* a, al::HitSensor* b, al::LiveActor* target) {
        Orig(self, a, b, target);
        if (!s_getCurrentHackName || !self) return;
        const char* name = s_getCurrentHackName(self);
        if (name && *name) {
            SMOAP_LOG_INFO("CaptureStartHook: hack_name=%s", name);
            smoap::ap::reportCaptureChecked(name);
        }
    }
};
}  // namespace

void installCaptureStartHook() {
    SMOAP_LOG_INFO("installing CaptureStartHook -> %s", smoap::sym::kPlayerHackKeeperStartHack);
    softInstallAtSymbol<CaptureStartHook>(smoap::sym::kPlayerHackKeeperStartHack);

    // Resolve getCurrentHackName once. If lookup fails we log it; the hook
    // still installs (Orig runs as normal) and we just won't report captures.
    uintptr_t addr = 0;
    const Result rc = nn::ro::LookupSymbol(&addr, kGetCurrentHackNameSym);
    if (R_FAILED(rc)) {
        SMOAP_LOG_ERROR("getCurrentHackName lookup FAILED rc=0x%x", rc);
    } else {
        s_getCurrentHackName = reinterpret_cast<GetCurrentHackNameFn>(addr);
        SMOAP_LOG_INFO("getCurrentHackName resolved @ 0x%lx", addr);
    }
}

}  // namespace smoap::hooks
