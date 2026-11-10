from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
import cv2
import numpy as np
from coc_bot.builder_base.deployment import air_deployment_points,separated_air_target,air_distance
from coc_bot.builder_base.runner import BuilderBaseRunner,deployment_points
from coc_bot.builder_base.frames import normalize_builder_frame

ROOT=Path(__file__).parent/'fixtures/builder_base'

class AirSpacingTests(unittest.TestCase):
    def test_real_wide_view_offers_four_separated_initial_air_positions(self):
        frame=cv2.imread(str(ROOT/'battle-baby-dragon-wide-boundary.png'))
        points=air_deployment_points(frame,deployment_points(frame));chosen=[]
        for _ in range(4):
            target=separated_air_target(points,chosen,frame.shape[1])
            self.assertIsNotNone(target)
            chosen.append(target)
        self.assertEqual(len(set(chosen)),4)
        self.assertTrue(all(air_distance(a,b)>=frame.shape[1]*.12
                            for i,a in enumerate(chosen) for b in chosen[i+1:]))

    def test_narrow_view_does_not_fall_back_to_the_first_dragons_position(self):
        frame=normalize_builder_frame(cv2.imread(str(ROOT/'battle-baby-dragon-predeploy-capped.png')))
        points=air_deployment_points(frame,deployment_points(frame));chosen=[]
        for _ in range(4):
            target=separated_air_target(points,chosen,frame.shape[1])
            if target is None:break
            chosen.append(target)
        self.assertGreater(len(chosen),0)
        self.assertLess(len(chosen),4)
        self.assertIsNone(separated_air_target(points,chosen,frame.shape[1]))
        self.assertEqual(air_deployment_points(np.zeros_like(frame)),[])

    def test_actual_watch_loop_does_not_restart_the_target_index_for_each_camp(self):
        frame=np.zeros((1080,1920,3),np.uint8)
        deployed=set();landings=[];selected=[None]
        points=[(300,350),(1500,350),(300,700),(1500,700)]
        def cards(*args,**kwargs):
            return [{'slot':i,'unit':'baby_dragon','deployed':i in deployed,'point':(i,950)} for i in range(1,5)]
        def tap(point):
            if point[1]==950:selected[0]=point[0]
            else:landings.append(point);deployed.add(selected[0])
        reader=Mock();reader.result_button.return_value=None;reader.reward_button.return_value=None
        reader.home.side_effect=lambda _:len(deployed)==4
        reader.battle.return_value=True;reader.find.return_value=None;reader.cards.side_effect=cards
        r=SimpleNamespace(record={'army_kind':'baby_dragon'},frame=lambda:frame,reader=reader,recover_overlay=lambda _:False,
                          zoom=lambda f:f,evidence=Mock(),tap=tap,wait=lambda _:None,phase=Mock())
        with patch('coc_bot.builder_base.tutorials.recover',return_value=False), \
             patch('coc_bot.builder_base.runner.compare_camera',return_value={'verified':True,'scale':1,'transform':np.eye(2,3)}), \
             patch('coc_bot.builder_base.runner.deployment_points',return_value=points), \
             patch('coc_bot.builder_base.deployment.air_deployment_points',return_value=points):
            result=BuilderBaseRunner.watch_battle(r,deploy=True,army='baby_dragon')
        self.assertEqual(result['verified_deployments'],4)
        self.assertEqual(len(set(landings)),4)
        self.assertTrue(all(air_distance(a,b)>=1920*.12 for i,a in enumerate(landings) for b in landings[i+1:]))

    def test_held_dragons_do_not_block_ground_battle_machine(self):
        frame=np.zeros((1080,1920,3),np.uint8);deployed=set();selected=[None];landings=[]
        def cards(*args,**kwargs):
            return [{'slot':i,'unit':'battle_machine' if i==0 else 'baby_dragon',
                     'deployed':i in deployed,'point':(i,950)} for i in range(5)]
        def tap(point):
            if point[1]==950:selected[0]=point[0]
            else:landings.append((selected[0],point));deployed.add(selected[0])
        reader=Mock();reader.result_button.return_value=None;reader.reward_button.return_value=None;reader.home.side_effect=lambda _:0 in deployed
        reader.battle.return_value=True;reader.find.return_value=None;reader.cards.side_effect=cards
        r=SimpleNamespace(record={},frame=lambda:frame,reader=reader,recover_overlay=lambda _:False,zoom=lambda f:f,
                          evidence=Mock(),tap=tap,wait=lambda _:None,phase=Mock())
        with patch('coc_bot.builder_base.tutorials.recover',return_value=False), \
             patch('coc_bot.builder_base.runner.compare_camera',return_value={'verified':True,'scale':1,'transform':np.eye(2,3)}), \
             patch('coc_bot.builder_base.runner.deployment_points',return_value=[(300,350)]), \
             patch('coc_bot.builder_base.deployment.air_deployment_points',return_value=[(300,350)]):
            result=BuilderBaseRunner.watch_battle(r,deploy=True,army='baby_dragon')
        self.assertEqual([slot for slot,point in landings],[1,0])
        self.assertEqual(result['verified_deployments'],2)
