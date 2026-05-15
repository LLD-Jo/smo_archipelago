// Hook on GameDataFile::setMainScenarioNo(int).
//
// M3: empty trampoline. M4 reports scenario via reportStatus.

#include "lib.hpp"
#include "../ap/ApFrameBridge.hpp"
#include "../util/Log.hpp"
#include "HookSymbols.hpp"
#include "SoftInstall.hpp"

class GameDataFile;

namespace smoap::hooks {

namespace {
HOOK_DEFINE_TRAMPOLINE(ScenarioFlagHook) {
    static void Callback(GameDataFile* self, int scenario_no) {
        Orig(self, scenario_no);
        SMOAP_LOG_INFO("ScenarioFlagHook: scenario_no=%d", scenario_no);
        // stage_name is left empty here; the bridge tags status with the
        // last kingdom from the most recent moon check. A future
        // ScenarioFlagHook revision can pull the current stage via
        // self->getStageNameCurrent() once we wire that lookup.
        smoap::ap::reportStatus(/*stage_name=*/nullptr, scenario_no);
    }
};
}  // namespace

void installScenarioFlagHook() {
    SMOAP_LOG_INFO("installing ScenarioFlagHook -> %s", smoap::sym::kGameDataFileSetMainScenarioNo);
    softInstallAtSymbol<ScenarioFlagHook>(smoap::sym::kGameDataFileSetMainScenarioNo);
}

}  // namespace smoap::hooks
