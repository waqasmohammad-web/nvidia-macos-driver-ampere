# RTX 3080 Ti (GA102) on macOS Sequoia — development baseline

This is an **experimental, unvalidated** hardware test log for PCI ID `10de:2208`. It is not evidence of functioning NVIDIA acceleration.

## Test machine

- CPU: Intel Core i9-12900K (Alder Lake)
- Board: MSI MAG Z690 Tomahawk WiFi DDR4
- GPU: desktop GeForce RTX 3080 Ti (12 GB), PCI vendor `0x10de`, device `0x2208`, revision `0x00a1`
- OS: freshly installed macOS 15 Sequoia via OpenCore 1.0.8
- Display: 3440 x 1440, single active display
- Driver state at baseline: third-party NVIDIA driver **not loaded**

## Observed baseline (driver not loaded)

```text
Type: GPU
Bus: PCIe
PCIe Lane Width: x16
VRAM (Total): 22 MB
Vendor: NVIDIA (0x10de)
Device ID: 0x2208
Revision ID: 0x00a1
Kernel Extension Info: No Kext Loaded
Display Resolution: 3440 x 1440
Framebuffer Depth: 24-Bit Color (ARGB8888)
```

The 22 MB value is the display information reported by macOS in the unaccelerated state; it is **not** the card's physical VRAM capacity.

## Previous experimental driver attempt

- After installation, About This Mac reported the GPU name and 12 GB of VRAM.
- A display-resolution change was followed by a black desktop with a visible cursor; reboot did not restore visible login UI.
- NVIDIA driver removal / clean OS reinstall was used to recover.
- **Metal device availability, actual acceleration, driver release, requested mode and kernel logs were not captured for that attempt.** Do not presume a particular cause or claim the driver previously worked.

## Successful driver startup: 1.11.0 (macOS 15.8.1)

After reinstalling the NVIDIA driver via 1401 1.11.0, the user reports a functioning graphical desktop with the following state:

- 1401 Mac app: **NullMoth driver running**
- Reported renderer: `NVIDIA GeForce RTX 3080 Ti (NVMTL over NVIDIA GeForce RTX 3080 Ti (NVK GA102-A))`
- System Report: **12 GB VRAM** recognised, PCI `10de:2208`, revision `00a1`, PCIe x16
- System Report: **Metal Support: Metal 3**
- One DisplayPort-connected ultrawide at **3440 × 1440, 60.00 Hz**, 24-bit framebuffer
- OpenCore: `DBG-108-2026-09-27`
- 1401 installer preflight: package SHA-256 checked; test kernel collection accepted all four kexts; internal EFI identified and backed up
- GPU kext `kmutil` listing **not yet captured after installation**
- Real Metal GPU workload **not yet independently tested**
- Other modes / refresh rates **not tested** on 1.11.0

**Interpretation:** This is confirmed startup/driver detection and Metal 3 advertisement on previously unvalidated GA102 hardware, not yet a verified rendering/compute benchmark or proof that display switching is fixed. Preserve 3440 × 1440 @ 60 Hz for a stable baseline and collect minimally invasive kext/Metal tests before attempting mode changes.

Private monitor serial number, Mac serial numbers and machine-specific identifiers are intentionally excluded from this public log.

## Loaded kernel-extension confirmation

The user subsequently ran `kmutil showloaded --list-only | grep -i nullmoth` on macOS 15.8.1 with driver 1.11.0. All four extensions were present:

```text
com.nullmoth.NVRMFB (0.1)       loaded
com.nullmoth.NVRMAGDC (0.1)     loaded
com.nullmoth.NVRM (0.1)         loaded
com.nullmoth.NVAccel (0.1)      loaded
```

This confirms extension loading, not that compute or rendering workloads are correct. The routine `No variant specified, falling back to release` message from `kmutil` is not a driver load failure.

## Metal device creation — warnings to investigate

A Swift Metal device-discovery test on Sequoia 15.8.1 with NullMoth 1.11.0 printed the following:

