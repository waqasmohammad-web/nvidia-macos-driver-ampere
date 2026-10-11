#!/usr/bin/env python3
"""Extract and stress the production AIR unroll policy using ThreadSanitizer.

CPU-only; no Metal device/plugin load. Requires a new output directory. Optional
baseline reproduces the pre-fix race; lack of a baseline warning is not a pass
for absence of a race. Candidate warnings/nonzero exit always fail validation.
"""
import argparse, json, pathlib, subprocess
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--output', type=pathlib.Path, required=True)
p.add_argument('--baseline', action='store_true')
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
root = pathlib.Path(__file__).resolve().parents[2]
current = (root/'plugin/NVMTLLibraryLoad.m').read_text()
sources = [('candidate', current)]
if a.baseline:
    sources.insert(0, ('original', subprocess.check_output(
        ['git', 'show', '005d714:plugin/NVMTLLibraryLoad.m'], cwd=root, text=True)))
pre = '#import <Foundation/Foundation.h>\n#include <string.h>\n#include <assert.h>\n'
main = r'''
int main(int argc,char **argv){@autoreleasepool{
 if(argc>1)setenv("NVMTL_NO_AIR_UNROLL","1",1);else unsetenv("NVMTL_NO_AIR_UNROLL");
 NSData *needle=[@"air.simdgroup_matrix_8x8" dataUsingEncoding:NSUTF8StringEncoding];
 dispatch_apply(16,dispatch_get_global_queue(QOS_CLASS_DEFAULT,0),^(size_t worker){
  @autoreleasepool{ for(int i=0;i<100;i++) assert(nvmtl_air_unroll_wanted(needle)==(argc==1)); }
 });
 assert(!nvmtl_air_unroll_wanted([NSData data]));puts("PASS: concurrent policy and empty-input checks");return 0;
}}
'''
rows = []
for label, source in sources:
    fn = source[source.index('static BOOL nvmtl_air_unroll_wanted(NSData *air) {'):
                source.index('static NSString *nvmtl_air_in_memory')]
    unit = a.output/(label+'.m')
    unit.write_text(pre+fn+main)
    exe = a.output/label
    subprocess.run(['xcrun','clang','-fobjc-arc','-O1','-fsanitize=thread',
                    '-D_DARWIN_C_SOURCE',str(unit),'-framework','Foundation',
                    '-o',str(exe)], check=True, timeout=30)
    for mode, args in [('enabled',[]), ('disabled',['disable'])]:
        r = subprocess.run([str(exe.resolve()),*args],capture_output=True,text=True,timeout=15)
        log = r.stdout+r.stderr
        (a.output/(label+'-'+mode+'.log')).write_text(log)
        row = dict(variant=label, mode=mode, exit_code=r.returncode,
                   race_warnings=log.count('WARNING: ThreadSanitizer: data race'))
        rows.append(row)
        if label == 'candidate' and (r.returncode or row['race_warnings']):
            raise SystemExit('FAIL: candidate concurrent policy; retained private log')
(a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows,indent=2))
