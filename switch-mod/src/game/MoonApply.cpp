// SCAFFOLD ONLY. M4/M6 fill in via lunakit-vendor's GameDataHolder helpers.

#include "MoonApply.hpp"

#include "../util/Log.hpp"

namespace smoap::game {

void grantShine(const std::string& kingdom, const std::string& shine_id) {
    SMOAP_LOG_INFO("grantShine (stub): %s / %s", kingdom.c_str(), shine_id.c_str());
    // M6:
    //   GameDataHolder* gdh = al::tryGetGameDataHolder();
    //   if (!gdh) return;
    //   ShineId sid = mapShineId(kingdom, shine_id);
    //   if (gdh->isGetShine(sid)) return;
    //   gdh->setShineGet(sid);  // also bumps moon counter / opens gates
}

bool extractShineCoords(std::string& out_kingdom, std::string& out_shine_id) {
    out_kingdom.clear();
    out_shine_id.clear();
    return false;
}

void enumerateOwnedShines(ShineEnumerationCallback cb, void* ctx) {
    // M5/M6 will iterate GameDataHolder's got-shine table and invoke `cb` once
    // per owned shine with its (stage_name, object_id, shine_uid). Stub for
    // M4.5: emit nothing. The bridge handles an empty snapshot as a no-op.
    (void)cb;
    (void)ctx;
}

}  // namespace smoap::game
