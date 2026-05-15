// Hook on PlayerHitPointData::kill().
//
// Mario's HP transitions to 0 here regardless of cause (fall, drown, poison,
// damage, abyss). M4 ships outbound only — reportDeath enqueues a death
// event for the bridge, which (when DeathLink is enabled in config) forwards
// it to AP as a `Bounce {tags:["DeathLink"]}`. Receiving DeathLink bounces
// and actually killing Mario from the outside lands in M6 where we also
// have the player-state-write machinery.

#include "lib.hpp"
#include "../ap/ApFrameBridge.hpp"
#include "../util/Log.hpp"
#include "HookSymbols.hpp"
#include "SoftInstall.hpp"

class PlayerHitPointData;

namespace smoap::hooks {

namespace {
HOOK_DEFINE_TRAMPOLINE(DeathHook) {
    static void Callback(PlayerHitPointData* self) {
        Orig(self);
        smoap::ap::reportDeath();  // debounced inside reportDeath
    }
};
}  // namespace

void installDeathHook() {
    SMOAP_LOG_INFO("installing DeathHook -> %s", smoap::sym::kPlayerHitPointDataKill);
    softInstallAtSymbol<DeathHook>(smoap::sym::kPlayerHitPointDataKill);
}

}  // namespace smoap::hooks
