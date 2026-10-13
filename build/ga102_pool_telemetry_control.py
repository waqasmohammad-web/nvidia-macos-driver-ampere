"""Explicit timing-off control for a copied diagnostic plugin; never production."""
from pathlib import Path

START='static _Atomic uint64_t ga102_pool_requests, ga102_pool_failures;'
SIGNATURE='static int pool_buffer_create_in(int vram, size_t size, nvk_buffer *out)\n{'
END='static int pool_buffer_create(size_t size, nvk_buffer *out) {'
UNAVAILABLE='''__attribute__((visibility("default"))) const char *ga102_perf_pool_trace(void) {
    return "{\\"available\\":false,\\"control\\":\\"pool timers disabled\\"}";
}
'''


def disable(copied, production):
    for text,marker in ((copied,START),(copied,END),(production,SIGNATURE),(production,END)):
        if text.count(marker)!=1:raise ValueError('pool timing control site changed')
    body=production[production.index(SIGNATURE):production.index(END)]
    return copied[:copied.index(START)]+body+copied[copied.index(END):]


def disable_export(unit, export):
    if unit.count(export)!=1:raise ValueError('pool trace export site changed')
    return unit.replace(export,UNAVAILABLE)
