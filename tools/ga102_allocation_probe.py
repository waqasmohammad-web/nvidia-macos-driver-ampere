#!/usr/bin/env python3
"""Owned GPU pool growth and resource-lifetime qualification. Explicit launch only."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
try:
    from . import ga102_graphics_perf as perf
except ImportError:
    import ga102_graphics_perf as perf


def validate_stress(result):
    growth=result['growth'];buffers=result['buffers']
    if len(growth)!=3 or len(buffers)!=3: raise ValueError('stress sequence incomplete')
    for i,row in enumerate(growth):
        if row['round']!=i or row['draws']!=1536 or row['checked_pixels']!=1024: raise ValueError('growth workload changed')
        held,after=row['held'],row['after']
        if held['live_sets']<1536 or held['pools']<2 or held['reserved_sets']<=256: raise ValueError('physical descriptor growth not exercised')
        if after['live_sets'] or after['allocated_sets']!=after['freed_sets'] or after['free_failures']: raise ValueError('descriptor retirement failed')
        if i and held['pools']!=row['before']['pools']: raise ValueError('repeated workload expanded instead of reusing pools')
        if held['reserved_sets']!=256+(held['pools']-1)*4096: raise ValueError('unexpected pool capacities')
        d=perf.delta(dict(before=row['metrics_before'],after=row['metrics_after']))
        if any(d[e]['count'] for e in ('sampler_abi','vk_pipeline','variant_build')) or d['local_hit']['count']!=1536:
            raise ValueError('growth draw recompiled or did not execute every sampler bind')
    for i,row in enumerate(buffers):
        if row['round']!=i or row['buffer_count']!=128 or row['bytes_verified']!=64*(1<<20) or len(row['allocation_samples_ns'])!=128:
            raise ValueError('buffer workload changed')
        if row['held']['buffer_live']<row['before']['buffer_live']+128: raise ValueError('buffers not held concurrently')
        if row['held']['host_pool_bytes']<=row['before']['host_pool_bytes']: raise ValueError('host allocation growth not exercised')
        if row['after']['buffer_live']!=row['before']['buffer_live']: raise ValueError('completed buffer resources retained')
        if row['after']['host_pool_bytes']>(64<<20)+row['after']['dummy_heap_bytes']: raise ValueError('empty pool trimming failed')
        if row['after']['free_failures']: raise ValueError('Vulkan free failure')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('plugin','metallib','dependency-manifest','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--execute-reviewed',action='store_true')
    parser.add_argument('--boundary-only',action='store_true',help='Verify alignment and pooled/dedicated allocation thresholds instead of stress waves')
    args=parser.parse_args()
    if sys.platform!='darwin' or not args.execute_reviewed:parser.error('Darwin and explicit reviewed execution required')
    if any(k.startswith('DYLD_') for k in os.environ):raise ValueError('inherited DYLD override')
    paths,hashes,proof=perf.artifact(args.plugin)
    fixture=json.loads(args.metallib.with_name('fixture-proof.json').read_text())
    if fixture['metallib_sha256']!=perf.sha(args.metallib) or fixture['source_sha256']!=perf.sha(perf.FIXTURE):raise ValueError('fixture mismatch')
    manifest=json.loads(args.dependency_manifest.read_text())
    if manifest.get('reviewed') is not True:raise ValueError('reviewed closure required')
    for path,digest in manifest['files'].items():
        if str(Path(path).resolve())!=path or perf.sha(path)!=digest:raise ValueError('dependency mismatch')
        if path in hashes and hashes[path]!=digest:raise ValueError('conflicting dependency hash')
        hashes[path]=digest
    hashes[str(args.dependency_manifest.resolve())]=perf.sha(args.dependency_manifest)
    hashes[str(args.metallib.resolve())]=perf.sha(args.metallib)
    args.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    source=(perf.ROOT/'tools/ga102_perf/graphics.swift').read_text()
    marker='guard let provenanceData='
    if source.count(marker)!=1:raise ValueError('stress insertion site changed')
    workload='buffer_boundaries.swift' if args.boundary_only else 'allocation_stress.swift'
    source=source.replace(marker,(perf.ROOT/'tools/ga102_perf'/workload).read_text()+'\n'+marker)
    extra='"boundaries":boundaryRecords,' if args.boundary_only else '"growth":growthRecords,"buffers":bufferRecords,'
    source=source.replace('"resources":resources(),','"resources":resources(),'+extra)
    swift=args.output/'allocation.swift';swift.write_text(source)
    obj=args.output/'binding.o';exe=args.output/'allocation-probe'
    commands=[['xcrun','clang','-arch','x86_64','-fobjc-arc','-O1','-Wall','-Wextra','-Werror','-DGA102_BINDING_ONLY=1','-DGA102_PERFORMANCE=1','-c',str(perf.ROOT/'tools/ga102_isolated_plugin_probe.m'),'-o',str(obj)],
              ['xcrun','swiftc','-O','-module-cache-path',str(args.output/'modules'),str(swift),str(obj),'-framework','IOKit','-o',str(exe)]]
    for i,cmd in enumerate(commands):
        with (args.output/f'compile-{i}.private.log').open('w') as log:
            if perf.run_owned(cmd,log,90):raise ValueError('stress probe compilation failed')
    (args.output/'commands.private.json').write_text(json.dumps(commands,indent=2)+'\n')
    hashes[str(exe.resolve())]=perf.sha(exe);approved=set(hashes)
    root,token=perf.new_cache(args.output);rows=[]
    for condition in ('cold','reuse'):
        perf.verify_cache(root,token)
        for path,digest in hashes.items():
            if perf.sha(path)!=digest:raise ValueError('artifact changed')
        env={k:v for k,v in os.environ.items() if not k.startswith(('GA102_','MESA_','XDG_CACHE_','NVMTL_','NVK_','NVRM_','NAK_','VK_'))}
        env.update(GA102_PLUGIN_IMAGE=paths['plugin'],GA102_PLUGIN_NAMESPACE='NVMTLGA102_',GA102_PLUGIN_TRANSLATOR=paths['translator'],
                   GA102_PLUGIN_LOWER_PROBE='1',GA102_TEST_ICD=paths['icd'],GA102_TEST_LLVM=paths['llvm'],GA102_TEST_CACHE=str(root),
                   GA102_TEST_TOKEN=token,GA102_TEST_CAPTURE='1',GA102_TEST_SAMPLER_FIRST='nearest')
        logpath=args.output/(condition+'.private.log')
        with logpath.open('w') as log:rc=perf.run_owned([str(exe),str(args.metallib.resolve())],log,45,env)
        for path,digest in hashes.items():
            if perf.sha(path)!=digest:raise ValueError('artifact changed during execution')
        lines=logpath.read_text().splitlines()
        markers=('binding_verified: true','binding_namespace_verified: true','binding_translator_verified: true','binding_lowering_verified: true')
        results=[json.loads(x[8:]) for x in lines if x.startswith('result: ')]
        if rc or len(results)!=1 or any(lines.count(m)!=1 for m in markers) or any('duplicate' in x.lower() and 'class' in x.lower() for x in lines):raise ValueError('child or binding failed: '+str(logpath))
        result=results[0];differences=perf.validate_record(result,condition,{**paths,'cache':str(root)})
        perf.verify_inventory(result['provenance']['inventory'],approved)
        if args.boundary_only:
            boundaries=result['boundaries']
            if [r['bytes_verified'] for r in boundaries]!=[1,255,256,257,4096,65535,(4<<20)-1,4<<20,(4<<20)+1]:raise ValueError('boundary sizes incomplete')
            if any(r['before']['buffer_live']!=r['after']['buffer_live'] or r['after']['live_sets'] or r['after']['free_failures'] for r in boundaries):raise ValueError('boundary retirement failed')
        else:validate_stress(result)
        modules=perf.captures(root);perf.verify_cache(root,token)
        rows.append(dict(condition=condition,resources=result['resources'],growth=result.get('growth',[]),buffers=result.get('buffers',[]),boundaries=result.get('boundaries',[]),
                         qualification_records=result['records'],differences=differences,validated_modules=sum(modules.values())))
        (root/'capture').rename(root/('capture-'+condition));(root/'capture').mkdir(mode=0o700)
    report=dict(status='PASS',mode='buffer-boundaries' if args.boundary_only else 'allocation-growth',source_commit=proof['source_commit'],source_tree=proof['source_tree'],
                artifact_hashes={k:perf.sha(paths[k]) for k in ('plugin','translator','icd','llvm')},
                probe_sha256=perf.sha(exe),swift_sha256=perf.sha(swift),rows=rows,
                limits=['Offscreen only, no desktop claim.']+(['Nine exact buffer copy sizes; no descriptor growth in this mode.'] if args.boundary_only else
                    ['Each stress render checks its final 1024 pixels; each buffer wave verifies all 64 MiB copied.','Physical growth beyond 256 sets; not saturation of the 262144-set ceiling.']))
    (args.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: physical buffer boundaries/retirement' if args.boundary_only else 'PASS: physical descriptor growth/reuse/retirement and 3 x64 MiB verified buffer copy waves per process')


if __name__=='__main__':main()
