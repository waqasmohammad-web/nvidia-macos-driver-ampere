#!/usr/bin/env python3
"""Exercise the production pool opener against captured Vulkan calls, without a GPU."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vulkan-headers', type=Path, required=True)
    args = parser.parse_args()
    source = (ROOT/'plugin/nvmtl_vk.c').read_text()
    start = source.index('static int nvmtl_desc_pool_open(void)')
    end = source.index('\nstatic int g_descriptor_state;', start)
    names = ['NVMTL_MAX_SETS', 'NVMTL_DESC_SET_BUDGET', 'NVMTL_INITIAL_POOL_SETS',
             'NVMTL_MAX_POOLS', 'NVMTL_NBUF', 'NVMTL_NTEX', 'NVMTL_NSAMP', 'NVMTL_NSTEX']
    defines = '\n'.join(re.search(r'^#define '+n+r'\s+[^\n]+', source, re.M)[0] for n in names)
    unit = r'''
#include <vulkan/vulkan_core.h>
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
''' + defines + r'''
static VkDescriptorPool g_descPools[NVMTL_MAX_POOLS];
static unsigned g_ndescPools;
static uint32_t g_desc_pool_sets;
static VkDevice g_dev;
static int g_mutable_layout, fail_next;
static unsigned calls;
static uint32_t last_sets;
static void nvlog(const char *fmt, ...) { (void)fmt; }
#define VKCK(call, label) do { if ((call) != VK_SUCCESS) return -1; } while (0)
static VkResult pvkCreateDescriptorPool(VkDevice dev, const VkDescriptorPoolCreateInfo *p,
                                      const VkAllocationCallbacks *a, VkDescriptorPool *out) {
    (void)dev; (void)a; ++calls;
    assert(p->flags == VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT);
    assert(p->poolSizeCount == 5);
    uint32_t factor[5] = {1, NVMTL_NBUF+1, NVMTL_NTEX, NVMTL_NSAMP, NVMTL_NSTEX};
    VkDescriptorType types[5] = {VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER_DYNAMIC,
        VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE,
        VK_DESCRIPTOR_TYPE_SAMPLER, VK_DESCRIPTOR_TYPE_STORAGE_IMAGE};
    if (g_mutable_layout) {
        const VkMutableDescriptorTypeCreateInfoEXT *m = p->pNext;
        assert(m && m->mutableDescriptorTypeListCount == 5);
        assert(m->pMutableDescriptorTypeLists[2].descriptorTypeCount == 4);
        assert(m->pMutableDescriptorTypeLists[4].descriptorTypeCount == 4);
        types[2] = types[4] = VK_DESCRIPTOR_TYPE_MUTABLE_EXT;
    } else assert(!p->pNext);
    for (unsigned i=0;i<5;++i) {
        assert(p->pPoolSizes[i].type == types[i]);
        assert(p->pPoolSizes[i].descriptorCount == factor[i]*p->maxSets);
    }
    last_sets=p->maxSets;
    if (fail_next) { fail_next=0; return VK_ERROR_OUT_OF_HOST_MEMORY; }
    *out=(VkDescriptorPool)(uintptr_t)calls; return VK_SUCCESS;
}
''' + source[start:end] + r'''
int main(void) {
    for (int mutable=0;mutable<=1;++mutable) {
        g_mutable_layout=mutable; g_ndescPools=0; g_desc_pool_sets=0;
        fail_next=1; assert(nvmtl_desc_pool_open() == -1);
        assert(g_ndescPools == 0 && g_desc_pool_sets == 0);
        assert(nvmtl_desc_pool_open() == 0 && last_sets == 256);
        assert(nvmtl_desc_pool_open() == 0 && last_sets == 4096);
        unsigned before_pools=g_ndescPools; uint32_t before_sets=g_desc_pool_sets;
        fail_next=1; assert(nvmtl_desc_pool_open() == -1);
        assert(g_ndescPools == before_pools && g_desc_pool_sets == before_sets);
        while (g_desc_pool_sets < NVMTL_DESC_SET_BUDGET) assert(nvmtl_desc_pool_open() == 0);
        assert(g_ndescPools == 65 && last_sets == 3840);
        assert(g_desc_pool_sets == 64u*4096u);
        unsigned before_calls=calls;
        assert(nvmtl_desc_pool_open() == -1 && calls == before_calls);
    }
    puts("PASS: actual pool opener; mutable/nonmutable counts, growth, exact budget, failed creation and ceiling");
}
'''
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory); (path/'proof.c').write_text(unit)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                        '-I'+str(args.vulkan_headers.resolve()),str(path/'proof.c'),'-o',str(path/'proof')],check=True)
        subprocess.run([str(path/'proof')],check=True)


if __name__ == '__main__': main()
