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
    from .ga102_presentation_trace import analyze as analyze_trace
    from .ga102_ca_validation import evaluate as evaluate_ca, repeated_ca_result
    from .ga102_stream_capture import StreamBroker
except ImportError:
    from ga102_visual_validation import evaluate as evaluate_visual, repeated_result
    from ga102_pacing_validation import evaluate as evaluate_pacing, repeated_pacing_result
    from ga102_core_validation import CORE_PROBES, FIELDS, evaluate as evaluate_core, repeated_core_result
    from ga102_capture_bridge import CaptureBroker
    from ga102_presentation_trace import analyze as analyze_trace
    from ga102_ca_validation import evaluate as evaluate_ca, repeated_ca_result
    from ga102_stream_capture import StreamBroker

ROOT = Path(__file__).resolve().parent.parent
PROBES = ("ga102_metal_smoketest", "ga102_metal_render_smoketest", "ga102_metal_benchmark",
          "ga102_metal_memory", "ga102_metal_present", "ga102_metal_composite", "ga102_metal_crossprocess", "ga102_metal_events", "ga102_core_animation", "ga102_visual_present", "ga102_ca_visual")
# IOSurface creation can implicitly enumerate Metal devices and load the installed
# bundle. Until class isolation exists, refuse those workloads before launch.
ISOLATED_PROBES = ('ga102_metal_smoketest', 'ga102_metal_render_smoketest',
                   'ga102_metal_events', 'ga102_metal_memory')


