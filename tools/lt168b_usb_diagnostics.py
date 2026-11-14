"""Test-runner diagnostics; wrapping alone opens no device and retries nothing.

Do not install in the running RIO process. The caller owns the original transport,
authorization and close lifecycle. Records include metadata only, never payloads.
"""
import time


class CallLog:
    def __init__(self, sink, clock=time.perf_counter_ns, limit=4096):
        self.sink, self.clock, self.limit = sink, clock, limit
        self.sequence = 0

    def call(self, stage, operation, **metadata):
        if self.sequence >= self.limit:
            raise RuntimeError('Diagnostic call budget exhausted before device I/O')
        self.sequence += 1
        identity = dict(sequence=self.sequence, stage=stage, **metadata)
        start = self.clock()
        self.sink(dict(identity, state='begin', started_ns=start))
        try:
            value = operation()
        except Exception as error:
            details = {key: getattr(error, key) for key in (
                'winerror', 'errno', 'usb_api', 'usb_endpoint',
                'usb_requested', 'usb_reported') if hasattr(error, key)}
            # Preserve the original exception and its USB diagnostic attributes.
            # A logging failure must not hide the actual transport failure.
            try:
                self.sink(dict(identity, state='error', elapsed_ns=self.clock()-start,
                               exception_type=type(error).__name__, **details))
            except Exception:
                pass
            raise
        self.sink(dict(identity, state='complete', elapsed_ns=self.clock()-start,
                       returned_bytes=len(value) if isinstance(value, bytes) else
                       value if isinstance(value, int) else None))
        return value


class _ResetAPI:
    """Trace the original reset_pipes implementation without copying its logic."""
    def __init__(self, original, log):
        self.original, self.log = original, log

    def __getattr__(self, name):
        original = getattr(self.original, name)
        if name not in ('WinUsb_ResetPipe', 'WinUsb_FlushPipe'):
            return original
        def invoke(handle, endpoint):
            # Do not do any file/log I/O between a failed WinUSB call and the
            # original caller's GetLastError, except with explicit preservation.
            import ctypes
            def run():
                result = original(handle, endpoint)
                error = ctypes.get_last_error() if hasattr(ctypes, 'get_last_error') else 0
                if not result:
                    failure = ctypes.WinError(error) if hasattr(ctypes, 'WinError') else OSError(error, 'USB pipe operation failed')
                    failure.winerror = error
                    failure.usb_api, failure.usb_endpoint = name, endpoint
                    raise failure
                return result
            return self.log.call(name, run, endpoint=endpoint)
        return invoke


class TracedTransport:
    def __init__(self, original, log):
        self.original, self.log = original, log

    def __getattr__(self, name):
        return getattr(self.original, name)

    def control(self, request_type, request, value, index, length):
        return self.log.call('control', lambda: self.original.control(
            request_type, request, value, index, length), api='WinUsb_ControlTransfer',
            request_type=request_type, request=request, value=value, index=index,
            requested_bytes=length)

    def reset_pipes(self):
        previous = self.original.u
        self.original.u = _ResetAPI(previous, self.log)
        try:
            return self.original.reset_pipes()
        finally:
            self.original.u = previous

    def write(self, endpoint, payload):
        return self.log.call('bulk_write', lambda: self.original.write(endpoint, payload),
                             api='WinUsb_WritePipe', endpoint=endpoint, requested_bytes=len(payload))

    def read(self, endpoint, length):
        return self.log.call('bulk_read', lambda: self.original.read(endpoint, length),
                             api='WinUsb_ReadPipe', endpoint=endpoint, requested_bytes=length)

    def close(self):
        return self.log.call('close', self.original.close)


def traced_factory(factory, log):
    def create(path):
        # The path/handle is deliberately absent from output. A constructor
        # failure remains 'open_transport'; no invented inner API attribution.
        return TracedTransport(log.call('open_transport', lambda: factory(path)), log)
    return create
