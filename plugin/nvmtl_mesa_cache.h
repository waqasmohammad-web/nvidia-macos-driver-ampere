/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
#ifndef NVMTL_MESA_CACHE_H
#define NVMTL_MESA_CACHE_H

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

enum nvmtl_mesa_cache_result {
    NVMTL_MESA_CACHE_UNAVAILABLE = -1,
    NVMTL_MESA_CACHE_UNCHANGED = 0,
    NVMTL_MESA_CACHE_HOME = 1,
    NVMTL_MESA_CACHE_DARWIN = 2
};

/* Require a searchable writable directory, not merely a writable pathname.
 * Parents may be platform symlinks (e.g. /var); the final cache must be a real
 * directory. Never replace an existing file/link or change its permissions. */
static inline int nvmtl_mesa_cache_prepare(const char *parent, const char *suffix,
                                         char *out, size_t capacity)
{
    if (!parent || parent[0] != '/' || !out || !capacity) return 0;
    const int n = snprintf(out, capacity, "%s%s%s", parent,
                           parent[strlen(parent) - 1] == '/' ? "" : "/", suffix);
    if (n < 0 || (size_t)n >= capacity) return 0;
    struct stat st;
    if (stat(parent, &st) || !S_ISDIR(st.st_mode) || access(parent, X_OK)) return 0;
    if (lstat(out, &st) == 0)
        return S_ISDIR(st.st_mode) && access(out, W_OK | X_OK) == 0;
    if (errno != ENOENT) return 0;
    // mkdir enforces write permission when creation is needed. An existing
    // writable cache also works under a read-only but searchable parent.
    if (mkdir(out, 0700) && errno != EEXIST) return 0;
    return lstat(out, &st) == 0 && S_ISDIR(st.st_mode) && access(out, W_OK | X_OK) == 0;
}

/* The caller supplies confstr(_CS_DARWIN_USER_CACHE_DIR)'s bounded result.
 * Return the chosen path for logging; setenv(overwrite=0) preserves a setting
 * another initializer may have supplied in the meantime. */
static inline enum nvmtl_mesa_cache_result
nvmtl_mesa_cache_configure(const char *darwin_parent, char *out, size_t capacity)
{
    if (getenv("MESA_SHADER_CACHE_DIR") || getenv("XDG_CACHE_HOME") ||
        getenv("NVMTL_NO_MESA_CACHE_DIR")) return NVMTL_MESA_CACHE_UNCHANGED;
    const char *home = getenv("HOME");
    char parent[4096];
    int n = home ? snprintf(parent, sizeof parent, "%s/Library/Caches", home) : -1;
    enum nvmtl_mesa_cache_result chosen = NVMTL_MESA_CACHE_UNAVAILABLE;
    if (n > 0 && (size_t)n < sizeof parent &&
        nvmtl_mesa_cache_prepare(parent, "nvmtl-mesa", out, capacity))
        chosen = NVMTL_MESA_CACHE_HOME;
    else if (nvmtl_mesa_cache_prepare(darwin_parent, "nvmtl-mesa", out, capacity))
        chosen = NVMTL_MESA_CACHE_DARWIN;
    if (chosen < 0) return chosen;
    if (setenv("MESA_SHADER_CACHE_DIR", out, 0)) return NVMTL_MESA_CACHE_UNAVAILABLE;
    const char *effective = getenv("MESA_SHADER_CACHE_DIR");
    return effective && !strcmp(effective, out) ? chosen : NVMTL_MESA_CACHE_UNCHANGED;
}

#endif
