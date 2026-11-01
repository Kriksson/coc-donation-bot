from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,patch
import cv2
import numpy as np
from coc_bot.vision.connection_dialog import connection_retry_button,recover_connection_error

ROOT=Path(__file__).parent/'fixtures/accounts'


class ConnectionDialogTests(TestCase):
    def frame(self):return cv2.imread(str(ROOT/'connection-error.png'))

    def test_actual_native_error_and_scaled_frames(self):
        for size in ((1853,1048),(1280,724),(1600,905)):
            point=connection_retry_button(cv2.resize(self.frame(),size))
            self.assertIsNotNone(point)
            self.assertLess(abs(point[0]/size[0]-511/1853),.004)
            self.assertLess(abs(point[1]/size[1]-560/1048),.004)

    def test_each_required_label_and_foreground_action_are_mandatory(self):
        for x,y,w,h in ((468,416,208,31),(468,461,750,27),(469,548,84,25)):
            frame=self.frame();frame[y:y+h,x:x+w]=0
            self.assertIsNone(connection_retry_button(frame))
        self.assertIsNone(connection_retry_button((self.frame()*.4).astype(np.uint8)))
        self.assertIsNone(connection_retry_button(np.zeros((1048,1853,3),np.uint8)))
        for name in ('defense-results.png','welcome-after-defense.png','event-ended.png'):
            self.assertIsNone(connection_retry_button(cv2.imread(str(ROOT/name))),name)

    def nav(self):
        return SimpleNamespace(_stopping=Mock(return_value=False),capture=Mock(),input=Mock())

    def test_retry_is_fresh_verified_bounded_and_cooldown_never_falls_through(self):
        nav=self.nav();nav.capture.screenshot.return_value=self.frame()
        with patch('time.monotonic',side_effect=[0,1,11,22,33,121]):
            for _ in range(6):self.assertTrue(recover_connection_error(nav,self.frame()))
        self.assertEqual(nav.input.tap.call_count,4)
        self.assertEqual(nav.capture.screenshot.call_count,4)
        self.assertTrue(all(call.kwargs=={'jitter':0} for call in nav.input.tap.call_args_list))

    def test_stop_or_changed_dialog_prevents_any_tap(self):
        nav=self.nav();nav._stopping.return_value=True
        self.assertFalse(recover_connection_error(nav,self.frame()));nav.input.tap.assert_not_called()
        nav._stopping.return_value=False
        nav.capture.screenshot.return_value=np.zeros_like(self.frame())
        self.assertFalse(recover_connection_error(nav,self.frame()));nav.input.tap.assert_not_called()
        nav.capture.screenshot.return_value=self.frame();nav._stopping.side_effect=[False,True]
        self.assertFalse(recover_connection_error(nav,self.frame()));nav.input.tap.assert_not_called()
