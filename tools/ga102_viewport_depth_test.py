#!/usr/bin/env python3
"""Exercise the production viewport function with captured Vulkan arguments."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vulkan-headers',type=Path,required=True)
    args=parser.parse_args()
    source=(ROOT/'plugin/nvmtl_vk.c').read_text()
    start=source.index('void nvmtl_vk_cmd_set_viewport(')
    end=source.index('\nstatic void nvmtl_vk_zero_dummies(void)',start)
    code=r'''
#include <vulkan/vulkan_core.h>
#include <math.h>
#include <assert.h>
#include <stdio.h>
typedef struct { VkCommandBuffer cb; } nvk_cmdbuf;
static VkViewport got;
static void pvkCmdSetViewport(VkCommandBuffer cb,uint32_t first,uint32_t count,const VkViewport *vp) {
    (void)cb; assert(first==0 && count==1);got=*vp;
}
''' + source[start:end] + r'''
int main(void) {
    float values[]={-INFINITY,-2,0,0.25f,1,2,INFINITY,NAN};
    nvk_cmdbuf c={0};
    for (unsigned i=0;i<8;i++) for (unsigned j=0;j<8;j++) {
        nvmtl_vk_cmd_set_viewport(&c,3,5,32,48,values[i],values[j]);
        assert(got.x==3 && got.y==53 && got.width==32 && got.height==-48);
        float lo=isnan(values[i])?0:fmaxf(0,fminf(1,values[i]));
        float hi=isnan(values[j])?1:fmaxf(0,fminf(1,values[j]));
        assert(got.minDepth==lo && got.maxDepth==hi);
    }
    nvmtl_vk_cmd_set_viewport(&c,0,0,32,32,1,0);
    assert(got.minDepth==1 && got.maxDepth==0); /* reversed depth stays valid */
    puts("PASS: production viewport; 64 depth pairs, infinities/NaNs, reversed depth and raster coordinates");
}
'''
    with tempfile.TemporaryDirectory() as directory:
        p=Path(directory);(p/'proof.c').write_text(code)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                        '-I'+str(args.vulkan_headers.resolve()),str(p/'proof.c'),'-o',str(p/'proof')],check=True)
        subprocess.run([str(p/'proof')],check=True)
        baseline=subprocess.check_output(['git','-C',str(ROOT),'show','4095041:plugin/nvmtl_vk.c'],text=True)
        bstart=baseline.index('void nvmtl_vk_cmd_set_viewport(')
        bend=baseline.index('\nstatic void nvmtl_vk_zero_dummies(void)',bstart)
        (p/'baseline.c').write_text(code.replace(source[start:end],baseline[bstart:bend],1))
        subprocess.run(['cc','-std=c11','-I'+str(args.vulkan_headers.resolve()),
                        str(p/'baseline.c'),'-o',str(p/'baseline')],check=True)
        rejected=subprocess.run([str(p/'baseline')],capture_output=True,text=True)
        assert rejected.returncode != 0 and 'got.minDepth' in rejected.stderr, rejected.stderr
        print('PASS: actual baseline rejects the depth oracle as expected')


if __name__=='__main__': main()
