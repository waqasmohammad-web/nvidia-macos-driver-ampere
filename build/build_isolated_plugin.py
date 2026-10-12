#!/usr/bin/env python3
"""Build a private Objective-C class namespace for isolated offscreen testing.

Only copied sources are rewritten. Class names and their literal lookup strings
are renamed together; C symbols are hidden. No driver installation, kernel
collection, configuration or graphics-service operation is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PREFIX='NVMTLGA102_'


def snapshot(directory):
    files=[f for f in (ROOT/'plugin').iterdir() if f.is_file()]
    names=set()
    for f in files:
        if f.suffix in ('.m','.h','.c'):
            names.update(re.findall(r'@(?:interface|implementation|protocol)\s+(NVMTL\w+)',f.read_text()))
    if 'NVMTLDevice' not in names:raise ValueError('device declaration unavailable')
    mapping={name:PREFIX+name[5:] for name in sorted(names)}
    pattern=re.compile(r'\b('+ '|'.join(map(re.escape,mapping))+r')\b')
    hashes={}
    for f in files:
        original=f.read_bytes();hashes[f.name]=hashlib.sha256(original).hexdigest()
        if f.suffix in ('.m','.h','.c'):
            transformed=pattern.sub(lambda m:mapping[m[0]],original.decode())
            # This global is returned by resource -device methods; keep it private
            # even if the installed bundle is subsequently loaded by IOSurface.
            transformed=re.sub(r'\bgNVMTLMainDevice\b','gGA102MainDevice',transformed)
            (directory/f.name).write_text(transformed)
        else:(directory/f.name).write_bytes(original)
    return mapping,hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--vulkan-headers',type=Path,required=True)
    parser.add_argument('--translator',type=Path,help='Explicit CPU translator dylib for this private build; defaults to installed release')
    args=parser.parse_args()
    if not (args.vulkan_headers/'vulkan/vulkan_core.h').is_file():parser.error('Vulkan include directory required')
    args.output.mkdir(parents=True,exist_ok=False)
    source=args.output/'source';source.mkdir()
    mapping,hashes=snapshot(source)
    library_source=source/'NVMTLLibraryLoad.m'
    library=library_source.read_text()
    declaration='static nvmtl_translate_fn xlate;'
    assignment='xlate = (nvmtl_translate_fn)dlsym(h, "nvmtl_translate");'
    if library.count(declaration)!=1 or library.count(assignment)!=1:
        raise ValueError('translation instrumentation site changed')
    library=library.replace(declaration,declaration+'''
static nvmtl_translate_fn gGA102TranslateImplementation;
static _Atomic unsigned long gGA102TranslateCalls;
static int ga102_counted_translate(const char *ll, const char *stage, uint8_t **out,
                                 size_t *length, char *err, size_t capacity) {
    atomic_fetch_add_explicit(&gGA102TranslateCalls, 1, memory_order_relaxed);
    return gGA102TranslateImplementation(ll, stage, out, length, err, capacity);
}
''')
    library=library.replace(assignment,'gGA102TranslateImplementation = (nvmtl_translate_fn)dlsym(h, "nvmtl_translate");\n        xlate = gGA102TranslateImplementation ? ga102_counted_translate : NULL;')
    lower_decl='static nvmtl_lower_fn xlate_lower;'
    lower_ex_decl='static nvmtl_lower_ex_fn xlate_lower_ex;'
    lower_assign='xlate_lower = (nvmtl_lower_fn)dlsym(h, "nvmtl_lower_buffer_addresses");'
    lower_ex_assign='xlate_lower_ex = (nvmtl_lower_ex_fn)dlsym(h, "nvmtl_lower_buffer_addresses_ex");'
    if any(library.count(site)!=1 for site in [lower_decl,lower_ex_decl,lower_assign,lower_ex_assign]):
        raise ValueError('address-lowering instrumentation site changed')
    library=library.replace(lower_decl,lower_decl+'''
static nvmtl_lower_fn gGA102LowerImplementation;
static _Atomic unsigned long gGA102LowerCalls;
static int ga102_counted_lower(const uint8_t *data, size_t size, uint8_t **out,
                              size_t *length, char *err, size_t capacity) {
    atomic_fetch_add_explicit(&gGA102LowerCalls, 1, memory_order_relaxed);
    return gGA102LowerImplementation(data, size, out, length, err, capacity);
}
''')
    library=library.replace(lower_ex_decl,lower_ex_decl+'''
static nvmtl_lower_ex_fn gGA102LowerExImplementation;
static int ga102_counted_lower_ex(const uint8_t *data, size_t size, uint32_t flags,
                                 uint8_t **out, size_t *length, uint32_t *info,
                                 char *err, size_t capacity) {
    atomic_fetch_add_explicit(&gGA102LowerCalls, 1, memory_order_relaxed);
    return gGA102LowerExImplementation(data, size, flags, out, length, info, err, capacity);
}
''')
    library=library.replace(lower_assign,'gGA102LowerImplementation = (nvmtl_lower_fn)dlsym(h, "nvmtl_lower_buffer_addresses");\n        xlate_lower = gGA102LowerImplementation ? ga102_counted_lower : NULL;')
    library=library.replace(lower_ex_assign,'gGA102LowerExImplementation = (nvmtl_lower_ex_fn)dlsym(h, "nvmtl_lower_buffer_addresses_ex");\n        xlate_lower_ex = gGA102LowerExImplementation ? ga102_counted_lower_ex : NULL;')
    library_source.write_text(library)
    with (source/'NVMTLDevice.m').open('a') as unit:
        unit.write('''\n__attribute__((visibility("default")))
const char *ga102_isolated_translator_image(void) {
    Dl_info info = {0};
    return gGA102TranslateImplementation && dladdr((const void *)gGA102TranslateImplementation, &info) ? info.dli_fname : NULL;
}
__attribute__((visibility("default")))
unsigned long ga102_isolated_translation_calls(void) {
    return atomic_load_explicit(&gGA102TranslateCalls, memory_order_relaxed);
}
__attribute__((visibility("default")))
const char *ga102_isolated_lowering_image(void) {
    Dl_info info = {0};
    const void *implementation = gGA102LowerExImplementation ? (const void *)gGA102LowerExImplementation : (const void *)gGA102LowerImplementation;
    return implementation && dladdr(implementation, &info) ? info.dli_fname : NULL;
}
__attribute__((visibility("default")))
unsigned long ga102_isolated_lowering_calls(void) {
    return atomic_load_explicit(&gGA102LowerCalls, memory_order_relaxed);
}
''')
    binary=args.output/'NVMTLDriver'
    cmd=['xcrun','clang','-arch','x86_64','-bundle','-fobjc-arc','-O1','-DNVMTL_RELEASE=1',
         '-fvisibility=hidden','-Wno-protocol','-Wno-incomplete-implementation',
         '-I'+str(args.vulkan_headers.resolve()),'-o',str(binary),str(source/'NVMTLDevice.m'),
         '-framework','Foundation','-framework','Metal','-framework','IOSurface']
    with (args.output/'build.private.log').open('w') as log:
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
    for name in ['libnvmtl_translate.dylib','air-runtime']:
        target=args.translator.resolve() if name=='libnvmtl_translate.dylib' and args.translator else Path('/Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS')/name
        if not target.exists():raise FileNotFoundError('installed CPU translator/runtime dependency absent')
        (args.output/name).symlink_to(target)
    proof={'schema_version':1,'class_prefix':PREFIX,'class_mapping':mapping,
           'source_sha256':hashes,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
           'installed':False,'runtime_executed':False,'c_symbols_hidden':True,
           'translator_image_probe':True,
           'translator_call_counter':True,
           'lowering_call_counter':True,
           'translator_sha256':hashlib.sha256((args.output/'libnvmtl_translate.dylib').read_bytes()).hexdigest(),
           'limits':'experimental namespace build; GPU correctness/provenance require separate execution'}
    (args.output/'isolation-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    (args.output/'command.private.json').write_text(json.dumps(cmd,indent=2)+'\n')
    print(json.dumps({'binary_sha256':proof['binary_sha256'],'renamed_classes_and_protocols':len(mapping),'installed':False}))


if __name__=='__main__':main()
