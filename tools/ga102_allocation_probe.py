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


def validate_uploads(uploads):
    if len(uploads)!=33 or {(r['worker'],r['trial']) for r in uploads[:-1]}!={(w,t) for w in range(4) for t in range(8)}:raise ValueError('upload thread coverage')
    for r in uploads[:-1]:
        width=(64,128,256,512)[(r['worker']+r['trial'])%4]
        if r['width']!=width or r['height']!=128 or r['source_row_bytes']!=width*4+256 or r['bytes_verified']!=width*128*4 or any(type(r[k]) is not int or r[k]<=0 for k in ('encode_ns','completion_ns')):raise ValueError('upload coverage bytes/timing')
    for key,width,height in [('large',4096,2049),('small_after_large',256,128)]:
        r=uploads[-1][key]
        if r['width']!=width or r['height']!=height or r['source_row_bytes']!=width*4+256 or r['bytes_verified']!=width*height*4 or any(type(r[k]) is not int or r[k]<=0 for k in ('encode_ns','completion_ns')):raise ValueError('large upload coverage')


def validate_fragments(fragments):
    if len(fragments)!=3:raise ValueError('fragmentation sequence incomplete')
    for i,r in enumerate(fragments):
        if r['round']!=i or r['bytes_verified']!=31*(1<<20) or type(r['allocation_ns']) is not int or r['allocation_ns']<=0:raise ValueError('fragmentation workload incomplete')
        if r['filled']['buffer_live']!=r['before']['buffer_live']+31:raise ValueError('sentinels not held')
        if r['before']['buffer_live']!=r['after']['buffer_live']:raise ValueError('fragmentation retirement failed')
        if r['holes']['buffer_live']!=r['filled']['buffer_live']-3:raise ValueError('fragmentation holes not actually freed')
        if r['held']['buffer_live']!=r['holes']['buffer_live']+1:raise ValueError('joined buffer not live')
        if r['after']['free_failures']:raise ValueError('fragmentation free failure')
        fields={'requests','failures','request_ns','lock_wait_ns','growths','growth_ns','fragmented_growths'}
        for key in ('trace_before','trace_after'):
            if set(r[key])!=fields or any(type(v) is not int or v<0 for v in r[key].values()):raise ValueError('fragmentation trace incomplete')
        for k,v in r['trace_before'].items():
            if r['trace_after'][k]<v:raise ValueError('fragmentation telemetry regressed')
        if r['trace_after']['requests']!=r['trace_before']['requests']+1 or r['trace_after']['failures']!=r['trace_before']['failures']:raise ValueError('joined request not observed')


SURFACE_MODES=('queued','alias','alias_read','cross','partial','partial_alias','same','wait','cpu','abandoned','alpha','private')


