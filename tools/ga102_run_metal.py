#!/usr/bin/env python3
"""Compile/run only the GA102 probes with external deadlines and private scratch.

No driver/display-setting writes, sudo, installation, or production-cache deletion.
Optional --isolated-cache requests test-owned Mesa/AIR caches; the installed
release plugin clears NVMTL_AIRCACHE, so AIR isolation must not be assumed.
Repeat uses the same scratch directories (other compiler caches remain).
Logs stay in a new private temporary directory, never auto-committed.
"""
import argparse
import hashlib
import json
import os
import signal
from pathlib import Path
import subprocess
import tempfile
import time
try:
    from .ga102_visual_validation import evaluate as evaluate_visual, repeated_result
    from .ga102_pacing_validation import evaluate as evaluate_pacing, repeated_pacing_result
    from .ga102_core_validation import CORE_PROBES, FIELDS, evaluate as evaluate_core, repeated_core_result
    from .ga102_capture_bridge import CaptureBroker
except ImportError:
    from ga102_visual_validation import evaluate as evaluate_visual, repeated_result
    from ga102_pacing_validation import evaluate as evaluate_pacing, repeated_pacing_result
    from ga102_core_validation import CORE_PROBES, FIELDS, evaluate as evaluate_core, repeated_core_result
    from ga102_capture_bridge import CaptureBroker

ROOT = Path(__file__).resolve().parent.parent
PROBES = ("ga102_metal_smoketest", "ga102_metal_render_smoketest", "ga102_metal_benchmark",
          "ga102_metal_memory", "ga102_metal_present", "ga102_metal_composite", "ga102_metal_crossprocess", "ga102_metal_events", "ga102_core_animation", "ga102_visual_present")


def run_owned(command, log, timeout, env=None, observer=None):
    """Deadline applies to our process group, including compiler children."""
    with subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                          start_new_session=True) as child:
        try:
            if observer is None:
                return child.wait(timeout=timeout)
            deadline = time.monotonic() + timeout
            while child.poll() is None:
                observer(child)
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise subprocess.TimeoutExpired(command, timeout)
                try: return child.wait(timeout=min(.05, remaining))
                except subprocess.TimeoutExpired: pass
            return child.returncode
        except BaseException:
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


DISPLAY_COUNTERS = tuple("debug." + name for name in (
    "nvaccel_iop_ok", "nvaccel_iop_flips", "nvaccel_iop_async_refused",
    "nvaccel_iop_async_drop", "nvaccel_iop_fail", "nvrmfb_flip_n",
    "nvrmfb_flip_us_sum", "nvrmfb_flip_us_max"))

def display_counters():
    """Read only named integer counters; unavailable data stays unavailable."""
    result = {}
    try:
        read = subprocess.run(["/usr/sbin/sysctl", *DISPLAY_COUNTERS],
                              capture_output=True, text=True, timeout=5)
        for line in read.stdout.splitlines():
            key, _, value = line.partition(": ")
            if key in DISPLAY_COUNTERS:
                try: result[key] = int(value)
                except ValueError: pass
    except (OSError, subprocess.TimeoutExpired):
        pass
    return result

