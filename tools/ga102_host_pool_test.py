#!/usr/bin/env python3
"""Sanitized production pool growth/free/rollback with captured heap operations."""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    source=(ROOT/'plugin/nvmtl_vk.c').read_text()
    def region(first,last):return source[source.index(first):source.index(last,source.index(first))]
    defines='\n'.join(re.search(r'^#define '+name+r'\s+[^\n]+',source,re.M)[0]
                      for name in ['NVMTL_POOL_BLOCK','NVMTL_POOL_MAX','NVMTL_POOL_KEEP'])
    host_keep=re.search(r'^#define NVMTL_POOL_KEEP_HOST\s+[^\n]+',source,re.M)
    if host_keep:defines+='\n'+host_keep[0]
    prefix=r'''
#include <assert.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nvmtl_vk.h"
'''+defines+r'''
static uint64_t g_pool_blocks,g_pool_live,g_pool_bytes,g_buf_made,g_buf_gone;
static size_t g_alloc_bytes,g_bar1_bytes;
static int fail_heap,fail_place;
static void nvlog(const char *fmt,...) { (void)fmt; }
static const char *pool_place_why(int vram) { (void)vram;return "test heap"; }
int nvmtl_vk_heap_create(size_t size,int host_visible,nvk_heap *out) {
    if (fail_heap) {fail_heap=0;return -1;}
    *out=(nvk_heap){0};out->mem=out->map=malloc(size);assert(out->map);
    out->size=size;out->host_visible=host_visible;g_alloc_bytes+=size;return 0;
}
static int vpool_heap_create(size_t size,nvk_heap *out) {
    int result=nvmtl_vk_heap_create(size,1,out);if (!result)g_bar1_bytes+=size;return result;
}
void nvmtl_vk_heap_destroy(nvk_heap *heap) {
    assert(g_alloc_bytes>=heap->size);g_alloc_bytes-=heap->size;free(heap->mem);memset(heap,0,sizeof *heap);
}
int nvmtl_vk_buffer_create_placed(size_t size,nvk_heap *heap,size_t offset,nvk_buffer *out) {
    if (fail_place) {fail_place=0;return -1;}
    assert(offset%256==0 && offset<=heap->size && size<=heap->size-offset);
    *out=(nvk_buffer){0};out->mem=heap->mem;out->map=(char *)heap->map+offset;
    out->buf=out->map;out->placed=1;out->size=size;g_buf_made++;return 0;
}
'''
    structs=region('typedef struct { size_t off, len; } pool_range;','static size_t pool_align(void)')
    takegive=region('static int pool_block_take(','static int vpool_on(void)')
    allocator=region('static int pool_buffer_create_in(int vram, size_t size, nvk_buffer *out)\n{','int nvmtl_vk_image_placed_fits(')
    code=prefix+structs+'static size_t pool_align(void) {g_pool_align=256;return g_pool_align;}\n'+takegive+allocator+r'''
static void drain(void) {
    while(g_pool) {pool_block *b=g_pool;g_pool=b->next;nvmtl_vk_heap_destroy(&b->heap);free(b->fr);free(b);g_pool_blocks--;}
    while(g_vpool) {pool_block *b=g_vpool;g_vpool=b->next;g_bar1_bytes-=b->heap.size;nvmtl_vk_heap_destroy(&b->heap);free(b->fr);free(b);g_pool_blocks--;g_vpool_blocks--;}
    assert(!g_alloc_bytes && !g_pool_blocks && !g_pool_live && !g_pool_bytes && !g_bar1_bytes);
}
static size_t host_bytes(void) {size_t n=0;for(pool_block *b=g_pool;b;b=b->next)n+=b->heap.size;return n;}
int main(void) {
    nvk_buffer buffer[128],failed;
    fail_heap=1;assert(pool_buffer_create(256,&failed)==-1);assert(!g_pool && !g_pool_live && !g_alloc_bytes);
    fail_place=1;assert(pool_buffer_create(256,&failed)==-1);assert(!g_pool_live && !g_pool_bytes);
    for (unsigned wave=0;wave<4;wave++) {
        for(unsigned i=0;i<128;i++) {
            assert(!pool_buffer_create(1u<<20,&buffer[i]));
            memset(buffer[i].map,(int)i,1u<<20);
        }
        assert(g_pool_live==128 && g_pool_bytes==128u*(1u<<20));
        for(unsigned i=0;i<128;i++) assert(((unsigned char *)buffer[i].map)[(1u<<20)-1]==(unsigned char)i);
        // Fragmented free order followed by complete reclamation.
        for(unsigned parity=0;parity<2;parity++)for(unsigned i=parity;i<128;i+=2)pool_buffer_release(&buffer[i]);
        assert(!g_pool_live && !g_pool_bytes && host_bytes()<=(64u<<20));
    }
    drain();
    assert(!pool_buffer_create(NVMTL_POOL_MAX,&buffer[0]));
    assert(buffer[0].size==NVMTL_POOL_MAX && buffer[0].alloc>=NVMTL_POOL_MAX);
    pool_buffer_release(&buffer[0]);drain();
    // VRAM pool size and retention policy remain independent of host tuning.
    for(unsigned i=0;i<5;i++)assert(!pool_buffer_create_in(1,NVMTL_POOL_MAX,&buffer[i]));
    for(unsigned i=0;i<5;i++)pool_buffer_release(&buffer[i]);
    assert(g_vpool_blocks<=NVMTL_POOL_KEEP);drain();
    puts("PASS: production host/VRAM pool growth, fragmented free, reuse, failure rollback, trimming and full cleanup");
}
'''
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);(path/'proof.c').write_text(code)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined',
                        '-I'+str(ROOT/'plugin'),str(path/'proof.c'),'-o',str(path/'proof')],check=True)
        subprocess.run([str(path/'proof')],check=True)


if __name__=='__main__':main()