def validate_surfaces(rows, backing):
    if backing not in ('family','private') or len(rows)!=len(SURFACE_MODES)*20:
        raise ValueError('surface coverage incomplete')
    expected=[(mode,frame) for mode in SURFACE_MODES for frame in range(20)]
    if [(r['mode'],r['frame']) for r in rows]!=expected:raise ValueError('surface sequence changed')
    for row in rows:
        actual=0 if row['mode']=='private' else 2 if backing=='family' else 1
        if type(row['backing']) is not int or row['backing']!=actual or row['checked_pixels']!=640*360 or type(row['max_error']) is not int or not 0<=row['max_error']<=1:
            raise ValueError('surface backing or pixel qualification failed')
        if row.get('cpu_checked_pixels')!=(0 if row['mode']=='private' else 640*360) or type(row.get('cpu_max_error')) is not int or not 0<=row['cpu_max_error']<=1:raise ValueError('CPU surface publication failed')
        times=[row[k] for k in ('frame_start_ns','encode_end_ns','commit_ns','scheduled_ns','completed_ns')]
        if any(type(t) is not int or t<=0 for t in times) or times!=sorted(times):
            raise ValueError('surface callback timeline invalid')
        gpu=[row[k] for k in ('gpu_start_s','gpu_end_s')]
        if any(type(t) not in (int,float) or not perf.math.isfinite(t) or t<=0 for t in gpu) or gpu[1]<gpu[0]:
            raise ValueError('surface GPU timestamps missing/invalid')
        for key in ('pool_before','pool_after'):
            if set(row[key])!={'requests','failures','request_ns','lock_wait_ns','growths','growth_ns','fragmented_growths'}:
                raise ValueError('pool trace fields missing')
            if any(type(v) is not int or v<0 for v in row[key].values()):raise ValueError('pool trace values invalid')
        if any(row['pool_after'][k]<v for k,v in row['pool_before'].items()):raise ValueError('pool trace regressed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('plugin','metallib','dependency-manifest','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--execute-reviewed',action='store_true')
    parser.add_argument('--surface-only',action='store_true',help='Owned offscreen surface/scheduling fixture; requires newly instrumented plugin')
    parser.add_argument('--surface-backing',choices=['family','private'],default='family')
    parser.add_argument('--upload-only',action='store_true',help='Physical threaded surface import and immediate application-reference release')
    parser.add_argument('--fragmentation-only',action='store_true',help='Joined-hole reuse with live sentinel GPU copies')
    parser.add_argument('--boundary-only',action='store_true',help='Verify alignment and pooled/dedicated allocation thresholds instead of stress waves')
    args=parser.parse_args()
    if sum((args.surface_only,args.boundary_only,args.fragmentation_only,args.upload_only))>1:parser.error('choose one workload')
    if sys.platform!='darwin' or not args.execute_reviewed:parser.error('Darwin and explicit reviewed execution required')
    if any(k.startswith('DYLD_') for k in os.environ):raise ValueError('inherited DYLD override')
    paths,hashes,proof=perf.artifact(args.plugin)
    if proof['performance'].get('pool_telemetry_disabled_control') and (args.surface_only or args.fragmentation_only):raise ValueError('this workload requires real pool telemetry')
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
    workload='upload_stress.swift' if args.upload_only else 'fragmentation_stress.swift' if args.fragmentation_only else 'surface_stress.swift' if args.surface_only else 'buffer_boundaries.swift' if args.boundary_only else 'allocation_stress.swift'
    source=source.replace(marker,(perf.ROOT/'tools/ga102_perf'/workload).read_text()+'\n'+marker)
    extra='"uploads":uploadRecords,' if args.upload_only else '"fragmentation":fragmentationRecords,' if args.fragmentation_only else '"surfaces":surfaceRecords,' if args.surface_only else '"boundaries":boundaryRecords,' if args.boundary_only else '"growth":growthRecords,"buffers":bufferRecords,'
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
        if args.surface_only:
            env['GA102_TEST_SURFACE_BACKING']=args.surface_backing
            if args.surface_backing=='private':env['GA102_TEST_SURFACE_PRIVATE']='1'
        logpath=args.output/(condition+'.private.log')
        with logpath.open('w') as log:rc=perf.run_owned([str(exe),str(args.metallib.resolve())],log,180 if args.surface_only or args.upload_only else 45,env)
        for path,digest in hashes.items():
            if perf.sha(path)!=digest:raise ValueError('artifact changed during execution')
        lines=logpath.read_text().splitlines()
        markers=('binding_verified: true','binding_namespace_verified: true','binding_translator_verified: true','binding_lowering_verified: true')
        results=[json.loads(x[8:]) for x in lines if x.startswith('result: ')]
        if rc or len(results)!=1 or any(lines.count(m)!=1 for m in markers) or any('duplicate' in x.lower() and 'class' in x.lower() for x in lines):raise ValueError('child or binding failed: '+str(logpath))
        result=results[0];differences=perf.validate_record(result,condition,{**paths,'cache':str(root)})
        perf.verify_inventory(result['provenance']['inventory'],approved)
        if args.surface_only:validate_surfaces(result['surfaces'],args.surface_backing)
        elif args.upload_only:
            validate_uploads(result['uploads'])
        elif args.fragmentation_only:
            validate_fragments(result['fragmentation'])
        elif args.boundary_only:
            boundaries=result['boundaries']
            if [r['bytes_verified'] for r in boundaries]!=[1,255,256,257,4096,65535,(4<<20)-1,4<<20,(4<<20)+1]:raise ValueError('boundary sizes incomplete')
            if any(r['before']['buffer_live']!=r['after']['buffer_live'] or r['after']['live_sets'] or r['after']['free_failures'] for r in boundaries):raise ValueError('boundary retirement failed')
        else:validate_stress(result)
        modules=perf.captures(root);perf.verify_cache(root,token)
        rows.append(dict(condition=condition,resources=result['resources'],growth=result.get('growth',[]),buffers=result.get('buffers',[]),boundaries=result.get('boundaries',[]),
                         uploads=result.get('uploads',[]),fragmentation=result.get('fragmentation',[]),surfaces=result.get('surfaces',[]),qualification_records=result['records'],differences=differences,validated_modules=sum(modules.values())))
        (root/'capture').rename(root/('capture-'+condition));(root/'capture').mkdir(mode=0o700)
    report=dict(status='PASS',mode='upload' if args.upload_only else 'fragmentation' if args.fragmentation_only else 'surface-'+args.surface_backing if args.surface_only else 'buffer-boundaries' if args.boundary_only else 'allocation-growth',source_commit=proof['source_commit'],source_tree=proof['source_tree'],
                pool_telemetry_enabled=not proof['performance'].get('pool_telemetry_disabled_control',False),artifact_hashes={k:perf.sha(paths[k]) for k in ('plugin','translator','icd','llvm')},
                probe_sha256=perf.sha(exe),swift_sha256=perf.sha(swift),rows=rows,
                limits=['Offscreen only, no desktop claim.']+(['Threaded whole-image import and application-reference release; retention cap controlled separately by sanitizer tests.'] if args.upload_only else ['31 MiB exact copies per round with live sentinels; no full randomized physical overlap coverage.'] if args.fragmentation_only else ['240 GPU/CPU pixel-checked 640x360 frames per process; callback/GPU completion is not presentation.','Source-prepared until actual Apple compilation and physical qualification.'] if args.surface_only else ['Nine exact buffer copy sizes; no descriptor growth in this mode.'] if args.boundary_only else
                    ['Each stress render checks its final 1024 pixels; each buffer wave verifies all 64 MiB copied.','Physical growth beyond 256 sets; not saturation of the 262144-set ceiling.']))
    (args.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: physical threaded upload/lifetime and large import' if args.upload_only else 'PASS: physical joined-hole and live-sentinel copies' if args.fragmentation_only else 'PASS: physical offscreen surface correctness and scheduling fixture' if args.surface_only else 'PASS: physical buffer boundaries/retirement' if args.boundary_only else 'PASS: physical descriptor growth/reuse/retirement and 3 x64 MiB verified buffer copy waves per process')


if __name__=='__main__':main()
