// M4: cap-name lookup via the generated capture_table.h. The bit index for a
// given cap matches its position in apworld/data/items.json (Capture category)
// so the Switch and bridge cannot drift on assignment.

#include "CaptureGate.hpp"

#include "../ap/ApState.hpp"
#include "../ap/capture_table.h"  // kCaptureNames
#include "../util/Log.hpp"

namespace smoap::game {

std::uint8_t captureBitFor(const std::string& cap_name) {
    for (std::uint8_t i = 0; i < kCaptureNames.size(); ++i) {
        if (cap_name == kCaptureNames[i]) return i;
    }
    return 0xff;
}

bool captureBlocked(const std::string& cap_name) {
    const std::uint8_t bit = captureBitFor(cap_name);
    if (bit == 0xff) return false;  // unknown -> don't block (fail open)
    return !smoap::ap::ApState::instance().captures_unlocked.test(bit);
}

std::string nameForHackData(/* const PlayerHackData* data */) {
    return {};  // M5
}

void playSE_NG() {
    // al::startSe(/* SE_NG */, /* ... */);
    SMOAP_LOG_INFO("playSE_NG (stub)");
}

void enumerateOwnedCaptures(CaptureEnumerationCallback cb, void* ctx) {
    // M5/M6 will iterate the player's used-capture record from GameDataHolder
    // and invoke cb with each raw hack_name. Stub for M4.5 — empty snapshot
    // is harmless.
    (void)cb;
    (void)ctx;
}

}  // namespace smoap::game
