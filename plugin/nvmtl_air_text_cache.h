// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Process-local immutable AIR text, keyed by the existing content/option path.
// Limits bound retained UTF-16 payload and entry count (not Foundation overhead).
#import <Foundation/Foundation.h>
#ifndef NVMTL_AIR_TEXT_ENTRIES
#define NVMTL_AIR_TEXT_ENTRIES 128u
#endif
#ifndef NVMTL_AIR_TEXT_BYTES
#define NVMTL_AIR_TEXT_BYTES (16u * 1024u * 1024u)
#endif
static NSString *nvmtl_air_text_cached(NSString *key, NSString *text) {
    if (!key.length) return nil;
    static NSMutableDictionary<NSString *, NSString *> *entries;
    static NSUInteger bytes;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ entries = [NSMutableDictionary new]; });
    @synchronized(entries) {
        NSString *hit = entries[key];
        if (hit) return hit;
        if (!text.length) return nil;
        const NSUInteger chars = NVMTL_AIR_TEXT_BYTES / sizeof(unichar);
        if (key.length > chars || text.length > chars - key.length) return nil;
        NSUInteger cost = (key.length + text.length) * sizeof(unichar);
        // Eviction affects only CPU lookup work; disk persistence remains intact.
        if (entries.count >= NVMTL_AIR_TEXT_ENTRIES || bytes > NVMTL_AIR_TEXT_BYTES - cost) {
            [entries removeAllObjects]; bytes = 0;
        }
        entries[[key copy]] = [text copy]; bytes += cost;
        return entries[key];
    }
}