def display_delta(before, after):
    delta = {key: after[key] - before[key] for key in DISPLAY_COUNTERS
             if key in before and key in after and not key.endswith("_max")}
    n = delta.get("debug.nvrmfb_flip_n", 0)
    return {"deltas": delta, "available_counters": len(delta),
            "mean_flip_call_us": delta["debug.nvrmfb_flip_us_sum"] / n
            if n > 0 and delta.get("debug.nvrmfb_flip_us_sum", -1) >= 0 else None,
            "visible_presentation": "candidate" if n > 0 else "unverified",
            "note": "system-wide counters, not exclusively this window; flip duration includes completion wait"}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", choices=PROBES)
    parser.add_argument("--repeat", type=int, choices=range(1, 4), default=1)
    parser.add_argument("--isolated-cache", action="store_true")
    parser.add_argument("--surface-comparison", action="store_true", help="Benchmark matching BGRA8 targets at 3440x1440 only")
    parser.add_argument("--graphics-copy-queue", action="store_true", help="Attempt test-process-only NVRM_610_CECHAN=0; verify engine selection in logs (installed builds may differ)")
    parser.add_argument("--negative-control", choices=("static", "timestamps", "hidden"))
    parser.add_argument("--display-linked", action="store_true")
    parser.add_argument("--capture-bridge", action="store_true", help="Capture only the owned visual window via ScreenCaptureKit in this Python process; never requests permission")
    parser.add_argument("--result-json", type=Path, help="Save scoped visual-probe verdicts and numeric metrics, excluding raw logs and machine identities")
    args = parser.parse_args()
    if args.capture_bridge and args.probe != 'ga102_visual_present':
        parser.error('--capture-bridge requires ga102_visual_present')
    if args.result_json and args.probe not in (*CORE_PROBES, "ga102_visual_present", "ga102_metal_present"):
        parser.error("--result-json requires a core correctness or presentation probe")
    if args.result_json and args.result_json.exists():
        parser.error("--result-json must name a new file; existing evidence is never overwritten")
    if args.display_linked and args.probe != "ga102_metal_present":
        parser.error("--display-linked requires ga102_metal_present")
    if args.negative_control and args.probe != "ga102_visual_present":
        parser.error("--negative-control requires ga102_visual_present")
    if args.surface_comparison and args.probe != "ga102_metal_benchmark":
        parser.error("--surface-comparison requires ga102_metal_benchmark")
    scratch = Path(tempfile.mkdtemp(prefix="ga102-metal-"))
    print(f"Local diagnostic scratch: {scratch}", flush=True)
    executable = scratch / args.probe
    env = os.environ.copy()
    if args.graphics_copy_queue:
        env["NVRM_610_CECHAN"] = "0"
        print("NOT VERIFIED: copy-engine override requested; release plugins clear NVRM_* environment before reading configuration", flush=True)
    if args.isolated_cache:
        for key, name in [("MESA_SHADER_CACHE_DIR", "mesa"), ("NVMTL_AIRCACHE", "air")]:
            folder = scratch / name
            folder.mkdir(mode=0o700)
            env[key] = str(folder)
        print("Cache isolation scope: Mesa override requested; AIR override may be stripped by release-plugin initialization", flush=True)
    source_bytes = (ROOT / "tools" / f"{args.probe}.swift").read_bytes()
    compile_input = scratch / f'{args.probe}.swift'
    compile_input.write_bytes(source_bytes)
    compile_command = ["xcrun", "swiftc", "-O", "-module-cache-path", str(scratch / "modules"),
                       str(compile_input), "-o", str(executable)]
    runs = []
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    capture_source_hash = None
    try:
        with (scratch / "compile.log").open("w") as log:
            code = run_owned(compile_command, log, 90)
        if code:
            print((scratch / "compile.log").read_text()[-6000:])
            return code
        capture_library = scratch / 'window-capture.dylib'
        if args.capture_bridge:
            capture_source = scratch / 'ga102_window_capture.m'
            capture_bytes = (ROOT / 'tools/ga102_window_capture.m').read_bytes()
            capture_source.write_bytes(capture_bytes)
            capture_source_hash = hashlib.sha256(capture_bytes).hexdigest()
            command = ['xcrun', 'clang', '-dynamiclib', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                       str(capture_source), '-framework', 'Foundation', '-framework', 'AppKit',
                       '-framework', 'ScreenCaptureKit', '-framework', 'CoreGraphics', '-o', str(capture_library)]
            with (scratch / 'capture-compile.log').open('w') as log:
                code = run_owned(command, log, 60)
            if code:
                print('BLOCKED: own-window capture helper did not compile; details in private scratch', flush=True)
                return code
        for iteration in range(args.repeat):
            output = scratch / f"run-{iteration + 1}.log"
            before = display_counters() if args.probe in ("ga102_metal_present", "ga102_visual_present") else {}
            broker = None
            if args.capture_bridge:
                channel = scratch / f'capture-{iteration}'; channel.mkdir(mode=0o700)
                broker = CaptureBroker(capture_library, channel)
                env['GA102_CAPTURE_IPC'] = str(channel)
                env['GA102_CAPTURE_PERMISSION'] = '1' if broker.allowed else '0'
            with output.open("w") as log:
                command = [str(executable)] + (["--surface-comparison"] if args.surface_comparison else [])
                if args.display_linked:
                    command.append("--display-linked")
                if args.negative_control:
                    command.append(args.negative_control)
                code = (run_owned(command, log, 45, env, broker.poll) if broker else run_owned(command, log, 45, env))
            if args.probe in ("ga102_metal_present", "ga102_visual_present"):
                correlation = display_delta(before, display_counters())
                print("result: " + json.dumps({"display_correlation": correlation}, sort_keys=True), flush=True)
            print(f"Run {iteration + 1}: exit {code}", flush=True)
            # Avoid copying paths, addresses and process identities from driver logs
            # into public reports; print only probe-owned result lines here.
            lines = output.read_text(errors="replace").splitlines()
            for line in lines:
                if line.startswith(("Metal GPU:", "Computed values:", "Center pixel", "PASS", "FAIL", "NOT VERIFIED", "BLOCKED",
                                    "device:", "device_creation_ms:", "library_creation_ms:",
                                    "pipeline_creation_ms_in_order:", "result:")):
                    print(line, flush=True)
            if args.probe == "ga102_visual_present":
                verdict = None
                metrics = {}
                for line in lines:
                    if line.startswith("result: "):
                        evidence = json.loads(line[8:])
                        if evidence.get("probe") == "visual":
                            metrics = {key: value for key, value in evidence.items()
                                       if key in ("frames", "gpu_correct_frames", "gpu_distinct_patterns",
                                                  "positive_timestamps", "distinct_timestamps", "timestamps_increasing",
                                                  "visible_frames", "capture_permission", "capture_attempted",
                                                  "capture_received_frames", "capture_correct_frames", "capture_distinct_patterns")
                                       and isinstance(value, (int, float, bool))}
                            verdict = evaluate_visual(evidence, correlation)
                            print("result: " + json.dumps(verdict, sort_keys=True), flush=True)
                            if verdict["automated_visual_validation"] == "FAIL":
                                code = 1
                runs.append({"exit_code": code, "metrics": metrics, "verdict": verdict or {},
                             "display_correlation": correlation})
            elif args.probe in CORE_PROBES:
                records = [{k: v for k, v in json.loads(line[8:]).items() if k in FIELDS}
                           for line in lines if line.startswith('result: ')]
                verdict = evaluate_core(args.probe, records, code)
                print('result: ' + json.dumps(verdict, sort_keys=True), flush=True)
                if verdict['automated_core_validation'] == 'FAIL':
                    code = 1
                runs.append({'exit_code': code, 'metrics': records, 'verdict': verdict})
            elif args.probe == "ga102_metal_present":
                verdict = None
                metrics = {}
                for line in lines:
                    if line.startswith("result: "):
                        evidence = json.loads(line[8:])
                        if evidence.get("probe") == "pacing":
                            keys = ("attempted", "completed", "command_errors", "outstanding", "timer_skips",
                                    "preflight_ready", "preflight_wait_ms",
                                    "display_width", "display_height", "display_refresh_hz",
                                    "positive_presented_times", "presented_frame_ids", "presented_times",
                                    "visibility_samples", "presentation_intervals", "drawable_acquisition", "gpu",
                                    "cpu_draw_intervals", "encode", "commit_return", "commit_to_scheduled_callback",
                                    "commit_to_completed_callback", "late_frame_correlations")
                            metrics = {key: evidence[key] for key in keys if key in evidence}
                            verdict = evaluate_pacing(evidence, correlation)
                            print("result: " + json.dumps(verdict, sort_keys=True), flush=True)
                            if verdict["automated_pacing_validation"] == "FAIL":
                                code = 1
                runs.append({"exit_code": code, "metrics": metrics, "verdict": verdict or {},
                             "display_correlation": correlation})
            if code:
                print(f"Failure details remain in {output}", flush=True)
                return code
    except subprocess.TimeoutExpired as error:
        print(f"FAIL: external deadline {error.timeout}s exceeded; owned child terminated", flush=True)
        return 124
    finally:
        if args.result_json:
            report = (repeated_pacing_result(runs, args.repeat, source_hash) if args.probe == "ga102_metal_present"
                      else repeated_core_result(args.probe, runs, args.repeat, source_hash) if args.probe in CORE_PROBES
                      else repeated_result(runs, args.repeat, source_hash, args.negative_control))
            if args.probe == "ga102_metal_present":
                report['pacing'] = 'AppKit display link' if args.display_linked else '60 Hz timer'
            if args.probe == 'ga102_visual_present':
                report['capture_method'] = 'ScreenCaptureKit owned-window broker' if args.capture_bridge else 'ScreenCaptureKit in probe'
                if capture_source_hash: report['capture_helper_source_sha256'] = capture_source_hash
            with args.result_json.open("x") as output:
                json.dump(report, output, indent=2, sort_keys=True, allow_nan=False)
                output.write("\n")
            print("Scoped results saved; physical scanout and desktop smoothness remain NOT VERIFIED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
