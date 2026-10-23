import unittest
from pathlib import Path
from PIL import Image,ImageChops,ImageStat
from rio_monitor.render import Renderer,complete_gauge_mask


@unittest.skipUnless((Path(__file__).resolve().parents[1]/'assets/background.png').is_file(),'Private artwork unavailable')
class TemperatureHistoryTests(unittest.TestCase):
    def setUp(self):
        self.renderer=Renderer()
        self.blank=self.renderer.render({},now=10,size=1254)

    def green_delta(self,image,box):
        return ImageStat.Stat(image.crop(box)).mean[1]-ImageStat.Stat(self.blank.crop(box)).mean[1]

    def test_area_is_translucent_green_and_fades_toward_baseline(self):
        self.renderer.history=[80]*120
        image=self.renderer.render({},now=10,size=1254)
        upper=self.green_delta(image,(500,592,620,612))
        lower=self.green_delta(image,(500,644,620,660))
        self.assertGreater(upper,lower+8)
        self.assertGreater(lower,0)
        self.assertLess(upper,100)
        self.assertIsNone(ImageChops.difference(image,self.blank).crop((500,544,620,565)).getbbox())

    def test_area_only_covers_existing_history_and_preserves_missing_intervals(self):
        self.renderer.history=[80]*45+[None]*30+[80]*45
        image=self.renderer.render({},now=10,size=1254)
        self.assertGreater(self.green_delta(image,(300,600,420,640)),5)
        self.assertIsNone(ImageChops.difference(image,self.blank).crop((560,600,690,640)).getbbox())
        self.renderer.history=[80]*20
        short=self.renderer.render({},now=10,size=1254)
        self.assertIsNone(ImageChops.difference(short,self.blank).crop((300,600,420,640)).getbbox())

    def test_missing_arc_cells_are_restored_without_changing_original_mask(self):
        original=Image.open(self.renderer.assets/'gauge-mask.png').convert('L')
        x,y,_,_=self.renderer.gauge_box
        for point in ((1069,287),(1092,323)):
            self.assertEqual(original.getpixel(point),0)
            self.assertGreater(self.renderer.gauge_mask.getpixel((point[0]-x,point[1]-y)),200)
        self.assertEqual(self.renderer.gauge_mask.getpixel((184-x,287-y)),original.getpixel((184,287)))

    def test_complete_mask_is_left_unchanged(self):
        mask=complete_gauge_mask(Image.open(self.renderer.assets/'gauge-mask.png').convert('L'))
        self.assertIsNone(ImageChops.difference(complete_gauge_mask(mask),mask).getbbox())


if __name__=='__main__':unittest.main()
