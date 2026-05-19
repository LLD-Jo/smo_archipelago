// Per-shine palette override via inline patches at 4 BL call sites inside
// Shine::init. Matches Kgamer77/SuperMarioOdysseyArchipelago's technique
// (MIT, codehook.slpatch) on SMO 1.0.0 — they redirect each BL to a wrapper;
// we use exlaunch's HOOK_DEFINE_INLINE to intercept before the BL fires and
// modify the color arg register in place.
//
// Why inline patches, not a symbol hook on rs::setStageShineAnimFrame?
// That function is called from MULTIPLE actor types (Shine AND
// ShineTowerRocket, observed live). Reading Shine-class fields off a
// non-Shine actor crashed in StageScene init. Patching inside Shine::init's
// body guarantees the parent IS a Shine.
//
// 1.0.0 offsets (verified against real main.nso disassembly 2026-05-19):
//   0x1cdce4 -> BL rs::setStageShineAnimFrame   (Mtp anim, X0 = Shine self)
//   0x1cdd3c -> BL rs::setStageShineAnimFrame   (Mtp anim, X0 = child actor)
//   0x1cddcc -> BL rs::setStageShineAnimFrame   (Mcl anim, X0 = Shine self)
//   0x1cde24 -> BL rs::setStageShineAnimFrame   (Mcl anim, X0 = child actor)
//
// Each shine fires exactly 2 of 4 sites: one Mtp + one Mcl. Which member of
// each pair runs depends on a per-shine branch inside Shine::init that picks
// between "apply on the Shine's own model" and "apply on a child LiveActor
// stored at [Shine + 0x2e8]" (the latter is the 2D ShineDot 'Dot' model
// holder). The X0 of the BL therefore varies between Shine and child.
//
// At each site, the AArch64 ABI has:
//   X0 = LiveActor* (Shine OR child — depends on site, see above)
//   X1 = const char* stageName
//   W2 = int color           <-- substitute this
//   W3 = bool isMatAnim
//
// Reading mShineIdx off X0 worked at 0x1cdce4 / 0x1cddcc (X0 = Shine) but
// was a buffer over-read past the child's 264-byte size at 0x1cdd3c /
// 0x1cde24, returning garbage. For 3D shines that mostly hit the Shine-self
// sites that landed correctly, but the ShineDot (2D-mural) variant runs
// through both child-actor sites and was silently no-op'd by the
// kNoPaletteOverride early-return.
//
// Fix: read the parent Shine* out of X19 instead. Shine::init's prologue
// does `mov x19, x0` at 0x1cd50c and x19 is callee-saved on the stack, so
// X19 holds the original Shine* across the whole function body — including
// every one of the 4 BL sites. mShineIdx at +0x290 is then always valid.

#include "lib.hpp"  // HOOK_DEFINE_INLINE, exl::hook::InlineCtx
#include "../ap/ApState.hpp"
#include "../util/Log.hpp"
#include "SoftInstall.hpp"

#include <cstdint>

namespace smoap::hooks {

namespace {

// Shine::mShineIdx offset per Kgamer77/SuperMarioOdysseyArchipelago
// Mod/include/game/Actors/Shine.h (MIT). Same value the bridge keys the
// palette table by — MoonGetHook reports it as ShineInfo::shineId for
// outbound checks, and Shine caches it locally on the actor.
inline constexpr std::size_t kShineMShineIdxOffset = 0x290;

// 1.0.0 BL call sites Kgamer77 patches in Shine::init. Same 4 offsets
// applied to our exlaunch InlineHook give us the same effect: substitute
// the color arg right before the BL fires.
inline constexpr ptrdiff_t kShineColorPatchOffsets[] = {
    0x1cdce4, 0x1cdd3c, 0x1cddcc, 0x1cde24,
};

HOOK_DEFINE_INLINE(ShineInitColorPatch) {
    static void Callback(exl::hook::InlineCtx* ctx) {
        // X19 holds the parent Shine* across all 4 patch sites — Shine::init's
        // prologue stashes the first arg there. X0 at the BL is the actor
        // about-to-be-passed to setStageShineAnimFrame, which may be either
        // the Shine itself OR a child LiveActor at [Shine + 0x2e8] depending
        // on the site / per-shine branch (see the file-header comment).
        // mShineIdx only lives on the Shine, so we always read it off X19.
        const auto* parent = reinterpret_cast<const std::uint8_t*>(ctx->X[19]);
        if (!parent) return;
        const int uid = *reinterpret_cast<const int*>(
            parent + kShineMShineIdxOffset);
        if (uid < 0 ||
            static_cast<std::size_t>(uid) >= smoap::ap::ApState::kMaxShineUid) {
            return;
        }
        const std::uint8_t pal = smoap::ap::ApState::instance().getShinePalette(uid);
        if (pal == smoap::ap::ApState::kNoPaletteOverride) return;

        // Log first few real substitutions so we can confirm in Ryujinx.
        // Per-shine, each Shine::init fires 2 of the 4 patches (one Mtp +
        // one Mcl), so 2 fires per moon is the natural rate — 16
        // substitutions covers ~8 shines. Logging both X0 and X19 surfaces
        // the Shine-vs-child distinction so we can verify the 2D ShineDot
        // path fires correctly (X0 != X19 there).
        static int s_subst_count = 0;
        if (s_subst_count < 16) {
            SMOAP_LOG_INFO("[shine-color] subst#%d actor=%p shine=%p uid=%d palette=%u",
                           s_subst_count + 1, ctx->X[0], ctx->X[19], uid,
                           static_cast<unsigned>(pal));
        }
        ++s_subst_count;
        ctx->W[2] = pal;  // substitute the color arg (zero-extends X2)
    }
};

}  // namespace

void installShineAppearanceHook() {
    for (ptrdiff_t off : kShineColorPatchOffsets) {
        SMOAP_LOG_INFO("installing ShineInitColorPatch @ +0x%lx",
                       static_cast<unsigned long>(off));
        ShineInitColorPatch::InstallAtOffset(off);
    }
}

}  // namespace smoap::hooks
