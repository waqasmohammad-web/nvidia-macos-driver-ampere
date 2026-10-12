#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Dependency preparation only; builds and hardware probes are deliberately separate.
command -v python3
command -v cargo
command -v rustc
command -v cc
command -v spirv-val
python3 --version
rustc --version
spirv-val --version
python3 - <<'PY'
import os, shutil
from pathlib import Path
memory = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
for path in ('/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory/memory.limit_in_bytes'):
    try:
        memory = min(memory, int(Path(path).read_text().strip()))
    except (OSError, ValueError):
        pass
print('Available planning ceiling: RAM %.1f GiB; free disk %.1f GiB; CPUs %d' %
      (memory / 2**30, shutil.disk_usage('.').free / 2**30, os.cpu_count() or 1))
PY
cargo fetch --locked --manifest-path translator/translator/Cargo.toml
python3 -S -m unittest discover -s tools -p 'test_ga102_*.py'
