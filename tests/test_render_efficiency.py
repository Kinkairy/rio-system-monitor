"""Cache invariants without changing rendering or audio values."""
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageChops

ROOT = Path(__file__).resolve().parents[1]


class SpectrumPlanTests(unittest.TestCase):
    def test_plan_reused_and_rebuilt_for_changed_input(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('NumPy unavailable')
        from rio_monitor.music.state import Spectrum
        spectrum = Spectrum(48000)
        pcm = np.sin(np.arange(4096, dtype=np.float32) * .1)
        with patch.object(np, 'hanning', wraps=np.hanning) as window:
            first = spectrum.analyze(pcm, 2, 1)
            second = spectrum.analyze(pcm, 2, 2)
            self.assertEqual(window.call_count, 1)
            self.assertEqual(first.bands, second.bands)
            self.assertEqual(first.level, second.level)
            spectrum.analyze(pcm[:2048], 2, 3)
            spectrum.rate = 44100
            spectrum.analyze(pcm[:2048], 2, 4)
            self.assertEqual(window.call_count, 3)
            self.assertEqual(spectrum._plan_key, (1024, 44100))


@unittest.skipUnless((ROOT / 'assets/background.png').is_file(), 'Private artwork unavailable')
class RenderCacheInvariants(unittest.TestCase):
    def test_compact_robot_plate_matches_original_full_canvas(self):
        from rio_monitor.render import Renderer
        renderer = Renderer()
        plate = Image.new('RGBA', renderer.background.size)
        ImageDraw.Draw(plate).ellipse((904,385,1036,517), fill=(0,24,16,255))
        grid = Image.new('RGBA', (132,132)); draw = ImageDraw.Draw(grid)
        for pos in range(0,132,22):
            draw.line((pos,0,pos,132), fill=(7,51,35,255))
            draw.line((0,pos,132,pos), fill=(7,51,35,255))
        clip = Image.new('L', (132,132))
        ImageDraw.Draw(clip).ellipse((0,0,131,131), fill=255)
        plate.paste(grid, (904,385), clip)
        old = renderer.background.copy(); old.paste(plate,(0,0),plate)
        new = renderer.background.copy(); new.paste(renderer.robot_plate,(904,385),renderer.robot_plate)
        self.assertIsNone(ImageChops.difference(old,new).getbbox())

    def test_existing_gpu_chart_is_not_reallocated(self):
        from rio_monitor.render import Renderer
        from rio_monitor.model import Readings, GPUReading
        from rio_monitor.usage_chart import UsageChart
        renderer = Renderer()
        samples = Readings({}, gpus=(GPUReading('gpu','GPU',50,None,10),))
        with patch('rio_monitor.render.UsageChart', wraps=UsageChart) as chart:
            renderer.render(samples, now=10)
            renderer.render(samples, now=10.1)
            self.assertEqual(chart.call_count, 1)


    def test_precomposed_assets_preserve_rendered_frames(self):
        import datetime, io, random, sys, tempfile
        from rio_monitor.render_cache import Renderer
        from rio_monitor.model import Sample
        from rio_monitor.music.renderer import MusicRenderer
        from rio_monitor.music.state import Track, Audio
        with tempfile.TemporaryDirectory() as work, patch.object(sys, 'path', [str(ROOT/'tools')]+sys.path):
            from prepare_fixed_layers import prepare, SOURCE_ONLY
            assets=ROOT/'assets';runtime=prepare(assets,Path(work)/'runtime-assets')
            for name in SOURCE_ONLY-{'rio-brand.png','private-manifest.json'}:
                self.assertFalse((runtime/name).exists(),name)
            self.assertEqual(Image.open(runtime/'rio-brand.png').size,(240,80))
            plain,baked=Renderer(assets),Renderer(runtime)
            plain.robot.rng=random.Random(17);baked.robot.rng=random.Random(17)
            for index,value in enumerate((None,0,57,100,999999,32)):
                now=10+index*.4
                samples={key:Sample(value,now) for key in ('cpu','gpu','temperature','ram_used','ram_total','upload','download')}
                kwargs=dict(now=now,wall=datetime.datetime(2026,10,25,12,index))
                self.assertEqual(plain.render(samples,**kwargs).tobytes(),baked.render(samples,**kwargs).tobytes())
            plain,baked=MusicRenderer(assets),MusicRenderer(runtime)
            cover=io.BytesIO();Image.new('RGB',(200,180),'#63a8bc').save(cover,format='PNG')
            for index in range(12):
                now=20+index*.12
                snapshot=dict(track=Track(title='A song that keeps scrolling '+str(index//5),artist='Artist',cover=cover.getvalue() if index>2 else b'',playing=True,position=1,observed=now,duration=180),audio=Audio(tuple([.6]*12),.65,now,'ready'),rows=(),lyric_status='loading')
                self.assertEqual(plain.render(snapshot,now).tobytes(),baked.render(snapshot,now).tobytes())
