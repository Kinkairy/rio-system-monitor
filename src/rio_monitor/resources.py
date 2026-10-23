"""Bounded native GIF resource protocol, reconstructed from static vendor reference.

Only the resource window may be erased/written. No firmware/configuration commands.
Hardware resource-write and power-cycle acceptance remain separate from source tests.
"""
import io, struct
from PIL import Image
from .protocol import ProtocolError, validate_status

RESOURCE_WINDOW = 0x3B6000
BLOCK = 4096
MAX_MEDIA_BYTES = 3_400_000  # Decimal MB, as displayed in the UI.
QUERY = bytes.fromhex('cd000000000300000000000000000000')
PLAY = bytes.fromhex('cd000000000401000000000000000000')

def gif_info(data, cancelled=lambda:False):
    if not 0 < len(data) <= MAX_MEDIA_BYTES:
        raise ValueError('File exceeds 3.4 MB / 文件超过 3.4 MB')
    if not data.startswith((b'GIF87a',b'GIF89a')) or not data.endswith(b';'):
        raise ValueError('Incomplete GIF / GIF 文件不完整')
    with Image.open(io.BytesIO(data)) as image:
        if image.size != (480,480):raise ValueError('Prepared media must be 480 × 480')
        count=duration=0
        while True:
            if cancelled():raise InterruptedError('Cancelled / 已取消')
            try:image.seek(count)
            except EOFError:break
            image.load();duration+=image.info.get('duration',100);count+=1
    if not count:raise ValueError('No decoded frames')
    return dict(frames=count,duration_ms=duration)

def pack_resource(gif):
    gif_info(gif)
    blob=b'\x02'+struct.pack('>I',len(gif))+bytes(11)+gif
    if len(blob)>RESOURCE_WINDOW:raise ValueError('Resource window exceeded')
    return blob

def validate_blob(blob):
    if not isinstance(blob,bytes) or not 16 < len(blob) <= min(RESOURCE_WINDOW,MAX_MEDIA_BYTES+16):
        raise ValueError('Invalid resource length')
    if blob[0]!=2 or blob[5:16]!=bytes(11) or struct.unpack_from('>I',blob,1)[0]!=len(blob)-16:
        raise ValueError('Invalid GIF resource header')
    gif_info(blob[16:])

def resource_cdb(operation,offset,length=0):
    if operation not in ('erase','write'):raise ValueError('Only resource erase/write is allowed')
    if not isinstance(offset,int) or offset<0 or offset%BLOCK or offset>=RESOURCE_WINDOW:
        raise ValueError('Invalid resource offset')
    if operation=='erase':
        if length!=0 or offset+BLOCK>RESOURCE_WINDOW:raise ValueError('Invalid erase block')
    elif not isinstance(length,int) or not 0<length<=BLOCK or offset+length>RESOURCE_WINDOW:
        raise ValueError('Invalid write block')
    cdb=bytearray(16);cdb[:2]=b'\xfb\xd8' if operation=='erase' else b'\xfb\xd9'
    struct.pack_into('>II',cdb,8,offset,length)
    return bytes(cdb)

class ResourceSender:
    def __init__(self,transport):self.transport=transport;self.tag=0;self.faulted=False
    def exchange(self,cdb,payload=b'',read_length=0):
        if self.faulted:raise ProtocolError('Transfer stopped; reconnect the screen / 请重接屏幕后重试')
        allowed=(cdb==QUERY and read_length==5 and not payload) or (cdb==PLAY and not read_length and not payload)
        if len(cdb)==16 and cdb[:2] in (b'\xfb\xd8',b'\xfb\xd9') and not read_length:
            offset,length=struct.unpack_from('>II',cdb,8)
            op='erase' if cdb[1]==0xd8 else 'write'
            allowed=cdb==resource_cdb(op,offset,length) and len(payload)==length
        if not allowed:raise ValueError('Command outside resource-only allowlist')
        self.tag=(self.tag+1)&0xffffffff
        size=read_length or len(payload)
        cbw=struct.pack('<4sIIBBB16s',b'USBC',self.tag,size,0x80 if read_length else 0,0,16,cdb)
        try:
            for data in ((cbw,payload) if payload else (cbw,)):
                if self.transport.write(1,data)!=len(data):raise ProtocolError('Short resource write; no retry')
            data=self.transport.read(0x81,read_length) if read_length else b''
            if len(data)!=read_length:raise ProtocolError('Short resource read; no retry')
            validate_status(self.transport.read(0x81,13),self.tag,size)
            return data
        except Exception as exc:
            self.faulted=True
            if isinstance(exc,ProtocolError):
                phase='identity query' if cdb==QUERY else 'play' if cdb==PLAY else 'erase' if cdb[1]==0xd8 else 'write'
                raise ProtocolError(f'{phase}: {exc}') from exc
            raise
    def verify_device(self):
        desc=self.transport.device_descriptor()
        if len(desc)!=18 or desc[:2]!=b'\x12\x01' or struct.unpack_from('<HHH',desc,8)!=(0x2a55,0x9990,0x0200):
            raise ProtocolError('Unexpected USB identity/revision; nothing erased')
        width,height,_=struct.unpack('<HHB',self.exchange(QUERY,read_length=5))
        if (width,height)!=(480,480):raise ProtocolError('Unexpected screen dimensions; nothing erased')
    def upload(self,blob,progress=lambda phase,done,total:None,before_erase=lambda:None):
        validate_blob(blob)  # All validation precedes the first erase.
        self.verify_device()
        before_erase()
        offsets=range(0,len(blob),BLOCK);total=len(offsets)*2+1;done=0
        for phase in ('erase','write'):
            for offset in offsets:
                payload=blob[offset:offset+BLOCK] if phase=='write' else b''
                self.exchange(resource_cdb(phase,offset,len(payload)),payload)
                done+=1;progress(phase,done,total)
        self.exchange(PLAY);progress('stored',total,total)
