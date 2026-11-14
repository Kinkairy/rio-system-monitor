"""Hardware-verified RGB565 framebuffer protocol. No persistent writes."""
import itertools,logging,os,struct,time

logger=logging.getLogger('rio_monitor.usb')
# A reopened handle still sees the device FIFO. Do not reuse its last command tag.
_tags=itertools.count(int.from_bytes(os.urandom(4),'little'))
from PIL import Image, ImageChops

class ProtocolError(RuntimeError):pass

class FrameTransferError(ProtocolError):
    """Keep failure context without treating a failed driver's count as success."""
    def __init__(self,stage,elapsed_ms,cause):
        self.stage=stage;self.elapsed_ms=elapsed_ms;self.cause=cause
        self.requires_replug=stage in ('lcd_info.command','frame.command','frame.pixels')
        self.is_timeout=(getattr(cause,'winerror',None) or getattr(cause,'errno',None))==121
        detail=''
        if hasattr(cause,'usb_api'):
            detail=(f'; {cause.usb_api} ep=0x{cause.usb_endpoint:02x}'
                    f' requested={cause.usb_requested} driver_count={cause.usb_reported} (unconfirmed)')
        super().__init__(f'{stage} ({elapsed_ms:.1f} ms): {cause}{detail}')

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
    response_timeout=4.5
    max_read_timeouts=2
    max_response_bytes=256
    max_reads=64

    def __init__(self,transport):
        self.transport=transport
        self.tag=0
        self.faulted=False
        self._incoming=bytearray()

    def _response(self,transferred,query=False):
        # WinUSB reads are byte counts, not protocol message boundaries. A new
        # handle does not reset firmware. Only a full matching CSW completes
        # the operation; never repeat an OUT write.
        started=time.monotonic();timeouts=0;received=0;empty=0
        data=self._incoming
        for _ in range(self.max_reads):
            index=data.find(b'USBS')
            if index>=0 and len(data)>=index+13:
                status=bytes(data[index:index+13])
                got=struct.unpack_from('<I',status,4)[0]
                if got==self.tag:
                    validate_status(status,self.tag,transferred)
                    payload=bytes(data[max(0,index-5):index]) if query else b''
                    del data[:index+13]
                    if query and len(payload)!=5:raise ProtocolError('Missing LCD information before current status')
                    return payload
                logger.warning('USB discarded stale status tag=%08x current=%08x',got,self.tag)
                del data[:index+13]
                continue
            if time.monotonic()-started>=self.response_timeout:
                raise ProtocolError('USB response deadline exceeded')
            # Preserve the normal OEM 5-byte query + 13-byte CSW reads. On a
            # fragmented response, ask only for the missing portion of the CSW.
            length=index+13-len(data) if index>=0 else (5-len(data) if query and len(data)<5 else 13)
            try:part=self.transport.read(0x81,length)
            except OSError as exc:
                code=getattr(exc,'winerror',None) or getattr(exc,'errno',None)
                if code!=121 or getattr(exc,'usb_reported',0) or timeouts>=self.max_read_timeouts:raise
                timeouts+=1
                logger.warning('USB delayed IN reply; keeping transaction tag=%08x retry=%d',self.tag,timeouts)
                continue
            if len(part)>length:raise ProtocolError('Read returned more bytes than requested')
            if not part:
                empty+=1
                if empty>=3:raise ProtocolError('Repeated empty USB replies')
            data.extend(part);received+=len(part)
            if received>self.max_response_bytes:raise ProtocolError('Too much stale USB response data')
            if query and len(data)>=5:self._stage='lcd_info.status'
        raise ProtocolError('USB response read limit exceeded')

    def lcd_info(self):
        if self.faulted:raise ProtocolError('Transport stopped; reconnect explicitly')
        self.tag=next(_tags)&0xffffffff
        cdb=bytearray(16);cdb[0]=0xcd;cdb[5]=3
        command=struct.pack('<4sIIBBB16s',b'USBC',self.tag,5,0x80,0,16,bytes(cdb))
        self._stage='lcd_info.command';started=time.monotonic()
        try:
            if self.transport.write(0x01,command)!=len(command):raise ProtocolError('Short command write; outcome uncertain')
            self._stage='lcd_info.reply';started=time.monotonic()
            data=self._response(5,query=True)
            self._stage='lcd_info.dimensions'
            width,height,flags=struct.unpack('<HHB',data)
            if (width,height)!=(480,480):raise ProtocolError(f'Unsupported display size: {width}x{height}')
            return width,height,flags
        except Exception as exc:
            self.faulted=True
            raise FrameTransferError(self._stage,(time.monotonic()-started)*1000,exc) from exc

    def send(self,pixels):
        if self.faulted:raise ProtocolError('Transport stopped; reconnect explicitly')
        self.tag=next(_tags)&0xffffffff
        command=frame_command(pixels,self.tag)
        stage='frame.command';started=time.monotonic()
        try:
            for stage,payload in (('frame.command',command),('frame.pixels',pixels)):
                started=time.monotonic()
                if self.transport.write(0x01,payload)!=len(payload):
                    raise ProtocolError('Short write; frame outcome uncertain')
            stage='frame.status';started=time.monotonic()
            self._response(len(pixels))
        except Exception as exc:
            self.faulted=True
            raise FrameTransferError(stage,(time.monotonic()-started)*1000,exc) from exc