```text
nvrm: b81 PERF_BOOST flags 0x12 INFINITE rc 0x0
nvrm: b72 host-pointer import ON (probe NV_STATUS 0)
Failed to create /var/folders/zz/zyxvpxvq6csfxvn_n0000000000000/C/nvmtl-mesa for shader cache (Permission denied)---disabling.
nvrm: b80 LOCAL+mapped memory -> system RAM (b79 placement) (BAR1 8192 MB, VRAM 12288 MB, default)
MESA: warning: ../src/nouveau/vulkan/nvkmd/nvrm/nvkmd_nvrm_ctx.c:758: VK_ERROR_UNKNOWN
nvrm: copy-engine queue could not be built on this GPU (VkResult -13) - copy queue on a graphics channel
nvrm: b81 SET_LG_SECTOR_PROMOTION 64B rc 0x56
nvrm: b81 SET_LG_SECTOR_PROMOTION 64B rc 0x56
Metal GPU: NVIDIA GeForce RTX 3080 Ti (NVMTL over NVIDIA GeForce RTX 3080 Ti (NVK GA102-A))
```

**Result:** `MTLCreateSystemDefaultDevice()` returned a GPU device. This **does not** prove Metal command-buffer completion, accelerated WindowServer compositing, or correct shader output. The diagnostic errors are recorded without assigning causal responsibility for perceived desktop sluggishness. Shader-cache creation was denied; the copy-engine queue creation failed and the driver printed a graphics-queue fallback. Avoid changing display modes until actual GPU execution is tested.

## Metal compute smoke test: PASS

Executed `tools/ga102_metal_smoketest.swift` from commit `4f2c2589f7bf0d1bad8af5c143595e46e3f5d209` on macOS 15.8.1 with NullMoth 1.11.0. The driver repeated startup warnings (shader cache permission denied, Vulkan copy-engine queue fallback, sector-promotion NV status) but the Metal command buffer completed and returned correct GPU-computed values:

```text
Metal GPU: NVIDIA GeForce RTX 3080 Ti (NVMTL over NVIDIA GeForce RTX 3080 Ti (NVK GA102-A))
Submitting a four-element Metal compute workload...
Computed values: [2.0, 4.0, 6.0, 8.0]
PASS: Metal compute dispatch completed with correct results
```

**Validated:** Metal shader compilation and small compute dispatch with correct result readback. **Not yet validated:** render pipeline, WindowServer composition, display flips, performance, or higher refresh rates. User reports macOS desktop still feels less accelerated than past Hackintosh builds.

## First diagnostic goal

1. Record installed driver release and exact macOS build.
2. With the clean baseline running, retain a bootable known-good OpenCore recovery USB.
3. Install the unmodified upstream release before testing any source patch.
4. Without changing display mode or refresh rate, collect:
   - `system_profiler SPDisplaysDataType`
   - `kmutil showloaded --list-only | grep -i nullmoth` (expect NVRM, NVAccel, NVRMFB, NVRMAGDC when functioning)
   - System Report's Metal Support field
   - A small actual Metal workload if Metal appears supported
5. If driver startup fails, use 1401's diagnostic report (review/redact personal identifiers before sharing). Compare PCI ID `2208`, BAR mappings, firmware/GSP bring-up, and WindowServer / framebuffer startup messages.
6. **Only after acceleration and a stable baseline are observed**, attempt one controlled display-mode change with a known recovery route, then collect precise logs.

## Source areas to investigate after obtaining logs

- `kexts/NVRMFB/fb/nvrm-fb.cpp`: `setDisplayMode`, `switchMode`, EDID / timings and head/connector handling
- `kexts/NVRMFB/fb/nvrm-fb-safety.h`: pitch / aperture guards
- `kexts/NVRMAGDC/`: display-policy transitions
- `plugin/`: Metal device / command submission when the framebuffer is up

The existing upstream `app/Resources/nvidia_gsp_ids.json` already lists `"2208": "NVIDIA GeForce RTX 3080 Ti"`. **Do not add a duplicate device ID as a proposed fix.** Device-table coverage is not successful GPU initialization.

## Acceptance criteria

- Driver kexts actually load and remain loaded
- Metal is reported and a Metal workload completes correctly
- WindowServer stays stable after login
- Single-display native resolution remains usable at 60 Hz
- If a mode change fails, the failure is logged and recovery is available without reinstalling macOS

No kernel / graphics code changes should be merged based solely on GPU name or VRAM appearing in System Report.
