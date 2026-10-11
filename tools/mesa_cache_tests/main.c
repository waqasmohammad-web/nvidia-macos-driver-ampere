/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
/* Exercise production directory-selection code; all fixtures are test-owned. */
#include "nvmtl_mesa_cache.h"
#include <assert.h>
#include <limits.h>

static unsigned checks;
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); return 1; } checks++; } while (0)

int main(int argc, char **argv)
{
    if (argc != 3) return 2;
    const char *home = argv[1], *darwin = argv[2];
    char out[PATH_MAX], expected[PATH_MAX], final[PATH_MAX];
    setenv("HOME", home, 1);
    unsetenv("MESA_SHADER_CACHE_DIR"); unsetenv("XDG_CACHE_HOME"); unsetenv("NVMTL_NO_MESA_CACHE_DIR");
    CHECK(nvmtl_mesa_cache_configure(darwin, out, sizeof out) == NVMTL_MESA_CACHE_HOME);
    snprintf(expected, sizeof expected, "%s/Library/Caches/nvmtl-mesa", home);
    CHECK(!strcmp(out, expected)); CHECK(!strcmp(getenv("MESA_SHADER_CACHE_DIR"), expected));
    struct stat st;
    CHECK(lstat(out, &st) == 0 && S_ISDIR(st.st_mode) && (st.st_mode & 0777) == 0700);
    unsetenv("MESA_SHADER_CACHE_DIR");
    CHECK(nvmtl_mesa_cache_configure(darwin, out, sizeof out) == NVMTL_MESA_CACHE_HOME);
    // HOME itself need not be writable; the immediate cache parent is writable.
    CHECK(chmod(home, 0500) == 0);
    unsetenv("MESA_SHADER_CACHE_DIR");
    CHECK(nvmtl_mesa_cache_configure(darwin, out, sizeof out) == NVMTL_MESA_CACHE_HOME);
    CHECK(chmod(home, 0700) == 0);
    char cacheParent[PATH_MAX]; snprintf(cacheParent, sizeof cacheParent, "%s/Library/Caches", home);
    CHECK(chmod(cacheParent, 0500) == 0); unsetenv("MESA_SHADER_CACHE_DIR");
    CHECK(nvmtl_mesa_cache_configure(darwin, out, sizeof out) == NVMTL_MESA_CACHE_HOME);
    CHECK(chmod(cacheParent, 0700) == 0);
    for (unsigned i = 0; i < 3; i++) {
        const char *keys[] = {"MESA_SHADER_CACHE_DIR", "XDG_CACHE_HOME", "NVMTL_NO_MESA_CACHE_DIR"};
        unsetenv("MESA_SHADER_CACHE_DIR"); setenv(keys[i], "", 1);
        CHECK(nvmtl_mesa_cache_configure(darwin, out, sizeof out) == NVMTL_MESA_CACHE_UNCHANGED);
        CHECK(getenv(keys[i]) && !*getenv(keys[i])); unsetenv(keys[i]);
    }
    unsetenv("HOME");
    CHECK(nvmtl_mesa_cache_configure(darwin, out, sizeof out) == NVMTL_MESA_CACHE_DARWIN);
    snprintf(final, sizeof final, "%s/nvmtl-mesa", darwin);
    CHECK(!strcmp(out, final));
    // Reject regular files and symlinks, including at the Darwin fallback.
    unsetenv("MESA_SHADER_CACHE_DIR"); CHECK(rmdir(final) == 0);
    FILE *f = fopen(final, "w"); CHECK(f != NULL); CHECK(fclose(f) == 0);
    CHECK(nvmtl_mesa_cache_configure(darwin, out, sizeof out) == NVMTL_MESA_CACHE_UNAVAILABLE);
    CHECK(getenv("MESA_SHADER_CACHE_DIR") == NULL); CHECK(unlink(final) == 0);
    CHECK(symlink(expected, final) == 0);
    CHECK(nvmtl_mesa_cache_configure(darwin, out, sizeof out) == NVMTL_MESA_CACHE_UNAVAILABLE);
    CHECK(getenv("MESA_SHADER_CACHE_DIR") == NULL); CHECK(unlink(final) == 0);
    // Search permission is essential even if a directory is writable.
    CHECK(mkdir(final, 0700) == 0); CHECK(chmod(final, 0600) == 0);
    CHECK(nvmtl_mesa_cache_configure(darwin, out, sizeof out) == NVMTL_MESA_CACHE_UNAVAILABLE);
    CHECK(chmod(final, 0700) == 0);
    CHECK(!nvmtl_mesa_cache_prepare("relative", "nvmtl-mesa", out, sizeof out));
    CHECK(!nvmtl_mesa_cache_prepare(darwin, "nvmtl-mesa", out, 4));
    CHECK(!nvmtl_mesa_cache_prepare(NULL, "nvmtl-mesa", out, sizeof out));
    char oversized[5000]; memset(oversized, 'a', sizeof oversized - 1); oversized[0] = '/'; oversized[sizeof oversized - 1] = 0;
    setenv("HOME", oversized, 1);
    CHECK(nvmtl_mesa_cache_configure(darwin, out, sizeof out) == NVMTL_MESA_CACHE_DARWIN);
    unsetenv("MESA_SHADER_CACHE_DIR"); setenv("HOME", "", 1);
    CHECK(nvmtl_mesa_cache_configure(darwin, out, sizeof out) == NVMTL_MESA_CACHE_DARWIN);
    unsetenv("MESA_SHADER_CACHE_DIR");
    setenv("HOME", home, 1); CHECK(rmdir(expected) == 0); CHECK(symlink(darwin, expected) == 0);
    CHECK(nvmtl_mesa_cache_configure(darwin, out, sizeof out) == NVMTL_MESA_CACHE_DARWIN);
    // Explicit paths remain untouched even if they don't exist.
    setenv("MESA_SHADER_CACHE_DIR", "/explicit/cache/choice", 1);
    CHECK(nvmtl_mesa_cache_configure(NULL, out, sizeof out) == NVMTL_MESA_CACHE_UNCHANGED);
    CHECK(!strcmp(getenv("MESA_SHADER_CACHE_DIR"), "/explicit/cache/choice"));
    printf("PASS: %u production Mesa cache assertions\n", checks);
    return 0;
}
