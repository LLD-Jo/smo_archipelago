#!/usr/bin/env python3
"""Apply Windows-port patches to the pinned LibHakkun submodule.

The spike at third_party/hakkun-spike (gitignored) discovered six source-level
patches needed to build LibHakkun + sail on Windows + msys2. Each patch is
idempotent (uses a sentinel check before applying). On first run, all six
land; subsequent runs report 'already applied' and exit cleanly.

These patches should be upstreamed to fruityloops1/LibHakkun. While upstream
PRs are in flight, this script reapplies them locally after submodule init.
If a PR review stalls > 1 week, the migration plan calls for forking
LibHakkun to mdietz94/LibHakkun-smo and re-pinning the submodule — at which
point this script becomes obsolete.

Patches applied:
  1. sys/sail/CMakeLists.txt — drop hardcoded clang/clang++ compiler.
  2. sys/sail/src/main.cpp — std::filesystem::path::c_str() is wchar_t* on Windows.
  3. sys/sail/src/fakelib.cpp — quote clangBinary path in popen cmdline.
  4. sys/cmake/sail.cmake — expand sys/addons/*/syms glob (cmd.exe doesn't).
  5. sys/cmake/generate_exefs.cmake — prefix elf2nso.py with `python`.
  6. (env only) Copy sys/sail/build/sail.exe → sys/sail/build/sail (no ext).
     Handled by scripts/build_switchmod_hk.py.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAKKUN = os.path.join(REPO_ROOT, "switch-mod-hk", "sys")


def patch_file(path: str, old: str, new: str, sentinel: str) -> str:
    """Apply a literal-string patch. Idempotent via sentinel check.

    Returns 'applied', 'already-applied', or 'missing'.
    """
    if not os.path.exists(path):
        return "missing"
    content = open(path, encoding="utf-8").read()
    if sentinel in content:
        return "already-applied"
    if old not in content:
        # The expected old text isn't present and the sentinel isn't either.
        # Either upstream has moved (need to revisit this patch) or we're
        # already mid-migration to a fork. Fail loud.
        sys.exit(f"[patch_hakkun] '{path}': old text not found and sentinel absent; upstream likely changed")
    new_content = content.replace(old, new, 1)
    open(path, "w", encoding="utf-8", newline="\n").write(new_content)
    return "applied"


def report(name: str, result: str) -> None:
    print(f"  [{result:>15}] {name}")


def main() -> int:
    if not os.path.isdir(HAKKUN):
        sys.exit(f"[patch_hakkun] {HAKKUN} not found — `git submodule update --init` first")

    print(f"[patch_hakkun] applying Windows-port patches to {HAKKUN}")

    # Patch 1: drop hardcoded compiler in sys/sail/CMakeLists.txt.
    # These set() lines come AFTER project() so they do nothing useful (compiler
    # already detected), but their values DO get baked into ninja rules, which
    # is what breaks the host build with our env-var-supplied gcc.
    report(
        "sail CMakeLists.txt clang/clang++ removal",
        patch_file(
            os.path.join(HAKKUN, "sail", "CMakeLists.txt"),
            "set(CMAKE_C_COMPILER clang)\nset(CMAKE_CXX_COMPILER clang++)\nset(CMAKE_CXX_STANDARD 23)",
            "set(CMAKE_CXX_STANDARD 23)",
            sentinel="# SMO_HAKKUN_PATCH_1",
        ),
    )
    _maybe_add_sentinel(
        os.path.join(HAKKUN, "sail", "CMakeLists.txt"),
        "set(CMAKE_CXX_STANDARD 23)",
        "# SMO_HAKKUN_PATCH_1: removed hardcoded clang/clang++ — host build uses CC/CXX env vars\n",
    )

    report(
        "sail main.cpp filesystem::path wchar_t fix",
        patch_file(
            os.path.join(HAKKUN, "sail", "src", "main.cpp"),
            "            const char* path = entry.path().c_str();",
            "            std::string path_str = entry.path().string();  // SMO_HAKKUN_PATCH_2: Windows wchar_t fix\n            const char* path = path_str.c_str();",
            sentinel="SMO_HAKKUN_PATCH_2",
        ),
    )

    report(
        "sail fakelib.cpp clang path quoting",
        patch_file(
            os.path.join(HAKKUN, "sail", "src", "fakelib.cpp"),
            "    static void compile(const char* outPath, const char* clangBinary, const char* language, const std::string& source, const std::string& flags, const char* filename) {\n        std::string cmd = clangBinary;",
            "    static void compile(const char* outPath, const char* clangBinary, const char* language, const std::string& source, const std::string& flags, const char* filename) {\n        // SMO_HAKKUN_PATCH_3: quote clangBinary for Windows paths with spaces.\n        std::string cmd;\n        cmd.push_back('\"');\n        cmd.append(clangBinary);\n        cmd.push_back('\"');",
            sentinel="SMO_HAKKUN_PATCH_3",
        ),
    )

    report(
        "sail.cmake addons glob expansion",
        patch_file(
            os.path.join(HAKKUN, "cmake", "sail.cmake"),
            "        if (ADDONS_SYMS_EMPTY_TEST)\n            set(SAIL_CMD ${SAIL_CMD} ${CMAKE_CURRENT_SOURCE_DIR}/sys/addons/*/syms)\n        endif()",
            "        if (ADDONS_SYMS_EMPTY_TEST)\n            # SMO_HAKKUN_PATCH_4: expand glob ourselves (cmd.exe doesn't).\n            file(GLOB ADDONS_SYM_DIRS LIST_DIRECTORIES TRUE ${CMAKE_CURRENT_SOURCE_DIR}/sys/addons/*/syms)\n            foreach (d IN LISTS ADDONS_SYM_DIRS)\n                if (IS_DIRECTORY ${d})\n                    set(SAIL_CMD ${SAIL_CMD} ${d})\n                endif()\n            endforeach()\n        endif()",
            sentinel="SMO_HAKKUN_PATCH_4",
        ),
    )

    report(
        "generate_exefs.cmake python prefix",
        patch_file(
            os.path.join(HAKKUN, "cmake", "generate_exefs.cmake"),
            "            COMMAND ${PROJECT_SOURCE_DIR}/sys/tools/elf2nso.py ${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}${CMAKE_EXECUTABLE_SUFFIX}.baked ${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}.nso -c",
            "            # SMO_HAKKUN_PATCH_5: explicit python invocation.\n            COMMAND python ${PROJECT_SOURCE_DIR}/sys/tools/elf2nso.py ${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}${CMAKE_EXECUTABLE_SUFFIX}.baked ${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}.nso -c",
            sentinel="SMO_HAKKUN_PATCH_5",
        ),
    )
    report(
        "generate_exefs.cmake python prefix (non-baked)",
        patch_file(
            os.path.join(HAKKUN, "cmake", "generate_exefs.cmake"),
            "            COMMAND ${PROJECT_SOURCE_DIR}/sys/tools/elf2nso.py ${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}${CMAKE_EXECUTABLE_SUFFIX} ${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}.nso -c",
            "            # SMO_HAKKUN_PATCH_5b: explicit python invocation (non-baked path).\n            COMMAND python ${PROJECT_SOURCE_DIR}/sys/tools/elf2nso.py ${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}${CMAKE_EXECUTABLE_SUFFIX} ${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}.nso -c",
            sentinel="SMO_HAKKUN_PATCH_5b",
        ),
    )

    print("[patch_hakkun] done")
    return 0


def _maybe_add_sentinel(path: str, after_line: str, sentinel: str) -> None:
    """Insert a sentinel comment after a given line so future re-runs detect 'already applied'."""
    if not os.path.exists(path):
        return
    content = open(path, encoding="utf-8").read()
    if sentinel.strip() in content:
        return
    if after_line not in content:
        return
    new_content = content.replace(after_line, after_line + "\n" + sentinel.rstrip() + "\n", 1)
    open(path, "w", encoding="utf-8", newline="\n").write(new_content)


if __name__ == "__main__":
    sys.exit(main())
