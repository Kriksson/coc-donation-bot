from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
import cv2
import numpy as np
from coc_bot.vision.notices import home_star_bonus_button
from coc_bot.builder_base.vision import BuilderReader
from coc_bot.builder_base.runner import BuilderBaseRunner
from coc_bot.progression.home import acknowledge_star_bonus,recover_home_bonus,ensure_home

ROOT=Path(__file__).parent/'fixtures'

class NativeStarBonusTests(unittest.TestCase):
    def setUp(self):
        self.bonus=cv2.imread(str(ROOT/'progression/star-bonus-builder-native.png'))
        self.home=cv2.imread(str(ROOT/'builder_base/resources-area1.png'))

    def test_current_layout_is_shared_by_both_villages_and_scales(self):
        for scale in (.5,.75,1,1.25):
            frame=cv2.resize(self.bonus,None,fx=scale,fy=scale)
            with self.subTest(scale=scale):
                point=home_star_bonus_button(frame)
                self.assertIsNotNone(point)
                self.assertEqual(BuilderReader().reward_button(frame),point)
                self.assertLess(abs(point[0]-960*scale),3)
                self.assertLess(abs(point[1]-841*scale),3)
        # The dimmed village is not evidence for acknowledging the notice.
        home_background=cv2.resize(self.home,(1920,1080))
        home_background[160:950,315:1605]=self.bonus[160:950,315:1605]
        self.assertEqual(home_star_bonus_button(home_background),home_star_bonus_button(self.bonus))

    def test_each_heading_and_enabled_button_are_required(self):
        for x,y,u,v in [(750,185,1165,250),(740,570,1190,615),(810,780,1110,900)]:
            bad=self.bonus.copy();bad[y:v,x:u]=0
            self.assertIsNone(home_star_bonus_button(bad))
        disabled=self.bonus.copy()
        disabled[780:900,810:1110]=cv2.cvtColor(cv2.cvtColor(disabled[780:900,810:1110],cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
        self.assertIsNone(home_star_bonus_button(disabled))
        only_button=np.zeros_like(self.bonus);only_button[780:900,810:1110]=self.bonus[780:900,810:1110]
        self.assertIsNone(home_star_bonus_button(only_button))
        self.assertIsNone(home_star_bonus_button((self.bonus*.4).astype(np.uint8)))
        for invalid in (None,np.zeros((0,0,3),np.uint8),np.zeros((1080,1920),np.uint8)):
            self.assertIsNone(home_star_bonus_button(invalid))

    def test_capped_native_frame_is_supported_without_mutating_evidence(self):
        capped=(self.bonus.astype(np.float32)*178/255).astype(np.uint8);original=capped.copy()
        self.assertIsNotNone(home_star_bonus_button(capped))
        self.assertTrue(np.array_equal(original,capped))

    def test_variable_reward_amounts_do_not_change_okay_identity(self):
        frame=self.bonus.copy();frame[645:760,450:1460]=0
        self.assertEqual(home_star_bonus_button(frame),home_star_bonus_button(self.bonus))

    def test_changed_second_frame_stop_and_retry_limit_never_send_extra_taps(self):
        owner=SimpleNamespace();capture=Mock();input_ctrl=Mock()
        capture.screenshot.return_value=self.home
        self.assertFalse(acknowledge_star_bonus(owner,self.bonus,capture,input_ctrl,lambda:False))
        input_ctrl.tap.assert_not_called()
        capture.screenshot.return_value=self.bonus
        self.assertFalse(acknowledge_star_bonus(owner,self.bonus,capture,input_ctrl,lambda:True))
        for _ in range(2):self.assertTrue(acknowledge_star_bonus(owner,self.bonus,capture,input_ctrl,lambda:False))
        self.assertFalse(acknowledge_star_bonus(owner,self.bonus,capture,input_ctrl,lambda:False))
        self.assertEqual(input_ctrl.tap.call_count,2)
        self.assertFalse(acknowledge_star_bonus(owner,self.home,capture,input_ctrl,lambda:False))
        self.assertTrue(acknowledge_star_bonus(owner,self.bonus,capture,input_ctrl,lambda:False))

    def test_home_verification_continues_only_after_bonus_is_closed(self):
        state={'frame':self.bonus};nav=SimpleNamespace()
        nav._stopping=lambda:False;nav.capture=Mock();nav.input=Mock();nav.classifier=Mock()
        nav.capture.screenshot.side_effect=lambda:state['frame']
        nav.input.tap.side_effect=lambda *a,**k:state.update(frame=self.home)
        nav.classifier._clan_chat_anchor_visible.return_value=False
        nav.classifier.auxiliary_page.return_value=None
        nav.classifier.looks_like_blocking_popup.return_value=False
        with patch('coc_bot.progression.home.recover_home_overlay',side_effect=recover_home_bonus), \
             patch('coc_bot.progression.home.home_build_control_visible',side_effect=lambda f:f is self.home), \
             patch('coc_bot.progression.home.interrupted_sleep',return_value=False):
            self.assertTrue(ensure_home(nav))
        nav.input.tap.assert_called_once_with(961,841,jitter=0)

    def test_builder_battle_return_acknowledges_bonus_before_home_detection(self):
        state={'frame':self.bonus};capture=Mock();input_ctrl=Mock();reader=BuilderReader()
        capture.screenshot.side_effect=lambda:state['frame']
        input_ctrl.tap.side_effect=lambda *a,**k:state.update(frame=self.home)
        r=SimpleNamespace(record={'army_kind':'baby_dragon'},reader=reader,stop=lambda:False,
                          frame=lambda:state['frame'],capture=capture,input=input_ctrl,
                          phase=Mock(),wait=Mock(),zoom=Mock(),evidence=Mock())
        from coc_bot.donation.navigator import Navigator
        from coc_bot.config import load_config
        r.nav=Navigator(load_config(),capture,input_ctrl)
        r.recover_overlay=lambda f:BuilderBaseRunner.recover_overlay(r,f)
        r.acknowledge_bonus=lambda f:BuilderBaseRunner.acknowledge_bonus(r,f)
        with patch('coc_bot.builder_base.tutorials.recover',return_value=False):
            result=BuilderBaseRunner.watch_battle(r,deploy=False)
        self.assertEqual(result,{'status':'returned','verified_deployments':0})
        input_ctrl.tap.assert_called_once_with(961,841,jitter=0)
        r.zoom.assert_not_called()
        r.phase.assert_called_once_with('builder_home')

    def test_inactivity_dialog_blocks_bonus_until_native_reload_is_identified(self):
        from coc_bot.vision.idle_dialog import IdleDialogDetector
        frame=cv2.imread(str(ROOT/'progression/star-bonus-blocked-by-idle.png'))
        self.assertIsNone(home_star_bonus_button(frame))
        self.assertEqual(IdleDialogDetector().detect(frame),(622,566))
        for x,y,u,v in [(570,438,740,467),(570,478,945,503),(570,553,675,579)]:
            bad=frame.copy();bad[y:v,x:u]=0
            self.assertIsNone(IdleDialogDetector().detect(bad))
        self.assertIsNone(IdleDialogDetector().detect((frame*.4).astype(np.uint8)))
