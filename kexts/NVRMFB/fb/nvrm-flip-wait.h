/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
#ifndef NVRM_FLIP_WAIT_H
#define NVRM_FLIP_WAIT_H
struct NVRMFlipWaitResult {
    bool complete, queryFailed;
    unsigned polls, sleeps;
};
/* Preserve the existing 100 queries / 1 ms sleep contract. A failed query is
 * not a completed flip. No extra query or surface retirement on exhaustion. */
template<class Query, class Sleep>
static NVRMFlipWaitResult nvrmWaitFlipCompletion(Query query, Sleep sleep)
{
    NVRMFlipWaitResult r = {false, false, 0, 0};
    for (unsigned i = 0; i < 100; ++i) {
        bool pending = true;
        ++r.polls;
        if (!query(pending)) { r.queryFailed = true; return r; }
        if (!pending) { r.complete = true; return r; }
        ++r.sleeps; sleep();
    }
    return r;
}
#endif
