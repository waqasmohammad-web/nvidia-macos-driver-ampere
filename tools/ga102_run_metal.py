#!/usr/bin/env python3
"""Compile/run only the GA102 probes with external deadlines and private scratch.

No driver settings, display APIs, sudo, installation, or production-cache deletion.
Optional --isolated-cache uses test-owned Mesa/AIR caches; repeat uses the same
scratch directories to compare process starts (other compiler caches remain).
Logs stay in a new private temporary directory, never auto-committed.
"""
import argparse
import os
import signal
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
PROBES = ("ga102_metal_smoketest", "ga102_metal_render_smoketest", "ga102_metal_benchmark",
          "ga102_metal_memory", "ga102_metal_present", "ga102_metal_composite")


def run_owned(command, log, timeout, env=None):
    """Deadline applies to our process group, including compiler children."""
    with subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                          start_new_session=True) as child:
        try:
            return child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Signal only the session we created, never WindowServer/services.
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", choices=PROBES)
    parser.add_argument("--repeat", type=int, choices=range(1, 4), default=1)
    parser.add_argument("--isolated-cache", action="store_true")
    parser.add_argument("--surface-comparison", action="store_true", help="Benchmark matching BGRA8 targets at 3440x1440 only")
    parser.add_argument("--graphics-copy-queue", action="store_true", help="Attempt test-process-only NVRM_610_CECHAN=0; verify engine selection in logs (installed builds may differ)")
    args = parser.parse_args()
    if args.surface_comparison and args.probe != "ga102_metal_benchmark":
        parser.error("--surface-comparison requires ga102_metal_benchmark")
    scratch = Path(tempfile.mkdtemp(prefix="ga102-metal-"))
    print(f"Local diagnostic scratch: {scratch}", flush=True)
    executable = scratch / args.probe
    env = os.environ.copy()
    if args.graphics_copy_queue:
        env["NVRM_610_CECHAN"] = "0"
    if args.isolated_cache:
        for key, name in [("MESA_SHADER_CACHE_DIR", "mesa"), ("NVMTL_AIRCACHE", "air")]:
            folder = scratch / name
            folder.mkdir(mode=0o700)
            env[key] = str(folder)
    compile_command = ["xcrun", "swiftc", "-O", "-module-cache-path", str(scratch / "modules"),
                       str(ROOT / "tools" / f"{args.probe}.swift"), "-o", str(executable)]
    try:
        with (scratch / "compile.log").open("w") as log:
            code = run_owned(compile_command, log, 90)
        if code:
            print((scratch / "compile.log").read_text()[-6000:])
            return code
        for iteration in range(args.repeat):
            output = scratch / f"run-{iteration + 1}.log"
            with output.open("w") as log:
                command = [str(executable)] + (["--surface-comparison"] if args.surface_comparison else [])
                code = run_owned(command, log, 45, env)
            print(f"Run {iteration + 1}: exit {code}", flush=True)
            # Avoid copying paths, addresses and process identities from driver logs
            # into public reports; print only probe-owned result lines here.
            lines = output.read_text(errors="replace").splitlines()
            for line in lines:
                if line.startswith(("Metal GPU:", "Computed values:", "Center pixel", "PASS", "FAIL",
                                    "device:", "device_creation_ms:", "library_creation_ms:",
                                    "pipeline_creation_ms_in_order:", "result:")):
                    print(line, flush=True)
            if code:
                print(f"Failure details remain in {output}", flush=True)
                return code
    except subprocess.TimeoutExpired as error:
        print(f"FAIL: external deadline {error.timeout}s exceeded; owned child terminated", flush=True)
        return 124
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
