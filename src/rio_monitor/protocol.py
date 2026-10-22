"""Screen frame protocol based on static inspection. No firmware/resource writes."""
import struct

class ProtocolError(RuntimeError):pass

def frame_command(jpeg: bytes, tag: int, width=480, height=480):
    if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
        raise ValueError('A complete JPEG is required')
    if not 1 <= width <= 65536 or not 1 <= height <= 65536:
        raise ValueError('Invalid frame dimensions')
    if not 0 <= tag <= 0xffffffff or len(jpeg)>8*1024*1024:
        raise ValueError('Invalid tag or oversized frame')
    cdb=bytearray(16)
    cdb[0],cdb[5],cdb[6]=0xcd,0x06,0x30
    struct.pack_into('<HH',cdb,11,width-1,height-1)
    return struct.pack('<4sIIBBB16s',b'USBC',tag,len(jpeg),0,0,16,bytes(cdb))

def validate_status(raw:bytes,tag:int):
    if len(raw)!=13:raise ProtocolError('Status must be exactly 13 bytes')
    signature,got,residue,status=struct.unpack('<4sIIB',raw)
    if signature!=b'USBS':raise ProtocolError('Invalid status signature')
    if got!=tag:raise ProtocolError('Status tag mismatch')
    if residue!=0:raise ProtocolError('Incomplete payload transfer')
    if status!=0:raise ProtocolError(f'Device rejected frame: {status}')

class FrameSender:
    def __init__(self,transport):
        self.transport=transport
        self.tag=0
        self.faulted=False
    def send(self,jpeg):
        if self.faulted:raise ProtocolError('Transport stopped; reconnect explicitly')
        self.tag=(self.tag+1)&0xffffffff
        command=frame_command(jpeg,self.tag)
        try:
            for payload in (command,jpeg):
                if self.transport.write(0x01,payload)!=len(payload):
                    raise ProtocolError('Short write; frame outcome uncertain')
            validate_status(self.transport.read(0x81,13),self.tag)
        except Exception:
            self.faulted=True
            raise