def isolated_source(source):
    """Shadow enumeration only in the compiled snapshot; never edit the probe."""
    if source.count(b'MTLCopyAllDevices()') != 1 or b'MTLCreateSystemDefaultDevice' in source:
        raise ValueError('isolated probe must contain one explicit enumeration site')
    prefix = b'''import Metal
@_silgen_name("ga102_bound_device") private func ga102BoundDevicePointer() -> UnsafeMutableRawPointer
private let ga102ExplicitDevice = Unmanaged<AnyObject>.fromOpaque(ga102BoundDevicePointer()).takeRetainedValue() as! any MTLDevice
private let MTLCopyAllDevices: () -> [any MTLDevice] = { [ga102ExplicitDevice] }
'''
    return prefix + source


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
    parser.add_argument('--plugin', type=Path, help='Explicit process-local plugin binding for offscreen probes only; never installs a component')
    parser.add_argument("--surface-comparison", action="store_true", help="Benchmark matching BGRA8 targets at 3440x1440 only")
    parser.add_argument("--graphics-copy-queue", action="store_true", help="Attempt test-process-only NVRM_610_CECHAN=0; verify engine selection in logs (installed builds may differ)")
    parser.add_argument("--negative-control", choices=("static", "timestamps", "hidden"))
    parser.add_argument("--display-linked", action="store_true")
    parser.add_argument("--drawable-paced", action="store_true", help="Continuous Metal control: drawable/GPU-completion paced; no extra sleep or display-link wait")
    parser.add_argument("--runloop-trace", action="store_true", help="Bounded own-client run-loop and framework event timings; no input-event recording")
    parser.add_argument("--reference-only", action="store_true", help="CA comparison without extra animated layers")
    parser.add_argument("--first-frame-half-period", action="store_true", help="Timing-only startup phase control; shifts first client draw by 8.333 ms")
    parser.add_argument("--double-buffered", action="store_true", help="Use two drawables in this probe's CAMetalLayer only; no framebuffer/display changes")
    parser.add_argument('--continuous', action='store_true', help='120 CA or Metal reference frames with one owned-window SCStream')
    parser.add_argument('--onscreen-every-frame', action='store_true', help='Diagnostic control: synchronous session/window queries on every continuous CA frame')
    parser.add_argument('--capture-disabled', action='store_true', help='Continuous Metal control: do not start capture; full visual capture validation cannot pass')
    parser.add_argument('--capture-metadata-only', action='store_true', help='Continuous Metal control: capture metadata without pixel-buffer CPU access; content NOT VERIFIED')
    parser.add_argument("--capture-bridge", action="store_true", help="Capture only the owned visual window via ScreenCaptureKit in this Python process; never requests permission")
    parser.add_argument("--result-json", type=Path, help="Save scoped visual-probe verdicts and numeric metrics, excluding raw logs and machine identities")
    args = parser.parse_args()
    if args.plugin and (args.probe not in ISOLATED_PROBES or args.capture_bridge):
        parser.error('--plugin requires a verified offscreen probe without IOSurface/capture')
    if args.plugin and (not args.plugin.is_file() or args.plugin.name != 'NVMTLDriver'):
        parser.error('--plugin must name an existing NVMTLDriver binary')
    if args.continuous and (args.probe not in ('ga102_ca_visual','ga102_visual_present') or not args.capture_bridge):
        parser.error('--continuous requires an owned-window visual probe --capture-bridge')
    if args.onscreen_every_frame and (not args.continuous or args.probe != 'ga102_ca_visual'):
        parser.error('--onscreen-every-frame requires ga102_ca_visual --continuous')
    if args.capture_disabled and (not args.continuous or args.probe != 'ga102_visual_present'):
        parser.error('--capture-disabled requires ga102_visual_present --continuous')
    if args.capture_metadata_only and (not args.continuous or args.probe != 'ga102_visual_present' or args.capture_disabled):
        parser.error('--capture-metadata-only requires continuous Metal capture enabled')
    if args.capture_bridge and args.probe not in ('ga102_visual_present', 'ga102_ca_visual'):
        parser.error('--capture-bridge requires an owned-window visual probe')
    if args.result_json and args.probe not in (*CORE_PROBES, "ga102_visual_present", "ga102_metal_present", "ga102_ca_visual"):
        parser.error("--result-json requires a core correctness or presentation probe")
    if args.result_json and args.result_json.exists():
        parser.error("--result-json must name a new file; existing evidence is never overwritten")
    if args.drawable_paced and (args.probe != 'ga102_visual_present' or not args.continuous or args.display_linked):parser.error('--drawable-paced requires continuous Metal and excludes --display-linked')
    if args.runloop_trace and (args.probe != 'ga102_visual_present' or not args.continuous):parser.error('--runloop-trace requires continuous Metal visual probe')
    if args.reference_only and args.probe != 'ga102_ca_visual':parser.error('--reference-only requires CA probe')
    if args.display_linked and not (args.probe == 'ga102_metal_present' or args.probe in ('ga102_visual_present','ga102_ca_visual') and args.continuous):
        parser.error('--display-linked requires a pacing probe or continuous visual probe')
    if args.first_frame_half_period and (args.probe != 'ga102_metal_present' or not args.display_linked):parser.error('--first-frame-half-period requires linked timing probe')
    if args.double_buffered and args.probe != 'ga102_metal_present':
        parser.error('--double-buffered requires ga102_metal_present')
    if args.negative_control and args.probe not in ('ga102_visual_present', 'ga102_ca_visual'):
        parser.error('--negative-control requires an owned-window visual probe')
    if args.probe == 'ga102_ca_visual' and args.negative_control == 'timestamps':
        parser.error('Core Animation probe does not claim presentation timestamps')
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
    original_source_hash = hashlib.sha256(source_bytes).hexdigest()
    plugin_hash = None
    binding_hash = None
    if args.plugin:
        plugin_hash = hashlib.sha256(args.plugin.read_bytes()).hexdigest()
        env['GA102_PLUGIN_IMAGE'] = str(args.plugin.resolve())
        source_bytes = isolated_source(source_bytes)
    compile_input = scratch / f'{args.probe}.swift'
    compile_input.write_bytes(source_bytes)
    compile_command = ["xcrun", "swiftc", "-O", "-module-cache-path", str(scratch / "modules"),
                       str(compile_input), "-o", str(executable)]
    runs = []
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    capture_source_hash = None
    try:
        if args.plugin:
            binding_bytes = (ROOT / 'tools/ga102_isolated_plugin_probe.m').read_bytes()
            binding_hash = hashlib.sha256(binding_bytes).hexdigest()
            binding_source = scratch / 'binding.m'; binding_source.write_bytes(binding_bytes)
            binding_object = scratch / 'binding.o'
            with (scratch / 'binding-compile.log').open('w') as log:
                code = run_owned(['xcrun', 'clang', '-fobjc-arc', '-O1', '-Wall', '-Wextra', '-Werror',
                                  '-DGA102_BINDING_ONLY=1', '-c', str(binding_source), '-o', str(binding_object)], log, 60)
            if code:
                print('FAIL: explicit binding helper compilation; details retained privately', flush=True)
                return code
            compile_command += [str(binding_object), '-framework', 'IOKit']
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
            command.extend(['-framework','CoreMedia','-framework','CoreVideo'])
            with (scratch / 'capture-compile.log').open('w') as log:
                code = run_owned(command, log, 60)
            if code:
                print('BLOCKED: own-window capture helper did not compile; details in private scratch', flush=True)
                return code
        for iteration in range(args.repeat):
            output = scratch / f"run-{iteration + 1}.log"
            before = display_counters() if args.probe in ("ga102_metal_present", "ga102_visual_present", "ga102_ca_visual") else {}
            broker = None
            if args.capture_bridge:
                channel = scratch / f'capture-{iteration}'; channel.mkdir(mode=0o700)
                broker = (StreamBroker(capture_library,channel,not args.capture_metadata_only) if args.continuous else CaptureBroker(capture_library,channel))
                env['GA102_CAPTURE_IPC'] = str(channel)
                env['GA102_CAPTURE_PERMISSION'] = '1' if broker.allowed else '0'
            with output.open("w") as log:
                command = [str(executable)] + (["--surface-comparison"] if args.surface_comparison else [])
                if args.display_linked:
                    command.append("--display-linked")
                if args.double_buffered:
                    command.append('--double-buffered')
                if args.first_frame_half_period:command.append('--first-frame-half-period')
                if args.drawable_paced:command.append('--drawable-paced')
                if args.runloop_trace:command.append('--runloop-trace')
                if args.reference_only: command.append('--reference-only')
                if args.continuous: command.append('--continuous')
                if args.onscreen_every_frame: command.append('--onscreen-every-frame')
                if args.capture_disabled: command.append('--capture-disabled')
                if args.negative_control:
                    command.append(args.negative_control)
                try:
                    code = (run_owned(command, log, 45, env, broker.poll) if broker else run_owned(command, log, 45, env))
                finally:
                    if isinstance(broker, StreamBroker): broker.close()
            probe_exit_code = code
            if args.probe in ("ga102_metal_present", "ga102_visual_present", "ga102_ca_visual"):
                correlation = display_delta(before, display_counters())
                print("result: " + json.dumps({"display_correlation": correlation}, sort_keys=True), flush=True)
            print(f"Run {iteration + 1}: exit {code}", flush=True)
            # Avoid copying paths, addresses and process identities from driver logs
            # into public reports; print only probe-owned result lines here.
            lines = output.read_text(errors="replace").splitlines()
            if args.plugin and (lines.count('binding_verified: true') != 1 or
                                hashlib.sha256(args.plugin.read_bytes()).hexdigest() != plugin_hash):
                print('FAIL: explicit plugin provenance missing or binary changed', flush=True)
                code = probe_exit_code = 1
            for line in lines:
                if args.probe in ('ga102_metal_present','ga102_ca_visual') or args.continuous:
                    if not line.startswith('result: '):
                        if line.startswith(('PASS','FAIL','NOT VERIFIED','device:')): print(line,flush=True)
                        continue
                    summary = json.loads(line[8:])
                    for key in ('frame_trace', 'presented_times', 'presented_frame_ids','samples','runloop_long_gaps','owned_window_event_spans','owned_application_event_spans'):
                        if key in summary: summary[key] = 'full data retained in private log/result artifact'
                    if 'stream_analysis' in summary:
                        summary['stream_analysis'].pop('captured_changes',None)
                    print('result: ' + json.dumps(summary, sort_keys=True), flush=True)
                    continue
                if line.startswith(("Metal GPU:", "Computed values:", "Center pixel", "PASS", "FAIL", "NOT VERIFIED", "BLOCKED",
                                    "device:", "device_creation_ms:", "library_creation_ms:",
                                    "pipeline_creation_ms_in_order:", "result:")):
                    print(line, flush=True)
            if args.probe == 'ga102_ca_visual':
                verdict = None
                metrics = {}
                for line in lines:
                    if line.startswith('result: '):
                        evidence = json.loads(line[8:])
                        if evidence.get('probe') == 'ca_visual':
                            metrics = {key: evidence[key] for key in ('frames', 'transactions', 'preflight_ready',
                                'visible_frames', 'capture_permission', 'capture_attempted', 'capture_received_frames',
                                'capture_correct_frames', 'capture_distinct_patterns', 'samples', 'continuous',
                                'stream_started', 'stream_analysis','full_visibility_samples','onscreen_query_every_frame','display_linked','reference_only','missed_display_ticks') if key in evidence}
                            verdict = evaluate_ca(evidence, correlation)
                            print('result: ' + json.dumps(verdict, sort_keys=True), flush=True)
                            if verdict['automated_ca_validation'] == 'FAIL': code = 1
                runs.append(dict(exit_code=probe_exit_code, validation_exit_code=code, metrics=metrics, verdict=verdict or {}, display_correlation=correlation))
            elif args.probe == "ga102_visual_present":
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
                            metrics.update({key:evidence[key] for key in ('continuous','stream_started','stream_analysis',
                                'full_visibility_samples','steady_reported_presentation','display_linked',
                                'missed_display_ticks','frame_trace','drawable_paced','pipeline_initialization_ms','runloop_trace_enabled','runloop_long_gaps','runloop_event_count','runloop_overflow','owned_window_event_count','owned_window_event_spans','owned_window_event_overflow','owned_application_event_spans','owned_application_event_count','owned_application_event_overflow','application_dispatcher_instrumented') if key in evidence})
                            if 'capture_disabled_control' in evidence:metrics['capture_disabled_control']=evidence['capture_disabled_control']
                            verdict = evaluate_visual(evidence, correlation)
                            print("result: " + json.dumps(verdict, sort_keys=True), flush=True)
                            if verdict["automated_visual_validation"] == "FAIL":
                                code = 1
                runs.append({"exit_code": probe_exit_code, "validation_exit_code": code, "metrics": metrics, "verdict": verdict or {},
                             "display_correlation": correlation})
            elif args.probe in CORE_PROBES:
                records = [{k: v for k, v in json.loads(line[8:]).items() if k in FIELDS}
                           for line in lines if line.startswith('result: ')]
                verdict = evaluate_core(args.probe, records, code)
                print('result: ' + json.dumps(verdict, sort_keys=True), flush=True)
                if verdict['automated_core_validation'] == 'FAIL':
                    code = 1
                runs.append({'exit_code': probe_exit_code, 'validation_exit_code': code, 'metrics': records, 'verdict': verdict})
            elif args.probe == "ga102_metal_present":
                verdict = None
                metrics = {}
                for line in lines:
                    if line.startswith("result: "):
                        evidence = json.loads(line[8:])
                        if evidence.get("probe") == "pacing":
                            keys = ("attempted", "completed", "command_errors", "outstanding", "timer_skips",
                                    "preflight_ready", "preflight_wait_ms",
                                    "frame_trace",
                                    "drawable_count",
                                    "display_width", "display_height", "display_refresh_hz",
                                    "positive_presented_times", "presented_frame_ids", "presented_times",
                                    "visibility_samples", "presentation_intervals", "drawable_acquisition", "gpu",
                                    "cpu_draw_intervals", "encode", "commit_return", "commit_to_scheduled_callback",
                                    "commit_to_completed_callback", "late_frame_correlations")
                            metrics = {key: evidence[key] for key in keys if key in evidence}
                            verdict = evaluate_pacing(evidence, correlation)
                            verdict['submission_trace'] = analyze_trace(evidence)
                            print("result: " + json.dumps(verdict, sort_keys=True), flush=True)
                            if verdict["automated_pacing_validation"] == "FAIL":
                                code = 1
                runs.append({"exit_code": probe_exit_code, "validation_exit_code": code, "metrics": metrics, "verdict": verdict or {},
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
                      else repeated_ca_result(runs, args.repeat, source_hash, args.negative_control, args.continuous) if args.probe == 'ga102_ca_visual'
                      else repeated_core_result(args.probe, runs, args.repeat, source_hash) if args.probe in CORE_PROBES
                      else repeated_result(runs, args.repeat, source_hash, args.negative_control))
            if args.probe == "ga102_metal_present":
                report['pacing'] = 'AppKit display link' if args.display_linked else '60 Hz timer'
            if args.plugin:
                report['runtime'] = {'binding': 'explicit process-local user-space plugin',
                    'plugin_sha256': plugin_hash, 'binding_helper_source_sha256': binding_hash,
                    'original_probe_source_sha256': original_source_hash,
                    'installed_driver_changed': False,
                    'limits': 'installed kernel/NVK/translator retained; offscreen coverage only'}
            if args.probe in ('ga102_visual_present', 'ga102_ca_visual'):
                report['capture_method'] = 'ScreenCaptureKit owned-window broker' if args.capture_bridge else 'ScreenCaptureKit in probe'
                report['capture_mode'] = 'bounded SCStream' if args.continuous else 'held screenshot references'
                if args.capture_metadata_only:report['capture_mode']='bounded SCStream, metadata only'
                if args.continuous and args.probe == 'ga102_visual_present':report['scope']='120 encoded GPU/readback/presented frames and owned-window captured IDs; cadence evaluated separately'
                if capture_source_hash: report['capture_helper_source_sha256'] = capture_source_hash
            with args.result_json.open("x") as output:
                json.dump(report, output, indent=2, sort_keys=True, allow_nan=False)
                output.write("\n")
            print("Scoped results saved; physical scanout and desktop smoothness remain NOT VERIFIED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
