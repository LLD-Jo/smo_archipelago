// Strategy B port (per HAKKUN.md): trampoline StaffRollScene::init instead
// of the exlaunch inline patch at +0x4C54A4. StaffRollScene is the credits-
// only scene class per OdysseyDecomp; its init only fires when the post-
// wedding cutscene chains into credits, never on Darker Side / portrait
// warp / save load. Same goal-once latch semantics as the inline patch
// (gated by ApState::goal_sent, cleared by SaveLoadHook on save reload).
//
// If Ryujinx / real-Switch validation reveals a false-positive (e.g.
// credits-from-menu would also call StaffRollScene::init), fall back to
// Strategy A: naked-trampoline @ 0x4C54A4 via Hakkun's writeBranchLinkAt
// MainOffset. Not expected per spike Gate 3 analysis.

#include "hk/hook/Trampoline.h"
#include "hk/types.h"

#include "../ap/ApFrameBridge.hpp"
#include "../ap/ApState.hpp"
#include "../util/Log.hpp"

namespace al { class ActorInitInfo; }

namespace smoap::hooks {

namespace {

HkTrampoline<void, void*, const al::ActorInitInfo*> creditsStartHook =
    hk::hook::trampoline([](void* self, const al::ActorInitInfo* init_info) -> void {
        creditsStartHook.orig(self, init_info);
        auto& st = smoap::ap::ApState::instance();
        if (st.goal_sent) return;
        st.goal_sent = true;
        SMOAP_LOG_INFO("[credits] StaffRollScene::init reached — reporting goal");
        smoap::ap::reportGoal();
    });

}  // namespace

void installCreditsStartHook() {
    SMOAP_LOG_INFO("installing CreditsStartHook -> StaffRollScene::init (Strategy B)");
    creditsStartHook.installAtSym<
        "_ZN14StaffRollScene4initERKN2al13ActorInitInfoE">();
}

}  // namespace smoap::hooks
