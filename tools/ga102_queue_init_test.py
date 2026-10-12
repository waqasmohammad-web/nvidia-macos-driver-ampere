#!/usr/bin/env python3
"""CPU-only production texture-transfer queue publication and retry test.

The backend creator is replaced with a delayed, fault-injectable stub. No Metal
plugin, NVK channel, kernel service or GPU workload is loaded. ThreadSanitizer
must reject the pre-fix helper and accept the candidate. Logs stay private.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PREAMBLE = r'''
#import <Foundation/Foundation.h>
#include <pthread.h>
#include <stdatomic.h>
#include <assert.h>
#include <unistd.h>
#include "nvmtl_vk.h"
static _Atomic unsigned calls, invalid_reads;
static unsigned failures;
static void nvlog(const char *fmt, ...) { (void)fmt; }
int nvmtl_vk_queue_create(nvk_queue *out) {
    unsigned call = atomic_fetch_add(&calls, 1);
    usleep(1000);
    memset(out, 0, sizeof *out);
    if (call < failures) return -1;
    out->pool = (void *)(uintptr_t)0x1234;
    return 0;
}
'''
MAIN = r'''
static dispatch_semaphore_t ready, start;
static void *worker(void *arg) { @autoreleasepool {
    (void)arg; dispatch_semaphore_signal(ready);
    dispatch_semaphore_wait(start, DISPATCH_TIME_FOREVER);
    for (unsigned i=0; i<100; ++i) {
        nvk_queue *q=nvmtl_device_queue();
        if (!q || q->pool != (void *)(uintptr_t)0x1234) atomic_fetch_add(&invalid_reads,1);
    }
    return NULL;
}}
int main(int argc, char **argv) { @autoreleasepool {
    (void)argv;
    if (argc > 1) {
        failures=2;
        assert(nvmtl_device_queue()==NULL); assert(nvmtl_device_queue()==NULL);
    }
    ready=dispatch_semaphore_create(0); start=dispatch_semaphore_create(0);
    pthread_t threads[16];
    for (unsigned i=0;i<16;++i) assert(!pthread_create(&threads[i],NULL,worker,NULL));
    for (unsigned i=0;i<16;++i) dispatch_semaphore_wait(ready,DISPATCH_TIME_FOREVER);
    for (unsigned i=0;i<16;++i) dispatch_semaphore_signal(start);
    for (unsigned i=0;i<16;++i) assert(!pthread_join(threads[i],NULL));
    if (atomic_load(&calls)!=failures+1 || atomic_load(&invalid_reads)) {
        printf("FAIL: %u creation calls; %u invalid reads\n",atomic_load(&calls),atomic_load(&invalid_reads));
        return 1;
    }
    printf("PASS: 1600 concurrent queue reads; %u creation calls; failed creation retried\n", atomic_load(&calls));
    return 0;
}}
'''


def helper(source):
    begin = source.index('static nvk_queue *nvmtl_device_queue(void) {')
    return source[begin:source.index('static bool nvmtl_accel_armed', begin)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sources = [('candidate', (ROOT / 'plugin/NVMTLDevice.m').read_text())]
    if args.baseline:
        sources.insert(0, ('original', subprocess.check_output(
            ['git', 'show', '44ed7c7:plugin/NVMTLDevice.m'], cwd=ROOT, text=True)))
    rows = []
    for label, source in sources:
        function = helper(source)
        unit = args.output / (label + '.m')
        unit.write_text(PREAMBLE + function + MAIN)
        exe = args.output / label
        with (args.output / (label + '-compile.private.log')).open('w') as log:
            subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-O1', '-fsanitize=thread',
                            '-I'+str(ROOT/'plugin'), str(unit), '-framework', 'Foundation',
                            '-o', str(exe)], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
        for mode, options in [('first-use', []), ('retry', ['retry'])]:
            result = subprocess.run([str(exe.resolve()), *options], capture_output=True, text=True, timeout=20)
            log = result.stdout + result.stderr
            (args.output / (label + '-' + mode + '.private.log')).write_text(log)
            row = {'variant': label, 'mode': mode, 'exit_code': result.returncode,
                   'race_warnings': log.count('WARNING: ThreadSanitizer: data race'),
                   'production_helper_sha256': hashlib.sha256(function.encode()).hexdigest()}
            rows.append(row)
            if label == 'candidate' and (result.returncode or row['race_warnings']):
                raise SystemExit('FAIL: candidate publication/retry test; private logs retained')
    (args.output / 'results.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
