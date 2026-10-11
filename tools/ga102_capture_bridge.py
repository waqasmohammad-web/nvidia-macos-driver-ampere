"""Own-child ScreenCaptureKit broker. No images or window/process IDs in reports."""
import ctypes
import json
from pathlib import Path


def expected_samples(frame):
    result = []
    for cell in range(8):
        bit = [255] * 3 if (frame >> cell) & 1 else [0] * 3
        color = [255 if channel == frame % 3 else 0 for channel in range(3)]
        result += bit + ([255] * 3 if cell == frame % 8 else color) + color
    return result


def correct_samples(frame, samples):
    return len(samples) == 72 and all(abs(a - b) <= 40 for a, b in zip(samples, expected_samples(frame)))


class CaptureBroker:
    def __init__(self, library, directory):
        self.directory = Path(directory)
        self.library = ctypes.CDLL(str(library))
        self.library.ga102_capture_preflight.restype = ctypes.c_int
        self.library.ga102_capture_window.argtypes = [ctypes.c_uint, ctypes.c_int,
                                                     ctypes.POINTER(ctypes.c_ubyte), ctypes.c_size_t]
        self.library.ga102_capture_window.restype = ctypes.c_int
        self.library.ga102_capture_conversion_control.restype = ctypes.c_int
        self.allowed = self.library.ga102_capture_preflight() == 1
        if self.library.ga102_capture_conversion_control() != 0:
            raise RuntimeError('independent CPU capture conversion control failed')
        self.signatures = set()

    def poll(self, child):
        request = self.directory / 'request.json'
        if not request.exists(): return
        data = json.loads(request.read_text())
        frame = data.get('frame')
        # The child owns this private channel. Do not accept another process ID.
        if data.get('pid') != child.pid or not isinstance(frame, int) or not 0 <= frame < 12:
            raise ValueError('capture request does not identify the owned probe child')
        request.unlink()
        samples = (ctypes.c_ubyte * 72)()
        window_id = data.get('window_id')
        code = (self.library.ga102_capture_window(window_id, child.pid, samples, 72)
                if self.allowed and isinstance(window_id, int) and window_id > 0
                else -4 if self.allowed else -1)
        received = code == 0
        if received: self.signatures.add(tuple(samples))
        else: self.allowed = False  # Do not repeatedly invoke a blocked/failed capture API.
        response = dict(received=received, correct=received and correct_samples(frame, samples),
                        distinct_patterns=len(self.signatures), code=code,
                        samples=list(samples) if received else [])
        temporary = self.directory / 'response.tmp'
        temporary.write_text(json.dumps(response))
        temporary.replace(self.directory / f'response-{frame}.json')
