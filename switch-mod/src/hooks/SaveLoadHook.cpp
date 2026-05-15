// Hook on GameDataFile::initializeData().
//
// M3: empty trampoline. M4 wires this to drop our session dedupe set and
// request a checked_replay from the bridge (which fires automatically on
// our next HELLO).

#include "lib.hpp"
#include "../ap/ApClient.hpp"
#include "../ap/ApState.hpp"
#include "../util/Log.hpp"
#include "HookSymbols.hpp"
#include "SoftInstall.hpp"

class GameDataFile;

namespace smoap::hooks {

namespace {
HOOK_DEFINE_TRAMPOLINE(SaveLoadHook) {
    static void Callback(GameDataFile* self) {
        Orig(self);
        SMOAP_LOG_INFO("SaveLoadHook: clearing session state + requesting re-HELLO");
        auto& st = smoap::ap::ApState::instance();
        // Reset frame-thread-only dedupe state. These are touched only from
        // the frame thread so no lock is needed.
        st.locations_checked.reset();
        st.captures_unlocked.reset();
        st.received_kingdom_mask = 0;
        st.goal_sent = false;
        st.death_pending_send.store(false, std::memory_order_release);
        // Tell the socket worker to close-and-reopen so the bridge's HELLO
        // replay re-syncs both sides. The actual socket close happens on the
        // worker thread; we just set the atomic here.
        smoap::ap::ApClient::instance().requestRehello();
    }
};
}  // namespace

void installSaveLoadHook() {
    SMOAP_LOG_INFO("installing SaveLoadHook -> %s", smoap::sym::kGameDataFileInitializeData);
    softInstallAtSymbol<SaveLoadHook>(smoap::sym::kGameDataFileInitializeData);
}

}  // namespace smoap::hooks
