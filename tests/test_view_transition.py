import unittest
from PIL import Image
from rio_monitor.view_transition import ViewTransition,pop_scale


class ViewTransitionTests(unittest.TestCase):
    def test_first_view_is_direct_and_new_view_pops_from_center(self):
        old=Image.new('RGB',(80,80),'red');new=Image.new('RGB',(80,80),'blue');effect=ViewTransition()
        self.assertIs(effect.render('monitor',old,100),old)
        self.assertEqual(effect.render('music',new,101).tobytes(),old.tobytes())
        frame=effect.render('music',new,101.10)
        self.assertGreater(frame.getpixel((40,40))[2],0)
        self.assertEqual(frame.getpixel((0,40)),(255,0,0))
        self.assertIs(effect.render('music',new,101.55),new)

    def test_scale_overshoots_and_rebounds_to_exact_size(self):
        self.assertAlmostEqual(pop_scale(0),.72)
        scales=[pop_scale(i/100) for i in range(101)]
        self.assertGreater(max(scales),1.04);self.assertLess(max(scales),1.08)
        self.assertLess(scales[90],max(scales));self.assertEqual(pop_scale(1),1)

    def test_reverse_mid_transition_continues_from_displayed_frame(self):
        old=Image.new('RGB',(80,80),'red');new=Image.new('RGB',(80,80),'blue');effect=ViewTransition()
        effect.render('monitor',old,100);effect.render('music',new,101)
        shown=effect.render('music',new,101.2)
        self.assertEqual(effect.render('monitor',old,101.21).tobytes(),shown.tobytes())
        self.assertIs(effect.render('monitor',old,102),old)
