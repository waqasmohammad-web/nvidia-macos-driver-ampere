#!/usr/bin/env python3
"""xz -ce -C none equivalent for upstream NVKMS shader compression only.

Use with make XZ='python3 /path/to/compress_nvkms_shaders.py'. No installation,
vendor source edits or replacement shader contents are involved.
"""
import lzma
import sys

if sys.argv[1:] != ['-ce', '-C', 'none']:
    raise SystemExit('Only the upstream NVKMS flags -ce -C none are supported')
compressor = lzma.LZMACompressor(format=lzma.FORMAT_XZ, check=lzma.CHECK_NONE,
                                preset=6 | lzma.PRESET_EXTREME)
while True:
    chunk = sys.stdin.buffer.read(65536)
    if not chunk:
        break
    sys.stdout.buffer.write(compressor.compress(chunk))
sys.stdout.buffer.write(compressor.flush())
