#!/usr/bin/env python3
"""Compile the patched NVK config helper against an owned fixture, without GPU APIs."""
import argparse
import hashlib
import json
from pathlib import Path
import os
import shlex
import sys
import subprocess

ROOT = Path(__file__).resolve().parents[1]

PREAMBLE = r'''
#include <stdio.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <stdatomic.h>
#include <unistd.h>
static _Atomic unsigned reads, failures;
static size_t delayed_read(void *p, size_t s, size_t n, FILE *f) {
    atomic_fetch_add(&reads, 1); usleep(50000); return fread(p,s,n,f);
}
#define fread delayed_read
'''
MAIN = r'''
#undef fread
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition = PTHREAD_COND_INITIALIZER;
static unsigned ready, start;
static void *worker(void *argument) {
    unsigned index = (unsigned)(uintptr_t)argument;
    const char *key = index % 2 ? "GA102_ALPHA" : "GA102_BETA";
    const char *expected = index % 2 ? "alpha" : "beta";
    pthread_mutex_lock(&lock); ready++; pthread_cond_broadcast(&condition);
    while (!start) pthread_cond_wait(&condition,&lock);
    pthread_mutex_unlock(&lock);
    for (unsigned i=0;i<100;i++) {
        const char *value = nvmtl_cfg_getenv(key); usleep(100);
        if (!value || strcmp(value,expected)) atomic_fetch_add(&failures,1);
    }
    return NULL;
}
int main(int argc, char **argv) {
    if (argc<2) return 2;
    if (!strcmp(argv[1],"parser")) {
        const char *a=nvmtl_cfg_getenv("GA102_COMMENT");
        const char *b=nvmtl_cfg_getenv("GA102_SUFFIX");
        if (!a || strcmp(a,"right") || !b || strcmp(b,"exact")) return 1;
        setenv("GA102_COMMENT","environment",1);
        if (strcmp(nvmtl_cfg_getenv("GA102_COMMENT"),"environment")) return 1;
        if (nvrm610_on("TEST_SWITCH")) return 1;
        setenv("TEST_SWITCH","1",1);
        if (nvrm610_on("TEST_SWITCH")) return 1;
        setenv("NVRM_610_TEST_SWITCH","1",1);
        if (!nvrm610_on("TEST_SWITCH")) return 1;
        setenv("NVRM_610_TEST_SWITCH","0",1);
        if (nvrm610_on("TEST_SWITCH")) return 1;
        puts("PASS: exact line lookup after comment/suffix matches; environment precedence");
        return 0;
    }
    if (!strcmp(argv[1],"ring")) nvmtl_cfg_getenv("GA102_ALPHA");
    pthread_t threads[16];
    for (unsigned i=0;i<16;i++) if (pthread_create(&threads[i],NULL,worker,(void *)(uintptr_t)i)) return 2;
    pthread_mutex_lock(&lock);
    while (ready<16) pthread_cond_wait(&condition,&lock);
    start=1; pthread_cond_broadcast(&condition); pthread_mutex_unlock(&lock);
    for (unsigned i=0;i<16;i++) pthread_join(threads[i],NULL);
    printf("reads=%u invalid_values=%u\n",atomic_load(&reads),atomic_load(&failures));
    return atomic_load(&reads)!=1 || atomic_load(&failures)!=0;
}
'''


def patched_file(patch, path):
    section = patch.split('+++ b/'+path+'\t', 1)[1]
    section = section.split('\ndiff ', 1)[0]
    return '\n'.join(line[1:] for line in section.splitlines()
                     if line.startswith('+') and not line.startswith('+++')) + '\n'


def header(patch):
    return patched_file(patch, 'src/nouveau/vulkan/nvmtl_cfg.h')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--before-fix', action='store_true')
    parser.add_argument('--cc', default=os.environ.get('CC', 'xcrun clang' if sys.platform == 'darwin' else 'cc'))
    parser.add_argument('--sanitizer', choices=['thread', 'address,undefined', 'none'], default='thread')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    fixture = args.output/'owned.conf'
    fixture.write_text('# GA102_COMMENT=wrong\nGA102_COMMENT=right\nOTHER_GA102_SUFFIX=bad\nGA102_SUFFIX=exact\nGA102_ALPHA=alpha\nGA102_BETA=beta\n# TEST_SWITCH=1\nTEST_SWITCH=0\n')
    sources = [('original' if args.before_fix else 'candidate', (ROOT/'nvk/nvk-macos.patch').read_text())]
    if args.baseline:
        sources.insert(0, ('original', subprocess.check_output(['git','show','8c54ce4:nvk/nvk-macos.patch'],cwd=ROOT,text=True)))
    rows=[]
    for label, patch in sources:
        production=header(patch)
        owned=production.replace('/Library/GPUBundles/nvmtl/nvrm610.conf',json.dumps(str(fixture.resolve()))[1:-1])
        wrapper_source=patched_file(patch,'src/nouveau/vulkan/nvkmd/nvrm/nvkmd_nvrm.h')
        begin=wrapper_source.index('static inline bool\nnvrm610_on(')
        wrapper=wrapper_source[begin:wrapper_source.index('static inline void\nnvkmd_nvrm_dev_api_ctl',begin)]
        wrapper=wrapper.replace('/Library/GPUBundles/nvmtl/nvrm610.conf',json.dumps(str(fixture.resolve()))[1:-1])
        unit=args.output/(label+'.c'); unit.write_text(PREAMBLE+'\n#include <stdint.h>\n'+owned+wrapper+MAIN)
        executable=args.output/label
        with (args.output/(label+'-compile.private.log')).open('w') as log:
            flags = [] if args.sanitizer == 'none' else ['-fsanitize='+args.sanitizer]
            subprocess.run(shlex.split(args.cc)+['-std=c11','-D_DEFAULT_SOURCE','-O1']+flags+['-pthread',str(unit),'-o',str(executable)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=30)
        for mode in ['parser','first-use','ring']:
            result=subprocess.run([str(executable.resolve()),mode],capture_output=True,text=True,timeout=20)
            log=result.stdout+result.stderr;(args.output/(label+'-'+mode+'.private.log')).write_text(log)
            row={'variant':label,'sanitizer':args.sanitizer,'mode':mode,'exit_code':result.returncode,'race_warnings':log.count('WARNING: ThreadSanitizer: data race'),'source_sha256':hashlib.sha256(production.encode()).hexdigest()};rows.append(row)
            if label=='candidate' and (result.returncode or row['race_warnings']):raise SystemExit('FAIL: candidate config helper; private logs retained')
    (args.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows,indent=2))


if __name__ == '__main__':
    main()
