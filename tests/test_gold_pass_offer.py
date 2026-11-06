from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
import cv2
from coc_bot.vision.notices import gold_pass_offer_close_button
from coc_bot.progression.home import recover_home_announcement

ROOT=Path(__file__).parent/'fixtures/accounts'


class GoldPassOfferTests(TestCase):
    def frame(self):return cv2.imread(str(ROOT/'gold-pass-offer.png'))

    def test_native_offer_only_authorizes_its_close(self):
        frame=self.frame()
        self.assertEqual(gold_pass_offer_close_button(frame),(1620,121))
        for x,y,w,h in ((767,640,335,48),(733,697,400,32),(1585,88,70,66)):
            bad=frame.copy();bad[y:y+h,x:x+w]=0
            self.assertIsNone(gold_pass_offer_close_button(bad))
        self.assertIsNone(gold_pass_offer_close_button((frame*.4).astype('uint8')))
        for name in ('hammer-jam.png','free-chest.png','skip-chest-confirm.png'):
            self.assertIsNone(gold_pass_offer_close_button(cv2.imread(str(ROOT/name))))

    def test_fresh_proof_and_two_attempt_bound(self):
        nav=SimpleNamespace(capture=Mock(),input=Mock(),_stopping=lambda:False)
        frame=self.frame();nav.capture.screenshot.return_value=frame
        self.assertTrue(recover_home_announcement(nav,frame))
        self.assertTrue(recover_home_announcement(nav,frame))
        self.assertFalse(recover_home_announcement(nav,frame))
        self.assertEqual(nav.input.tap.call_count,2)
        nav.input.tap.assert_called_with(1620,121,jitter=0)
        nav=SimpleNamespace(capture=Mock(),input=Mock(),_stopping=lambda:False)
        nav.capture.screenshot.return_value=frame*0
        self.assertFalse(recover_home_announcement(nav,frame));nav.input.tap.assert_not_called()
        nav._stopping=lambda:True
        self.assertFalse(recover_home_announcement(nav,frame));nav.input.tap.assert_not_called()

    def test_discount_offer_closes_only_after_matching_text_and_bright_x(self):
        import numpy as np
        frame=np.zeros((1048,1853,3),np.uint8)
        frame[54:983,197:1658]=cv2.imread(str(ROOT/'gold-pass-discount.jpg'))
        self.assertEqual(gold_pass_offer_close_button(frame),(1594,114))
        for ys,xs in [(slice(645,760),slice(600,1250)),(slice(740,825),slice(390,1440)),
                      (slice(50,175),slice(1520,1650))]:
            covered=frame.copy();covered[ys,xs]=0
            self.assertIsNone(gold_pass_offer_close_button(covered))
        self.assertIsNone(gold_pass_offer_close_button((frame*.4).astype('uint8')))
