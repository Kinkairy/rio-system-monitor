"""Diagnostic error attribution on the real unchanged host initialization code."""
from pathlib import Path
import importlib.util
import struct
import unittest
import zlib
import ast
import types
from rio_monitor.winusb import WinUSB

ROOT=Path(__file__).resolve().parents[1]
# Execute the original initializer and capability validator verbatim from AST.
# Isolate this USB-only unit from Pillow/GUI dependencies; no statement is edited.
source=ROOT/'src/rio_monitor/lt168b_display.py'
tree=ast.parse(source.read_text())
validator=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='validate_hello')
adapter=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LT168BBenchProtocol')
initializer=next(n for n in adapter.body if isinstance(n,ast.FunctionDef) and n.name=='initialize')
namespace=dict(HELLO=struct.Struct('<4sHHHHHHIIII'),UnsupportedDisplay=RuntimeError,zlib=zlib)
exec(compile(ast.Module(body=[validator,initializer],type_ignores=[]),str(source),'exec'),namespace)
def make_adapter(factory):
    a=types.SimpleNamespace(transport=factory('offline'),session_factory=lambda:918)
    a.initialize=types.MethodType(namespace['initialize'],a)
    return a
spec=importlib.util.spec_from_file_location('usb_diagnostics',ROOT/'tools/lt168b_usb_diagnostics.py')
diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)


class FakeAPI:
    def __init__(self, transport): self.t=transport
    def WinUsb_ResetPipe(self, handle, endpoint): return self.t.event('reset_'+str(endpoint))
    def WinUsb_FlushPipe(self, handle, endpoint): return self.t.event('flush_'+str(endpoint))


class FakeTransport:
    def __init__(self, fail=None):
        self.fail, self.calls, self.closed = fail, [], False
        self.u=FakeAPI(self);self.handle=None;self.endpoints=(1,0x82)
    def event(self,name):
        self.calls.append(name)
        if self.fail==name:
            e=OSError(121,'injected timeout');e.winerror=121
            e.usb_api=name;e.usb_endpoint=0;e.usb_requested=32;e.usb_reported=0
            raise e
        return True
    def control(self,t,r,v,i,n):
        self.event('control_'+str(r))
        if r==0x53:return b''
        payload=struct.pack('<4sHHHHHHIII',b'RIO1',1,32,480,480,32,16,3,1048,460800)
        return payload+struct.pack('<I',zlib.crc32(payload))
    reset_pipes=WinUSB.reset_pipes
    def write(self,ep,data):self.event('write');return len(data)
    def read(self,ep,n):self.event('read');return b'\0'*n
    def close(self):self.event('close');self.closed=True


class DiagnosticTests(unittest.TestCase):
    def test_exact_initializer_order_and_no_additional_io(self):
        original=FakeTransport();events=[]
        a=make_adapter(diag.traced_factory(lambda path:original,diag.CallLog(events.append)))
        a.initialize();a.initialize()
        self.assertEqual(original.calls,2*['control_82','reset_1','reset_130','flush_130','control_83'])
        self.assertTrue(a.ready);self.assertEqual(a.session,918)
        self.assertEqual(len([x for x in events if x['state']=='complete']),11)
        self.assertIsInstance(original.u,FakeAPI)

    def test_each_initialization_failure_stops_without_retry_and_restores_api(self):
        order=['control_82','reset_1','reset_130','flush_130','control_83']
        for failure in order:
            with self.subTest(failure=failure):
                original=FakeTransport(failure);events=[]
                a=make_adapter(diag.traced_factory(lambda p:original,diag.CallLog(events.append)))
                with self.assertRaises(OSError) as caught:a.initialize()
                self.assertEqual(original.calls,order[:order.index(failure)+1])
                self.assertEqual(caught.exception.winerror,121)
                errors=[e for e in events if e['state']=='error']
                self.assertEqual(len(errors),1);self.assertEqual(errors[0]['usb_api'],failure)
                self.assertFalse(a.ready);self.assertIsInstance(original.u,FakeAPI)

    def test_first_write_and_ack_error_metadata(self):
        for failure in ('write','read'):
            with self.subTest(failure=failure):
                original=FakeTransport(failure);events=[];t=diag.TracedTransport(original,diag.CallLog(events.append))
                with self.assertRaises(OSError):
                    if failure=='write':t.write(1,b'private pixel data')
                    else:t.read(0x82,24)
                self.assertEqual(events[-1]['winerror'],121)
                self.assertEqual(events[-1]['usb_reported'],0)
                self.assertNotIn('private pixel data',str(events))
                self.assertEqual(original.calls,[failure])

    def test_logging_failure_never_hides_usb_failure(self):
        def sink(event):
            if event['state']=='error':raise ValueError('log failed')
        expected=OSError(121,'USB failed')
        def fail():raise expected
        with self.assertRaises(OSError) as caught:diag.CallLog(sink).call('control',fail)
        self.assertIs(caught.exception,expected)

    def test_false_native_pipe_return_records_exact_api_and_endpoint(self):
        from unittest.mock import patch
        for name,endpoint in [('WinUsb_ResetPipe',1),('WinUsb_ResetPipe',130),('WinUsb_FlushPipe',130)]:
            with self.subTest(api=name,endpoint=endpoint):
                api=types.SimpleNamespace(**{name:lambda h,e:False});events=[]
                with patch('ctypes.get_last_error',return_value=121,create=True):
                    with self.assertRaises(OSError) as caught:
                        getattr(diag._ResetAPI(api,diag.CallLog(events.append)),name)(None,endpoint)
                self.assertEqual(caught.exception.winerror,121)
                self.assertEqual(events[-1]['usb_api'],name)
                self.assertEqual(events[-1]['usb_endpoint'],endpoint)

    def test_open_failure_remains_explicitly_unattributed_inside_constructor(self):
        events=[]
        def failure(path):raise OSError(121,'constructor failed')
        with self.assertRaises(OSError):diag.traced_factory(failure,diag.CallLog(events.append))('offline')
        self.assertEqual(events[-1]['stage'],'open_transport')
        self.assertNotIn('usb_api',events[-1])

    def test_budget_stops_before_io(self):
        calls=[];log=diag.CallLog(lambda e:None,limit=1)
        log.call('first',lambda:calls.append(1))
        with self.assertRaises(RuntimeError):log.call('second',lambda:calls.append(2))
        self.assertEqual(calls,[1])


if __name__=='__main__':unittest.main()
