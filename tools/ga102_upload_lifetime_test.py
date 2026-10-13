#!/usr/bin/env python3
"""ASan/UBSan actual upload helpers with captured Vulkan calls (no GPU)."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vulkan-headers', type=Path, required=True)
    args = parser.parse_args()
    source = (ROOT / 'plugin/nvmtl_vk.c').read_text()
    start = source.index('#define NVMTL_UPSTAGE_KEEP')
    end = source.index('\nint nvmtl_vk_copy_buffer', start)
    unit = r'''
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan_core.h>
#include "nvmtl_vk.h"
static unsigned made, destroyed, submits, copies, barriers;
static int fail_create, fail_begin, submit_result;
static nvk_buffer *recorded;
static void nvlog(const char *fmt, ...) { (void)fmt; }
static uint32_t nvmtl_blocks(uint32_t n, uint32_t b) { return b ? (n+b-1)/b : n; }
static VkImageAspectFlags nvmtl_barrier_aspect(const nvk_image *i) { (void)i;return VK_IMAGE_ASPECT_COLOR_BIT; }
static VkImageAspectFlags nvmtl_copy_aspect(const nvk_image *i) { (void)i;return VK_IMAGE_ASPECT_COLOR_BIT; }
int nvmtl_vk_buffer_create(size_t size, int host, nvk_buffer *b) {
    assert(host==1); if(fail_create) {fail_create=0;return -1;}
    *b=(nvk_buffer){0};b->buf=b->map=malloc(size);assert(b->map);b->size=size;made++;recorded=b;return 0;
}
void nvmtl_vk_buffer_destroy(nvk_buffer *b) {if(b->buf) {free(b->map);destroyed++;}memset(b,0,sizeof *b);}
int nvmtl_vk_cmd_begin(nvk_queue *q,nvk_cmdbuf *c) {(void)q;if(fail_begin)return -1;memset(c,0,sizeof *c);c->cb=(void*)1;barriers=0;return 0;}
static void pvkCmdPipelineBarrier(void *cb,VkPipelineStageFlags src,VkPipelineStageFlags dst,
 VkDependencyFlags flags,uint32_t nm,const VkMemoryBarrier *m,uint32_t nb,const VkBufferMemoryBarrier *b,
 uint32_t ni,const VkImageMemoryBarrier *i) {
 (void)cb;(void)flags;(void)m;(void)b;assert(!nm&&!nb&&ni==1);assert(i->subresourceRange.levelCount==1);
 if(!barriers) {assert(src==VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT&&dst==VK_PIPELINE_STAGE_TRANSFER_BIT);
 assert(i->oldLayout==VK_IMAGE_LAYOUT_UNDEFINED&&i->newLayout==VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);}
 else {assert(src==VK_PIPELINE_STAGE_TRANSFER_BIT&&dst==VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT);
 assert(i->srcAccessMask==VK_ACCESS_TRANSFER_WRITE_BIT&&i->dstAccessMask==VK_ACCESS_SHADER_READ_BIT);}
 barriers++;
}
static void pvkCmdCopyBufferToImage(void *cb,VkBuffer b,VkImage i,VkImageLayout l,uint32_t n,const VkBufferImageCopy *r) {
 (void)cb;(void)i;assert(b==(VkBuffer)recorded->buf&&l==VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL&&n==1);assert(r->imageExtent.depth==1);copies++;
}
int nvmtl_vk_submit_wait_at(nvk_cmdbuf *c,const char *who) {assert(!strcmp(who,"surface upload")&&barriers==2);submits++;if(submit_result!=-2)c->cb=NULL;return submit_result;}
''' + source[start:end] + r'''
static void *worker(void *unused) {
 (void)unused;nvk_image image={.w=2,.h=2,.bpp=4};unsigned char pixels[16]={0};
 assert(!nvmtl_vk_image_write(NULL,&image,pixels,8));return NULL;
}
int main(int argc,char **argv) {
 (void)argv;
 nvk_image image={.w=2,.h=2,.bpp=4};unsigned char src[24];for(unsigned i=0;i<24;i++)src[i]=(unsigned char)i;
 if(argc>1) {pthread_once(&g_upstage_once,nvmtl_upstage_key_make);g_upstage_ready=0;
 assert(nvmtl_vk_image_write(NULL,&image,src,12)==-1&&made==0);puts("PASS: unavailable TLS fails closed");return 0;}
 assert(nvmtl_vk_image_write(NULL,&image,src,7)==-1&&made==0);
 assert(nvmtl_vk_image_write(NULL,&image,NULL,12)==-1&&made==0);
 assert(nvmtl_vk_image_write(NULL,&image,src,SIZE_MAX)==-1&&made==0);
 fail_create=1;assert(nvmtl_vk_image_write(NULL,&image,src,12)==-1&&made==0);
 assert(!nvmtl_vk_image_write(NULL,&image,src,12));assert(made==1&&submits==1);
 assert(!memcmp(recorded->map,src,8)&&!memcmp((char*)recorded->map+8,src+12,8));
 assert(!nvmtl_vk_image_write(NULL,&image,src,8)&&made==1&&submits==2);
 fail_begin=1;assert(nvmtl_vk_image_write(NULL,&image,src,8)==-1&&submits==2);fail_begin=0;
 submit_result=-1;assert(nvmtl_vk_image_write(NULL,&image,src,8)==-1);submit_result=0;
 image.w=4096;image.h=2049;size_t bytes=(size_t)image.w*image.h*4;unsigned char *big=calloc(1,bytes);assert(big);
 assert(!nvmtl_vk_image_write(NULL,&image,big,image.w*4)&&destroyed==2);free(big);
 image.w=image.h=2;assert(!nvmtl_vk_image_write(NULL,&image,src,8));
 nvmtl_upstage *st=pthread_getspecific(g_upstage_key);unsigned before=destroyed;
 submit_result=-2;assert(nvmtl_vk_image_write(NULL,&image,src,8)==-2&&st->uncertain);
 unsigned before_submits=submits;assert(!nvmtl_upstage_get(16));nvmtl_upstage_free(st);assert(destroyed==before);
 assert(nvmtl_vk_image_write(NULL,&image,src,8)==-1&&submits==before_submits);
 // The call double has no real inflight GPU; explicitly end its simulated ownership for leak checking.
 st->uncertain=0;nvmtl_upstage_free(st);assert(!pthread_setspecific(g_upstage_key,NULL));submit_result=0;
 pthread_t thread;assert(!pthread_create(&thread,NULL,worker,NULL));assert(!pthread_join(thread,NULL));
 assert(made==destroyed);assert(copies==submits);
 puts("PASS: actual upload: pitched/tight copy, synchronous submit, reuse, >32MiB eviction, TLS exit, failures, uncertain lifetime");return 0;
}
'''
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        (path / 'proof.c').write_text(unit)
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-missing-field-initializers',
                        '-pthread', '-fsanitize=address,undefined', '-I'+str(args.vulkan_headers.resolve()),
                        '-I'+str(ROOT / 'plugin'), str(path / 'proof.c'), '-o', str(path / 'proof')], check=True)
        subprocess.run([str(path / 'proof')], check=True)
        subprocess.run([str(path / 'proof'), 'tls-failure'], check=True)


if __name__ == '__main__':
    main()
