"""Read-only Windows Core Audio signal for the verified NetEase client."""
import ctypes as c
from contextlib import ExitStack
import math
import sys
from uuid import UUID

_P = c.c_void_p
_U = c.c_uint
_L = c.c_long
_PATH = r"C:\Program Files\Netease\CloudMusic\cloudmusic.exe".casefold()


def _guid(value):
    return (c.c_ubyte * 16).from_buffer_copy(UUID(value).bytes_le)


def _call(p, slot, types, *args):
    method = c.cast(p, c.POINTER(c.POINTER(_P)))[0][slot]
    return c.WINFUNCTYPE(_L, _P, *types)(method)(p, *args)


def _own(stack, p):
    if not p:
        raise OSError("Core Audio returned an empty interface")
    stack.callback(_call, p, 2, [])
    return p


def _interface(stack, p, slot, types, *args):
    child = _P()
    if _call(p, slot, [*types, c.POINTER(_P)], *args, c.byref(child)) != 0:
        raise OSError("Core Audio interface unavailable")
    return _own(stack, child)


def _installed_client(pid):
    kernel = c.WinDLL("kernel32", use_last_error=True)
    open_process = kernel.OpenProcess
    open_process.argtypes = (_U, c.c_int, _U)
    open_process.restype = _P
    query = kernel.QueryFullProcessImageNameW
    query.argtypes = (_P, _U, c.POINTER(c.c_wchar), c.POINTER(_U))
    query.restype = c.c_int
    close = kernel.CloseHandle
    close.argtypes = (_P,)
    close.restype = c.c_int
    handle = open_process(0x1000, False, pid)
    if not handle:
        return False
    try:
        buffer = c.create_unicode_buffer(32768)
        size = _U(len(buffer))
        return bool(query(handle, 0, buffer, c.byref(size))) and buffer.value.casefold() == _PATH
    finally:
        close(handle)


def active_cloudmusic_pids():
    """Return confirmed audible cloudmusic PIDs, never a play/pause verdict."""
    if sys.platform != "win32":
        return set()
    ole = c.windll.ole32
    # A compatible existing MTA returns S_FALSE; both successful calls balance.
    if ole.CoInitializeEx(None, 0) not in (0, 1):
        return set()
    active = set()
    try:
        with ExitStack() as root:
            enumerator = _P()
            if ole.CoCreateInstance(
                _guid("bcde0395-e52f-467c-8e3d-c4579291692e"), None, 23,
                _guid("a95664d2-9614-4f35-a746-de8db63617e6"), c.byref(enumerator)
            ) != 0:
                return set()
            _own(root, enumerator)
            devices = _interface(root, enumerator, 3, [_L, _U], 0, 1)
            count = _U()
            if _call(devices, 3, [c.POINTER(_U)], c.byref(count)) != 0:
                return set()
            for idx in range(min(count.value, 64)):
                try:
                    with ExitStack() as endpoint:
                        device = _interface(endpoint, devices, 4, [_U], idx)
                        manager = _interface(endpoint, device, 3, [_P, _U, _P],
                                             _guid("77aa99a0-1bd6-484f-8bc7-2c654c9a9b6f"), 23, None)
                        sessions = _interface(endpoint, manager, 5, [])
                        n = _L()
                        if _call(sessions, 3, [c.POINTER(_L)], c.byref(n)) != 0:
                            continue
                        for j in range(min(n.value, 1024)):
                            try:
                                with ExitStack() as scope:
                                    s = _interface(scope, sessions, 4, [_L], j)
                                    state = _L()
                                    if _call(s, 3, [c.POINTER(_L)], c.byref(state)) != 0 or state.value != 1:
                                        continue
                                    s2 = _interface(scope, s, 0, [_P],
                                                    _guid("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d"))
                                    pid = _U()
                                    if (_call(s2, 14, [c.POINTER(_U)], c.byref(pid)) != 0
                                            or pid.value in active or not _installed_client(pid.value)):
                                        continue
                                    meter = _interface(scope, s, 0, [_P],
                                                       _guid("c02216f6-8c67-4b5b-9d00-d008e73e0064"))
                                    peak = c.c_float()
                                    if (_call(meter, 3, [c.POINTER(c.c_float)], c.byref(peak)) == 0
                                            and math.isfinite(peak.value) and peak.value > 0):
                                        active.add(pid.value)
                            except OSError:
                                continue
                except OSError:
                    continue
    except OSError:
        pass
    finally:
        ole.CoUninitialize()
    return active
