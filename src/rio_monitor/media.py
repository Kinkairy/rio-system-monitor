"""Local-only preparation of still/animated images and video for native GIF storage."""
from dataclasses import dataclass
from pathlib import Path
import io, subprocess, time
from PIL import Image, ImageOps, GifImagePlugin, UnidentifiedImageError
from .resources import MAX_MEDIA_BYTES, gif_info, pack_resource

@dataclass(frozen=True)
class PreparedMedia:
    name:str
    source_bytes:int
    gif:bytes
    preview:Path
    frames:int
    duration_ms:int
    @property
    def blob(self):return pack_resource(self.gif)

def fit_frame(image):
    image=ImageOps.exif_transpose(image).convert('RGBA')
    image=ImageOps.contain(image,(480,480),Image.Resampling.LANCZOS)
    canvas=Image.new('RGB',(480,480),'black')
    canvas.paste(image,((480-image.width)//2,(480-image.height)//2),image)
    return canvas.quantize(colors=256,method=Image.Quantize.MEDIANCUT)

def convert_image_animation(image,target,cancelled):
    # Pillow's GIF stream helpers encode one frame at a time; a small compressed
    # input cannot make us retain an unbounded list of decoded 480x480 images.
    deadline=time.monotonic()+120;count=0
    with target.open('wb') as out:
        while True:
            if cancelled():raise InterruptedError('Cancelled / 已取消')
            if time.monotonic()>deadline:raise ValueError('Animation conversion timed out / 动画转换超时')
            try:image.seek(count)
            except EOFError:break
            image.load()  # WebP updates each frame's timestamp/duration on load.
            duration=max(10,min(655350,round(image.info.get('duration',100)/10)*10))
            frame=fit_frame(image)
            if count==0:
                header,_=GifImagePlugin.getheader(frame,info={'loop':0,'duration':duration})
                for part in header:out.write(part)
            for part in GifImagePlugin.getdata(frame,duration=duration,disposal=2,include_color_table=True):out.write(part)
            if out.tell()+1>MAX_MEDIA_BYTES:
                raise ValueError('Converted animation exceeds 3.4 MB / 转换后的动画超过 3.4 MB')
            count+=1
        out.write(b';')

def convert_animation(source,target,ffmpeg,cancelled):
    if not ffmpeg.is_file():raise ValueError('Bundled video converter is missing / 视频转换组件缺失')
    # No playlists, URL/network inputs, audio or arbitrary external protocols.
    formats='mov,matroska,webm,avi,asf,mpeg,mpegts,flv,gif,apng,webp_pipe'
    vf=('fps=30,scale=480:480:force_original_aspect_ratio=decrease:flags=lanczos,'
        'pad=480:480:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,split[a][b];'
        '[a]palettegen=stats_mode=single:reserve_transparent=0[p];'
        '[b][p]paletteuse=new=1:dither=bayer:bayer_scale=3:diff_mode=rectangle')
    cmd=[str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-y',
         '-protocol_whitelist','file,pipe','-format_whitelist',formats,'-threads','2',
         '-i',str(source),'-filter_complex_threads','1','-filter_complex',vf,
         '-an','-sn','-dn','-threads','2','-loop','0','-fs',str(MAX_MEDIA_BYTES+1),str(target)]
    process=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    deadline=time.monotonic()+120
    try:
        while True:
            if cancelled():raise InterruptedError('Cancelled / 已取消')
            if time.monotonic()>deadline:raise ValueError('Conversion timed out. Shorten the clip / 转换超时，请剪短视频')
            try:_,error=process.communicate(timeout=.15);break
            except subprocess.TimeoutExpired:continue
        if process.returncode:raise ValueError('Cannot decode this media / 无法解码此文件')
        if not target.is_file():raise ValueError('No video/image frames / 文件中没有可播放的画面')
        if target.stat().st_size>MAX_MEDIA_BYTES:
            raise ValueError('Converted media exceeds 3.4 MB. Shorten the clip / 转换后超过 3.4 MB，请剪短视频或动画')
    finally:
        if process.poll() is None:process.kill()
        process.communicate()

def prepare_media(path,job_dir,ffmpeg,cancelled=lambda:False):
    path=Path(path);job_dir=Path(job_dir);job_dir.mkdir(parents=True,exist_ok=False)
    with path.open('rb') as f:data=f.read(MAX_MEDIA_BYTES+1)
    if not data or len(data)>MAX_MEDIA_BYTES:raise ValueError('Choose a file no larger than 3.4 MB / 请选择不超过 3.4 MB 的文件')
    image=None
    try:image=Image.open(io.BytesIO(data))
    except UnidentifiedImageError:pass
    target=job_dir/'preview.gif'
    if image is not None:
        with image:
            if image.format not in ('PNG','JPEG','BMP','GIF','WEBP'):
                raise ValueError('Supported images: PNG, JPG, BMP, GIF, WebP')
            animated=getattr(image,'is_animated',False)
            if image.format=='GIF' and image.size==(480,480):
                gif_info(data,cancelled);target.write_bytes(data)
            elif not animated:
                fit_frame(image).save(target,'GIF')
            else:
                convert_image_animation(image,target,cancelled)
    else:
        snapshot=job_dir/'input.media';snapshot.write_bytes(data)
        convert_animation(snapshot,target,ffmpeg,cancelled)
    gif=target.read_bytes();info=gif_info(gif,cancelled)
    if cancelled():raise InterruptedError('Cancelled / 已取消')
    return PreparedMedia(path.name,len(data),gif,target,**info)
