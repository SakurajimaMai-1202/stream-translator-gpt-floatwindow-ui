r"""Standalone Windows GPU VRAM check for a packaged Stream Translator runtime.

Copy this file next to StreamTranslator.exe and run:
    .\_runtime\python.exe .\check_dxgi_vram.py
No third-party packages, network access, or app configuration are required.
"""

import ctypes
import json
import os
import sys


class Guid(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16),
                ("data3", ctypes.c_uint16), ("data4", ctypes.c_ubyte * 8)]


class Luid(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_int32)]


class AdapterDesc1(ctypes.Structure):
    _fields_ = [("description", ctypes.c_wchar * 128),
                ("vendor_id", ctypes.c_uint32), ("device_id", ctypes.c_uint32),
                ("subsys_id", ctypes.c_uint32), ("revision", ctypes.c_uint32),
                ("dedicated_video_memory", ctypes.c_size_t),
                ("dedicated_system_memory", ctypes.c_size_t),
                ("shared_system_memory", ctypes.c_size_t),
                ("adapter_luid", Luid), ("flags", ctypes.c_uint32)]


def com_method(pointer, slot, result_type, *argument_types):
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *argument_types)(vtable[slot])


def detect_adapters():
    if os.name != "nt":
        raise RuntimeError("This check must run on Windows.")

    iid = Guid(0x770AAE78, 0xF26F, 0x4DBA,
               (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))
    factory = ctypes.c_void_p()
    create = ctypes.WinDLL("dxgi.dll").CreateDXGIFactory1
    create.argtypes = (ctypes.POINTER(Guid), ctypes.POINTER(ctypes.c_void_p))
    create.restype = ctypes.c_long
    result = create(ctypes.byref(iid), ctypes.byref(factory))
    if result != 0 or not factory.value:
        raise RuntimeError("CreateDXGIFactory1 failed: 0x%08X" % (result & 0xFFFFFFFF))

    adapters = []
    try:
        enum_adapters = com_method(factory, 12, ctypes.c_long, ctypes.c_uint32,
                                   ctypes.POINTER(ctypes.c_void_p))
        for index in range(32):
            adapter = ctypes.c_void_p()
            if enum_adapters(factory, index, ctypes.byref(adapter)) != 0:
                break
            try:
                desc = AdapterDesc1()
                get_desc = com_method(adapter, 10, ctypes.c_long, ctypes.POINTER(AdapterDesc1))
                if get_desc(adapter, ctypes.byref(desc)) != 0 or desc.flags & 2:
                    continue
                adapters.append({
                    "name": desc.description.rstrip("\x00"),
                    "dedicated_vram_mib": desc.dedicated_video_memory // (1024 * 1024),
                    "vendor_id": "%04X" % desc.vendor_id,
                    "device_id": "%04X" % desc.device_id,
                })
            finally:
                if adapter.value:
                    com_method(adapter, 2, ctypes.c_ulong)(adapter)
    finally:
        com_method(factory, 2, ctypes.c_ulong)(factory)
    return adapters


def main():
    try:
        adapters = detect_adapters()
    except Exception as exc:
        print("DXGI GPU check failed:", repr(exc))
        return 1
    print(json.dumps({"dxgi_adapters": adapters}, ensure_ascii=False, indent=2))
    matching = [item for item in adapters if "9070" in item["name"].lower()]
    if matching:
        best = max(item["dedicated_vram_mib"] for item in matching)
        print("\nRX 9070 detected: %d MiB dedicated VRAM (%.1f GiB)." % (best, best / 1024))
        print("Simple mode VRAM tier: %s." % ("8 GB or more" if best >= 8192 else "below 8 GB"))
    else:
        print("\nRX 9070 was not returned by DXGI. Please send the full output above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
