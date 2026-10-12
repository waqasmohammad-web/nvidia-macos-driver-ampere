import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from build import build_isolated_plugin as builder
from build.ga102_perf_instrumentation import instrument, once
from tools import ga102_graphics_perf as perf


class GraphicsPolicyTests(unittest.TestCase):
    def test_owned_cache_rejects_tokens_permissions_and_symlinks(self):
        with tempfile.TemporaryDirectory() as parent:
            root,token=perf.new_cache(parent)
            perf.verify_cache(root,token)
            with self.assertRaises(ValueError): perf.verify_cache(root,'0'*64)
            (root/'air').chmod(0o755)
            with self.assertRaises(ValueError): perf.verify_cache(root,token)
            (root/'air').chmod(0o700)
            (root/'air'/'escape').symlink_to(parent)
            with self.assertRaises(ValueError): perf.verify_cache(root,token)

    def test_real_portable_C_cache_metrics_and_capture_controls(self):
        with tempfile.TemporaryDirectory() as parent:
            base=Path(parent); root,token=perf.new_cache(base)
            unit=base/'proof.c'
            unit.write_text('#include "'+str(perf.ROOT/'tools/ga102_perf/metrics.h')+'"\n'+r'''
#include <pthread.h>
static void *worker(void *p) { (void)p; for(int i=0;i<1000;++i)ga102_hit(GA102_LOCAL_HIT); return NULL; }
int main(void) {
    ga102_owned_air(); ga102_owned_mesa();
    uint64_t t=ga102_tick(); ga102_record(GA102_VK_PIPELINE,ga102_tick()-t,0);
    pthread_t threads[4];
    for(int i=0;i<4;++i)if(pthread_create(&threads[i],NULL,worker,NULL))return 2;
    for(int i=0;i<4;++i)if(pthread_join(threads[i],NULL))return 3;
    // Exercises capture I/O only; deliberately not a shader/validator fixture.
    uint8_t bytes[20]={0}; ga102_capture(GA102_RUST,bytes,sizeof bytes);
    puts(ga102_metrics_json()); return 0;
}
''')
            exe=base/'proof'
            subprocess.run(['cc','-std=c11','-D_XOPEN_SOURCE=700','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined',str(unit),'-o',str(exe)],check=True,capture_output=True)
            env={**os.environ,'GA102_TEST_CACHE':str(root),'GA102_TEST_TOKEN':token}
            env.pop('MESA_SHADER_CACHE_DISABLE',None)
            output=subprocess.run([str(exe)],env=env,capture_output=True,text=True,check=True)
            m=json.loads(output.stdout); perf.metrics(m)
            self.assertEqual(m['local_hit']['count'],4000)
            self.assertEqual(m['vk_pipeline']['count'],1)
            self.assertEqual(list((root/'capture').iterdir()),[])
            captured=subprocess.run([str(exe)],env={**env,'GA102_TEST_CAPTURE':'1'},capture_output=True,text=True)
            self.assertEqual(captured.returncode,0,captured.stderr)
            self.assertEqual(len(list((root/'capture').glob('*.spv'))),1)
            for change in ({'GA102_TEST_TOKEN':'1'*64},{'MESA_SHADER_CACHE_DISABLE':'true'},{'GA102_TEST_CACHE':str(base)},{'NVMTL_VENDOR_COMPILER':'1'}):
                out=subprocess.run([str(exe)],env={**env,**change},capture_output=True,text=True)
                self.assertNotEqual(out.returncode,0)
                self.assertIn('GA102 isolation failure',out.stderr)
            (root/'spvcache').rmdir(); (root/'spvcache').symlink_to(base)
            out=subprocess.run([str(exe)],env=env,capture_output=True,text=True)
            self.assertNotEqual(out.returncode,0); self.assertIn('GA102 isolation failure',out.stderr)

    def test_prepare_only_transforms_actual_sites_without_changing_production(self):
        originals={p.name:perf.sha(p) for p in (perf.ROOT/'plugin').iterdir() if p.is_file()}
        with tempfile.TemporaryDirectory() as parent:
            out=Path(parent)/'snapshot'
            with patch('sys.argv',['builder','--prepare-only','--graphics-performance','--output',str(out),'--translator','/owned/translator.dylib','--icd','/retained/nvk.dylib','--air-runtime','/retained/runtime']):
                builder.main()
            proof=json.loads((out/'preparation-proof.json').read_text())
            self.assertIsNone(proof['binary_sha256']); self.assertFalse(proof['runtime_executed'])
            source=out/'source'; library=(source/'NVMTLLibraryLoad.m').read_text(); objects=(source/'NVMTLObjects.m').read_text(); vk=(source/'nvmtl_vk.c').read_text()
            cache_function=library.split('static NSString *nvmtl_aircache_dir(void) {')[1].split('static _Atomic unsigned long gSpvHit')[0]
            self.assertIn('ga102_owned_air()',cache_function)
            self.assertNotIn('NVMTL_AIRCACHE',cache_function)
            # The actual production environment/config constructor is byte-identical
            # after namespace conversion; this profile does not edit its safety policy.
            original=(perf.ROOT/'plugin/NVMTLObjects.m').read_text()
            def constructor(s): return s.split('__attribute__((constructor)) static void nvmtl_conf_knobs(void)')[1].split('static int nvmtl_dontcare_clears')[0]
            self.assertEqual(constructor(original),constructor(objects))
            self.assertIn('ga102_hit(selected ? GA102_LOCAL_HIT : GA102_LOCAL_MISS)',objects)
            self.assertIn('ga102_hit(selected ? GA102_DEVICE_HIT : GA102_DEVICE_MISS)',objects)
            self.assertIn('ga102_actual_sampler(',library)
            self.assertIn('ga102_record(GA102_VK_PIPELINE',vk)
            self.assertIn('loader fallback prohibited',vk)
            self.assertIn('in-memory AIR extraction failed; fallback prohibited',library)
            with self.assertRaises(ValueError): instrument(source,Path('/x'),Path('/y'))
        self.assertEqual(originals,{p.name:perf.sha(p) for p in (perf.ROOT/'plugin').iterdir() if p.is_file()})
        for text in ('absent','site site'):
            with self.assertRaises(ValueError): once(text,'site','new')

    @staticmethod
    def fixture(condition='cold'):
        def blank():return {k:dict(count=0,ns=0,failures=0) for k in perf.EVENTS}
        state=blank(); rows=[]
        for label in perf.LABELS:
            before=copy.deepcopy(state); counts={}
            if label=='library':counts={'air_miss':1,'air_extract':1} if condition=='cold' else {'index_disk_hit':1}
            elif label.startswith('pipeline-'):
                counts={'vk_pipeline':1}
                if label=='pipeline-initial':counts.update({'rust':2,'spv_miss':2} if condition=='cold' else {'spv_hit':2})
            else:
                counts={'sampler_bind':1,'local_lookup':1,'local_miss':1,'device_lookup':1,'device_miss':1,'variant_build':1,'sampler_abi':1,'vk_pipeline':1}
                if label.endswith('local-hit'):counts={'sampler_bind':1,'local_lookup':1,'local_hit':1}
                elif label.endswith('device-hit'):counts={'sampler_bind':1,'local_lookup':1,'local_miss':1,'device_lookup':1,'device_hit':1}
            for k,n in counts.items():state[k]['count']+=n; state[k]['ns']+=n*100
            row=dict(label=label,before=before,after=copy.deepcopy(state),wall_ns=100)
            if not label.startswith('pipeline') and label!='library':
                f=0 if label.startswith('nearest') else 1
                row.update(filter=f,checked_pixels=1024,max_error=0,center_rgba=[64,96,80,255] if f==0 else [56,104,80,255])
            rows.append(row)
        paths=dict(translator='/owned/xlate',icd='/retained/icd',llvm='/retained/llvm',plugin='/owned/plugin',cache='/owned/cache')
        images=[paths['translator']]*3+[paths['icd']]*2+[paths['llvm'] if condition=='cold' else None]
        result=dict(schema_version=1,records=rows,final_metrics=state,
                    provenance=dict(images=images,inventory=images+[paths['plugin']],cache=paths['cache'],mesa='/owned/cache/mesa',namespace_verified=True))
        return result,paths

    def test_acceptance_requires_actual_branches_pixels_images_and_cache_conditions(self):
        for condition in ('cold','reuse'):
            result,paths=self.fixture(condition); perf.validate_record(result,condition,paths)
            mutations=[lambda r:r['records'][2]['after']['sampler_abi'].update(count=0),
                       lambda r:r['records'][3]['after']['local_hit'].update(count=0),
                       lambda r:r['records'][7]['after']['device_hit'].update(count=0),
                       lambda r:r['records'][2].update(center_rgba=[0,0,0,0]),
                       lambda r:r['records'][2].update(max_error=3),
                       lambda r:r['provenance']['images'].__setitem__(1,'/installed/xlate'),
                       lambda r:r['provenance'].update(cache='/driver/cache'),
                       lambda r:r['records'][2]['after']['vk_pipeline'].update(failures=1),
                       lambda r:r['final_metrics']['vk_error'].update(count=1,failures=1),
                       lambda r:r['records'][2].update(encode_ns=float('nan')),
                       lambda r:r['records'].pop()]
            for mutate in mutations:
                changed=copy.deepcopy(result);mutate(changed)
                with self.assertRaises(ValueError):perf.validate_record(changed,condition,paths)
            with self.assertRaises(ValueError):perf.validate_record(result,'reuse' if condition=='cold' else 'cold',paths)

    def test_shader_is_runtime_bound_and_expected_filters_differ(self):
        shader=perf.FIXTURE.read_text()
        self.assertIn('[[sampler(3)]]',shader); self.assertNotIn('constexpr',shader)
        self.assertIn('image.sample(bound',shader)
        # Independent bilinear interpolation oracle, not just the fixture constants.
        corners=[(1,3),(2,3),(1,4),(2,4)]; weights=[.1875,.5625,.0625,.1875]
        result=[round(sum(w*(32*x if c==0 else 32*y if c==1 else 16*(x+y)) for (x,y),w in zip(corners,weights))) for c in range(3)]
        self.assertEqual(result,[56,104,80]); self.assertNotEqual(result,[64,96,80])

    def test_unknown_non_system_dependency_is_not_auto_accepted(self):
        perf.verify_inventory(['/usr/lib/libSystem.B.dylib','/owned/nvk'],{'/owned/nvk'})
        with self.assertRaises(ValueError):perf.verify_inventory(['/unexpected/driver'],{'/owned/nvk'})

    def test_linux_refuses_darwin_commands_before_execution(self):
        with patch('sys.platform','linux'),patch('sys.argv',['runner','prepare-metallib','--output','/not-created']),patch.object(perf,'prepare_metallib') as execute:
            with self.assertRaises(SystemExit):perf.main()
            execute.assert_not_called()

if __name__=='__main__':unittest.main()
