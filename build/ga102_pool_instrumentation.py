"""Add diagnostic pool telemetry to an owned snapshot only, never production."""


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('pool instrumentation site changed: '+old[:80])
    return source.replace(old, new)


def instrument(source):
    if "static int ga102_pool_buffer_body(" in source:
        raise ValueError("pool telemetry already applied")
    signature = 'static int pool_buffer_create_in(int vram, size_t size, nvk_buffer *out)\n{'
    source = once(source, signature, '''static _Atomic uint64_t ga102_pool_requests, ga102_pool_failures;
static _Atomic uint64_t ga102_pool_request_ns, ga102_pool_wait_ns;
static _Atomic uint64_t ga102_pool_growths, ga102_pool_growth_ns;
static _Atomic uint64_t ga102_pool_fragmented_growths;
static _Thread_local uint64_t ga102_pool_wait, ga102_pool_grow_start;
static _Thread_local int ga102_pool_fragmented;
static int ga102_pool_buffer_body(int vram, size_t size, nvk_buffer *out)
{''')
    start = source.index('static int ga102_pool_buffer_body(')
    end = source.index('static int pool_buffer_create(size_t size, nvk_buffer *out) {', start)
    body = source[start:end]
    body = once(body, '\n    pthread_mutex_lock(&g_pool_lock);', '''
    uint64_t poolWaitT=ga102_tick();
    pthread_mutex_lock(&g_pool_lock);
    ga102_pool_wait=ga102_tick()-poolWaitT;''')
    body = once(body, '    if (!got) {', '''    if (!got) {
        // Total free bytes can be fragmented between holes or separate blocks.
        // Neither permits placing a single buffer across those ranges.
        uint64_t freeBytes=0;
        for (pool_block *p=*head;p;p=p->next) {
            freeBytes+=p->heap.size-p->used;
            for (uint32_t i=0;i<p->nfr;i++) freeBytes+=p->fr[i].len;
        }
        ga102_pool_fragmented=freeBytes>=len;
        ga102_pool_grow_start=ga102_tick();''')
    # End growth span at heap publication, before placed-buffer creation.
    body = once(body, '    blk->nlive++;', '''    if (ga102_pool_grow_start) {
        atomic_fetch_add(&ga102_pool_growth_ns,ga102_tick()-ga102_pool_grow_start);
        ga102_pool_grow_start=0;
        atomic_fetch_add(&ga102_pool_growths,1);
        atomic_fetch_add(&ga102_pool_fragmented_growths,ga102_pool_fragmented);
    }
    blk->nlive++;''')
    wrapper = '''static int pool_buffer_create_in(int vram, size_t size, nvk_buffer *out)
{
    uint64_t poolRequestT=ga102_tick();
    ga102_pool_wait=ga102_pool_grow_start=0; ga102_pool_fragmented=0;
    int result=ga102_pool_buffer_body(vram,size,out);
    if (ga102_pool_grow_start) {
        atomic_fetch_add(&ga102_pool_growths,1);
        atomic_fetch_add(&ga102_pool_growth_ns,ga102_tick()-ga102_pool_grow_start);
        atomic_fetch_add(&ga102_pool_fragmented_growths,ga102_pool_fragmented);
    }
    atomic_fetch_add(&ga102_pool_requests,1);
    atomic_fetch_add(&ga102_pool_failures,result!=0);
    atomic_fetch_add(&ga102_pool_request_ns,ga102_tick()-poolRequestT);
    atomic_fetch_add(&ga102_pool_wait_ns,ga102_pool_wait);
    return result;
}
'''
    return source[:start]+body+wrapper+source[end:]


EXPORT = r'''
__attribute__((visibility("default"))) const char *ga102_perf_pool_trace(void) {
    static _Thread_local char output[1024];
    snprintf(output,sizeof output,
        "{\"requests\":%llu,\"failures\":%llu,\"request_ns\":%llu,\"lock_wait_ns\":%llu,\"growths\":%llu,\"growth_ns\":%llu,\"fragmented_growths\":%llu}",
        (unsigned long long)atomic_load(&ga102_pool_requests),
        (unsigned long long)atomic_load(&ga102_pool_failures),
        (unsigned long long)atomic_load(&ga102_pool_request_ns),
        (unsigned long long)atomic_load(&ga102_pool_wait_ns),
        (unsigned long long)atomic_load(&ga102_pool_growths),
        (unsigned long long)atomic_load(&ga102_pool_growth_ns),
        (unsigned long long)atomic_load(&ga102_pool_fragmented_growths));
    return output;
}
'''
