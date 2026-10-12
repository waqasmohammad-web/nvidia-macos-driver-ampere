"""Opt-in transformation of an owned namespace snapshot, never production files."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('performance instrumentation site changed: ' + old[:90])
    return text.replace(old, new)


def instrument(source, translator, icd):
    header = ROOT / 'tools/ga102_perf/metrics.h'
    (source/'ga102_perf_metrics.h').write_bytes(header.read_bytes())
    unit = source/'NVMTLDevice.m'
    unit.write_text(once(unit.read_text(), '#include <time.h>', '#include <time.h>\n#include "ga102_perf_metrics.h"'))
    lib = source/'NVMTLLibraryLoad.m'
    s = lib.read_text()
    start = s.index('static NSString *nvmtl_aircache_dir(void) {')
    end = s.index('\nstatic _Atomic unsigned long gSpvHit', start)
    s = s[:start] + '''static NSString *nvmtl_aircache_dir(void) {
    return @(ga102_owned_air());
}
''' + s[end:]
    # No installed translator fallback, even when the bundled path is missing.
    old = 'const char *xpath = bundled && access(bundled.fileSystemRepresentation,R_OK)==0 ? bundled.fileSystemRepresentation : NVMTL_XLATE_LIB;'
    s = once(s, old, 'const char *xpath = ' + json.dumps(str(translator)) + ';')
    # Existing ordinary/lowering counters remain; add separately timed actual calls.
    for name, event, args in [
        ('Translate', 'RUST', 'll, stage, out, length, err, capacity'),
        ('Lower', 'LOWER', 'data, size, out, length, err, capacity'),
        ('LowerEx', 'LOWER', 'data, size, flags, out, length, info, err, capacity')]:
        old = f'return gGA102{name}Implementation({args});'
        s = once(s, old, f'uint64_t t = ga102_tick(); int rc = gGA102{name}Implementation({args});\n    ga102_record(GA102_{event}, ga102_tick()-t, rc != 0);\n    if (!rc) ga102_capture(GA102_{event}, *out, *length); return rc;')
    # ABI wrappers preserve the exact argument and return types.
    variants = [
        ('sampler', 'nvmtl_sampler_fn', 'SAMPLER_ABI',
         'const char *ll, const char *stage, const char *json, uint8_t **out, size_t *len, char *err, size_t cap',
         'll, stage, json, out, len, err, cap', 'nvmtl_translate_samplers'),
        ('fc', 'nvmtl_fc_fn', 'RUST',
         'const char *ll, const char *stage, const uint32_t *idx, const uint32_t *sizes, const uint8_t *const *payloads, size_t n, uint8_t **out, size_t *len, char *err, size_t cap',
         'll, stage, idx, sizes, payloads, n, out, len, err, cap', 'nvmtl_translate_fc'),
        ('refl', 'nvmtl_refl_fn', 'REFLECT',
         'const char *ll, const char *stage, uint8_t **out, size_t *len, char *err, size_t cap',
         'll, stage, out, len, err, cap', 'nvmtl_reflect'),
        ('refl_fc', 'nvmtl_refl_fc_fn', 'REFLECT',
         'const char *ll, const char *stage, const uint32_t *idx, const uint32_t *sizes, const uint8_t **payloads, size_t n, uint8_t **out, size_t *len, char *err, size_t cap',
         'll, stage, idx, sizes, payloads, n, out, len, err, cap', 'nvmtl_reflect_fc')]
    for name, typedef, event, params, args, symbol in variants:
        decl = f'static {typedef} xlate_{name};'
        wrapper = f'''
static {typedef} ga102_actual_{name};
static int ga102_timed_{name}({params}) {{
    uint64_t t=ga102_tick(); int rc=ga102_actual_{name}({args});
    ga102_record(GA102_{event},ga102_tick()-t,rc != 0);
    {'if (!rc) ga102_capture(GA102_'+event+', *out, *len);' if event != 'REFLECT' else ''} return rc;
}}
'''
        s = once(s, decl, decl + wrapper)
        assignment = f'xlate_{name} = ({typedef})dlsym(h, "{symbol}");'
        s = once(s, assignment, f'ga102_actual_{name} = ({typedef})dlsym(h, "{symbol}");\n        xlate_{name} = ga102_actual_{name} ? ga102_timed_{name} : NULL;')
    site = 'static NSString *nvmtl_air_to_text(NSData *air) {'
    wrapper = '''static NSString *ga102_air_extract(NSData *air) {
    uint64_t t=ga102_tick(); NSString *result=nvmtl_air_in_memory(air);
    ga102_record(GA102_AIR_EXTRACT,ga102_tick()-t,!result.length); return result;
}
'''
    s = once(s, site, wrapper + site)
    s = once(s, 'NSString *memoryIR = nvmtl_air_in_memory(air);', 'NSString *memoryIR = ga102_air_extract(air);\n    if (!memoryIR.length) ga102_stop("in-memory AIR extraction failed; fallback prohibited");')
    s = once(s, 'gAirHit++; gAirMemoryHit++; return hit;', 'gAirHit++; gAirMemoryHit++; ga102_hit(GA102_AIR_MEMORY_HIT); return hit;')
    s = once(s, 'gAirHit++; return hit;', 'gAirHit++; ga102_hit(GA102_AIR_DISK_HIT); return hit;')
    s = once(s, '    gAirMiss++;', '    gAirMiss++; ga102_hit(GA102_AIR_MISS);')
    s = once(s, 'if (hit) { gSpvHit++;', 'if (hit) { ga102_hit(GA102_SPV_HIT); gSpvHit++;')
    s = once(s, '            gSpvMiss++;', '            gSpvMiss++; ga102_hit(GA102_SPV_MISS);')
    s = once(s, 'nvlog("library index: DISK hit bytes=', 'ga102_hit(GA102_INDEX_DISK_HIT);\n            nvlog("library index: DISK hit bytes=')
    lib.write_text(s)
    objects = source/'NVMTLObjects.m'
    s = objects.read_text()
    s = once(s, '- (BOOL)nvmtlBindSamplerPipeline {', '''- (BOOL)nvmtlBindSamplerPipeline {
    uint64_t t=ga102_tick(); BOOL ok=[self ga102MeasuredSamplerBind];
    ga102_record(GA102_SAMPLER_BIND,ga102_tick()-t,!ok); return ok;
}
- (BOOL)ga102MeasuredSamplerBind {''')
    s = once(s, '            id cached=_ps->_samplerVariants[key];', '            uint64_t localT=ga102_tick(); id cached=_ps->_samplerVariants[key];\n            ga102_record(GA102_LOCAL_LOOKUP,ga102_tick()-localT,0);')
    # Event increments sit on the actual production branches, under existing locks.
    s = once(s, '            selected=cached;', '            selected=cached;\n            ga102_hit(selected ? GA102_LOCAL_HIT : GA102_LOCAL_MISS);')
    s = once(s, 'NSString *gk=nvmtl_sampvar_key(_ps->_descriptor,vf,ff,key); selected=nvmtl_sampvar_get(gk);', 'NSString *gk=nvmtl_sampvar_key(_ps->_descriptor,vf,ff,key); uint64_t deviceT=ga102_tick(); selected=nvmtl_sampvar_get(gk);\n                ga102_record(GA102_DEVICE_LOOKUP,ga102_tick()-deviceT,0);\n                ga102_hit(selected ? GA102_DEVICE_HIT : GA102_DEVICE_MISS);')
    s = once(s, 'else nvmtl_sampvar_put(gk,selected,vf,ff);', 'else { nvmtl_sampvar_put(gk,selected,vf,ff); ga102_hit(GA102_VARIANT_BUILD); }')
    objects.write_text(s)
    vk = source/'nvmtl_vk.c'
    s = vk.read_text()
    s = once(s, '    (void)type; (void)user;', '    (void)type; (void)user;\n    if (sev & VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT) ga102_record(GA102_VK_ERROR,0,1);')
    start = s.index('static inline const char *nvmtl_icd_lib_path(void) {')
    end = s.index('\n#define NVMTL_ICD_LIB', start)
    s = s[:start] + 'static inline const char *nvmtl_icd_lib_path(void) { return ' + json.dumps(str(icd)) + '; }\n' + s[end:]
    s = once(s, '    if (!pvkGetInstanceProcAddr) {\n        if (!getenv("VK_ICD_FILENAMES"))', '    if (!pvkGetInstanceProcAddr) ga102_stop("explicit ICD failed; loader fallback prohibited");\n    if (!pvkGetInstanceProcAddr) {\n        if (!getenv("VK_ICD_FILENAMES"))')
    s = once(s, '    if (g_state) return g_state == 1 ? 0 : -1;\n    g_state = -1;', '    if (g_state) return g_state == 1 ? 0 : -1;\n    g_state = -1;\n    ga102_owned_mesa();')
    call = 'VkResult result = pvkCreateGraphicsPipelines(dev, cache, count, info, allocator, &handle);'
    s = once(s, call, 'uint64_t t=ga102_tick();\n    '+call+'\n    ga102_record(GA102_VK_PIPELINE,ga102_tick()-t,result != VK_SUCCESS);')
    # Inclusive CPU pipeline time: address lowering, Vulkan object preparation,
    # driver compilation and cleanup. Do not label the residual as NVK time.
    call = 'int result = nvmtl_vk_pipeline_create_impl_lifetime_body(vs, vn, fs, fn, vkfmt, depthfmt, blend_, vin_, samples, td, rt, &pending);'
    s = once(s, call, 'uint64_t pipelineT=ga102_tick();\n    '+call)
    site = 'else *(nvk_pipeline *)out_ = pending;\n    return result;'
    s = once(s, site, 'else *(nvk_pipeline *)out_ = pending;\n    ga102_record(GA102_PIPELINE_TOTAL,ga102_tick()-pipelineT,result != 0);\n    return result;')
    vk.write_text(s)
    with unit.open('a') as out:
        out.write('''
__attribute__((visibility("default"))) const char *ga102_perf_snapshot(void) { return ga102_metrics_json(); }
__attribute__((visibility("default"))) const char *ga102_perf_cache(void) { return ga102_owned_root(); }
__attribute__((visibility("default"))) const char *ga102_perf_image(unsigned kind) {
    const void *p=NULL;
    switch(kind) {
        case 0: p=(const void *)gGA102TranslateImplementation; break;
        case 1: p=(const void *)ga102_actual_sampler; break;
        case 2: p=(const void *)gGA102LowerExImplementation; break;
        case 3: p=(const void *)pvkGetInstanceProcAddr; break;
        case 4: p=(const void *)pvkCreateGraphicsPipelines; break;
        case 5: p=(const void *)nvLLVMParseBitcodeInContext2; break;
        default: return NULL;
    }
    Dl_info info={0}; return p && dladdr(p,&info) ? info.dli_fname : NULL;
}
''')
    return {'profile': 'ga102-graphics-v2', 'metrics_header_sha256': hashlib.sha256(header.read_bytes()).hexdigest(),
            'transformer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'transformed_source_sha256': {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()},
            'limitations': 'Generated source only until Apple compilation/GPU qualification; internal sampler reflection is included in sampler ABI time, not separately instrumented.'}
