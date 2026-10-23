"""Hardware-verified RGB565 framebuffer protocol. No persistent writes."""
import struct
from PIL import Image, ImageChops

class ProtocolError(RuntimeError):pass

def encode_rgb565(image):
    """Return big-endian RGB565 without a per-pixel Python loop."""
    red,green,blue=image.convert('RGB').split()
    high=ImageChops.add(red.point(lambda v:v & 0xf8),green.point(lambda v:v >> 5))
    low=ImageChops.add(green.point(lambda v:(v & 0x1c) << 3),blue.point(lambda v:v >> 3))
    return Image.merge('LA',(high,low)).tobytes()

def frame_command(pixels: bytes, tag: int, width=480, height=480):
    if not 1 <= width <= 65536 or not 1 <= height <= 65536:
        raise ValueError('Invalid frame dimensions')
    if not 0 <= tag <= 0xffffffff or len(pixels)>8*1024*1024:
        raise ValueError('Invalid tag or oversized frame')
    if len(pixels)!=width*height*2:raise ValueError('A complete RGB565 frame is required')
    cdb=bytearray(16)
    cdb[0],cdb[5],cdb[6]=0xcd,0x06,0x12
    struct.pack_into('<HHHH',cdb,7,0,0,width-1,height-1)
    return struct.pack('<4sIIBBB16s',b'USBC',tag,len(pixels),0,0,16,bytes(cdb))

def validate_status(raw:bytes,tag:int,transferred:int=0):
    if len(raw)!=13:raise ProtocolError('Status must be exactly 13 bytes')
    signature,got,residue,status=struct.unpack('<4sIIB',raw)
    if signature!=b'USBS':raise ProtocolError('Invalid status signature')
    if got!=tag:raise ProtocolError(f'Status tag mismatch (expected {tag:08x}, received {got:08x}, device status {status})')
    # This firmware leaves the original transfer length in successful replies.
    # Accept that exact quirk only after the caller verifies every data byte.
    if residue not in (0,transferred):raise ProtocolError('Incomplete payload transfer')
    if status!=0:raise ProtocolError(f'Device rejected frame: {status}')

class FrameSender:
    def __init__(self,transport):
        self.transport=transport
        self.tag=0
        self.faulted=False
    def lcd_info(self):
        if self.faulted:raise ProtocolError('Transport stopped; reconnect explicitly')
        self.tag=(self.tag+1)&0xffffffff
        cdb=bytearray(16);cdb[0]=0xcd;cdb[5]=2
        command=struct.pack('<4sIIBBB16s',b'USBC',self.tag,5,0,0,16,bytes(cdb))
        try:
            if self.transport.write(0x01,command)!=len(command):raise ProtocolError('Short command write')
            data=self.transport.read(0x81,5)
            if len(data)!=5:raise ProtocolError('Short LCD information reply')
            validate_status(self.transport.read(0x81,13),self.tag,len(data))
            width,height,flags=struct.unpack('<HHB',data)
            if (width,height)!=(480,480):raise ProtocolError(f'Unsupported display size: {width}x{height}')
            return width,height,flags
        except Exception:
            self.faulted=True
            raise
    def send(self,pixels):
        if self.faulted:raise ProtocolError('Transport stopped; reconnect explicitly')
        self.tag=(self.tag+1)&0xffffffff
        command=frame_command(pixels,self.tag)
        try:
            for payload in (command,pixels):
                if self.transport.write(0x01,payload)!=len(payload):
                    raise ProtocolError('Short write; frame outcome uncertain')
            validate_status(self.transport.read(0x81,13),self.tag,len(pixels))
        except Exception:
            self.faulted=True
            raise
