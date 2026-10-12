// Test-only: copied into the isolated plugin; never included by production.
#ifndef GA102_PERF_METRICS_H
#define GA102_PERF_METRICS_H
#include <stdatomic.h>
#include <stdint.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <limits.h>
#include <errno.h>

enum ga102_event {
    GA102_AIR_EXTRACT, GA102_REFLECT, GA102_RUST, GA102_SAMPLER_ABI,
    GA102_LOWER, GA102_VK_PIPELINE, GA102_LOCAL_HIT, GA102_LOCAL_MISS,
    GA102_DEVICE_HIT, GA102_DEVICE_MISS, GA102_VARIANT_BUILD,
    GA102_AIR_MEMORY_HIT, GA102_AIR_DISK_HIT, GA102_AIR_MISS,
    GA102_SPV_HIT, GA102_SPV_MISS, GA102_INDEX_DISK_HIT,
    GA102_SAMPLER_BIND, GA102_LOCAL_LOOKUP, GA102_DEVICE_LOOKUP, GA102_VK_ERROR, GA102_EVENT_COUNT
};
static const char *const ga102_event_names[] = {
    "air_extract", "reflect", "rust", "sampler_abi", "lower", "vk_pipeline",
    "local_hit", "local_miss", "device_hit", "device_miss", "variant_build",
    "air_memory_hit", "air_disk_hit", "air_miss", "spv_hit", "spv_miss", "index_disk_hit",
    "sampler_bind", "local_lookup", "device_lookup", "vk_error"
};
struct ga102_metric { _Atomic uint64_t count, ns, failures; };
static struct ga102_metric ga102_metrics[GA102_EVENT_COUNT];
static uint64_t ga102_tick(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) { fputs("GA102 clock unavailable\n", stderr); _Exit(1); }
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}
static void ga102_record(unsigned event, uint64_t elapsed, int failed) {
    if (event >= GA102_EVENT_COUNT) _Exit(1);
    atomic_fetch_add_explicit(&ga102_metrics[event].count, 1, memory_order_relaxed);
    atomic_fetch_add_explicit(&ga102_metrics[event].ns, elapsed, memory_order_relaxed);
    if (failed) atomic_fetch_add_explicit(&ga102_metrics[event].failures, 1, memory_order_relaxed);
}
static void ga102_hit(unsigned event) { ga102_record(event, 0, 0); }
static const char *ga102_metrics_json(void) {
    static _Thread_local char out[4096];
    size_t used = 0;
    out[used++] = '{';
    for (unsigned i = 0; i < GA102_EVENT_COUNT; ++i) {
        int n = snprintf(out + used, sizeof out - used,
            "%s\"%s\":{\"count\":%llu,\"ns\":%llu,\"failures\":%llu}",
            i ? "," : "", ga102_event_names[i],
            (unsigned long long)atomic_load_explicit(&ga102_metrics[i].count, memory_order_relaxed),
            (unsigned long long)atomic_load_explicit(&ga102_metrics[i].ns, memory_order_relaxed),
            (unsigned long long)atomic_load_explicit(&ga102_metrics[i].failures, memory_order_relaxed));
        if (n < 0 || (size_t)n >= sizeof out - used) _Exit(1);
        used += (size_t)n;
    }
    out[used++] = '}'; out[used] = 0; return out;
}
static void ga102_stop(const char *why) { fprintf(stderr, "GA102 isolation failure: %s\n", why); _Exit(1); }
static int ga102_private(const char *path, int directory) {
    struct stat s;
    return lstat(path, &s) == 0 && s.st_uid == getuid() &&
        (s.st_mode & 0777) == (directory ? 0700 : 0600) &&
        (directory ? S_ISDIR(s.st_mode) : S_ISREG(s.st_mode));
}
// The launcher creates this root via mkdtemp, never an existing driver cache.
// Check the marker/token and all leaves; no creation or production fallback here.
static const char *ga102_owned_root(void) {
    static _Thread_local char root[PATH_MAX];
    const char *requested = getenv("GA102_TEST_CACHE"), *token = getenv("GA102_TEST_TOKEN");
    if (!requested || !token || strlen(token) != 64 || !realpath(requested, root) || strcmp(root, requested))
        ga102_stop("canonical cache/token required");
    if (!ga102_private(root, 1)) ga102_stop("cache root must be owned mode 0700");
    char p[PATH_MAX];
    if (snprintf(p, sizeof p, "%s/.ga102-owned", root) >= (int)sizeof p || !ga102_private(p, 0))
        ga102_stop("owned marker unavailable");
    int fd = open(p, O_RDONLY | O_NOFOLLOW); char b[65];
    if (fd < 0) ga102_stop("marker open failed");
    ssize_t n = read(fd, b, sizeof b); close(fd);
    if (n != 64 || memcmp(b, token, 64)) ga102_stop("marker token mismatch");
    const char *leaves[] = {"air", "spvcache", "mesa", "capture"};
    for (unsigned i = 0; i < 4; ++i) {
        if (snprintf(p, sizeof p, "%s/%s", root, leaves[i]) >= (int)sizeof p || !ga102_private(p, 1))
            ga102_stop("cache leaf must be private directory, not symlink");
    }
    return root;
}
static const char *ga102_owned_air(void) {
    static _Thread_local char path[PATH_MAX];
    if (snprintf(path, sizeof path, "%s/air", ga102_owned_root()) >= (int)sizeof path) ga102_stop("AIR path too long");
    return path;
}
static void ga102_owned_mesa(void) {
    if (getenv("NVMTL_APPLE_PIPELINE") || getenv("NVMTL_VENDOR_COMPILER"))
        ga102_stop("alternate pipeline/compiler configured; NVK experiment refused");
    char p[PATH_MAX];
    if (snprintf(p, sizeof p, "%s/mesa", ga102_owned_root()) >= (int)sizeof p || setenv("MESA_SHADER_CACHE_DIR", p, 1))
        ga102_stop("Mesa route unavailable");
    // A conflicting inherited override must fail, not silently disable caching.
    const char *disable = getenv("MESA_SHADER_CACHE_DISABLE");
    if (disable && strcmp(disable, "false") && strcmp(disable, "0")) ga102_stop("Mesa cache disabled");
}
// Qualification only. File writes occur after the timed ABI span; timed trials
// must leave GA102_TEST_CAPTURE unset and use separate new owned cache roots.
static void ga102_capture(unsigned event, const uint8_t *bytes, size_t size) {
    if (!getenv("GA102_TEST_CAPTURE")) return;
    static _Atomic uint64_t serial;
    char p[PATH_MAX];
    uint64_t n=atomic_fetch_add_explicit(&serial,1,memory_order_relaxed);
    if (!bytes || size < 20 || size % 4 || snprintf(p,sizeof p,"%s/capture/%u-%llu.spv",ga102_owned_root(),event,(unsigned long long)n) >= (int)sizeof p)
        ga102_stop("invalid captured SPIR-V");
    int fd=open(p,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
    if (fd < 0) ga102_stop("capture create failed");
    size_t written=0;
    while (written < size) {
        ssize_t count=write(fd,bytes+written,size-written);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) ga102_stop("capture write failed");
        written+=(size_t)count;
    }
    if (close(fd)) ga102_stop("capture close failed");
}
#endif
