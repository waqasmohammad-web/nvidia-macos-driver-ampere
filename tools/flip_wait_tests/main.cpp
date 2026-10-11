/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
#include "nvrm-flip-wait.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
int main() {
    unsigned checks = 0;
    // Immediate completion, delayed completion, final permitted query, exhaustion.
    for (unsigned pendingCount : {0u, 1u, 16u, 99u, 100u, 101u}) {
        unsigned calls = 0, sleeps = 0;
        auto r = nvrmWaitFlipCompletion([&](bool &pending) { pending = calls++ < pendingCount; return true; }, [&] { ++sleeps; });
        assert(r.complete == (pendingCount < 100)); ++checks;
        assert(!r.queryFailed); ++checks;
        assert(r.polls == calls && r.sleeps == sleeps); ++checks;
        assert(calls == (pendingCount < 100 ? pendingCount+1 : 100)); ++checks;
        assert(sleeps == (pendingCount < 100 ? pendingCount : 100)); ++checks;
    }
    // Query failure is distinct from pending exhaustion, even if output says done.
    for (unsigned failureAt : {0u, 7u, 99u}) {
        unsigned calls = 0, sleeps = 0;
        auto r = nvrmWaitFlipCompletion([&](bool &pending) { unsigned n = calls++; pending = n != failureAt; return n != failureAt; }, [&] { ++sleeps; });
        assert(!r.complete && r.queryFailed); ++checks;
        assert(r.polls == failureAt+1 && r.sleeps == failureAt); ++checks;
        assert(calls == r.polls && sleeps == r.sleeps); ++checks;
    }
    printf("PASS: %u production flip-wait assertions\n", checks);
}
