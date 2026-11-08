from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
import struct
import cv2
import numpy as np

from coc_bot.adb.client import AdbStopped
from coc_bot.adb.multitouch import Multitouch
from coc_bot.attack.outer_ring import outer_projection, SOURCE
from coc_bot.attack.executor import VerifiedExecutor
from coc_bot.attack.army import ArmyCard
from coc_bot.attack.plans import AttackPlan, ArmyEntry, PlanStep, MapPoint
from coc_bot.attack.projection import Projection
from coc_bot.attack.camera import CameraFeatures, compare_camera


class RapidTouchTests(TestCase):
    def touch(self):
        value=Multitouch(SimpleNamespace(stop_check=lambda:False),(1000,600))
        value.connection=Mock()
        return value

    @patch('coc_bot.adb.multitouch.time.sleep')
    def test_five_taps_are_ten_packets_without_new_shell_commands(self,sleep):
        touch=self.touch();touch.taps([(300+i,300) for i in range(5)])
        packets=[struct.unpack('>BBQiiHHHII',c.args[0]) for c in touch.connection.sendall.call_args_list]
        self.assertEqual([p[1] for p in packets],[0,1]*5)
        self.assertEqual([p[3] for p in packets],[300,300,301,301,302,302,303,303,304,304])
        self.assertEqual(touch.active,{})
        self.assertAlmostEqual(sum(c.args[0] for c in sleep.call_args_list),.10)

    def test_invalid_later_target_prevents_entire_group(self):
        touch=self.touch()
        for points in ([(100,100),(1000,100)],[(True,100)],[(100,100)]*6,[]):
            with self.assertRaises(ValueError):touch.taps(points)
        touch.connection.sendall.assert_not_called()

    @patch('coc_bot.adb.multitouch.time.sleep')
    def test_stop_after_down_releases_finger_and_never_starts_next_tap(self,sleep):
        touch=self.touch()
        sleep.side_effect=lambda _:setattr(touch.client,'stop_check',lambda:True)
        with self.assertRaises(AdbStopped):touch.taps([(300,300)]*5)
        self.assertEqual(touch.connection.sendall.call_count,2)
        self.assertEqual(touch.active,{})

    def test_disconnect_never_replays_down(self):
        touch=self.touch();touch.connection.sendall.side_effect=[OSError('lost'),None]
        with self.assertRaises(OSError):touch.taps([(300,300)]*5)
        actions=[struct.unpack('>BBQiiHHHII',c.args[0])[1] for c in touch.connection.sendall.call_args_list]
        self.assertEqual(actions,[0,1])


class OuterTerrainTests(TestCase):
    def image(self,name):
        return cv2.imread(str(Path(__file__).parent/'fixtures/attack'/name))

    def test_native_default_outer_ring_and_different_scenery_rejection(self):
        frame=self.image('outer-default.png')
        projection=outer_projection(frame,frame.copy())
        self.assertIsNotNone(projection);self.assertEqual(projection.source,SOURCE)
        # Independently inspected build-zone corners on this captured opponent.
        np.testing.assert_allclose(projection.corners,[(917,-18),(1601,496),(916,1008),(233,495)],atol=4)
        other=self.image('outer-unsupported.png')
        self.assertIsNone(outer_projection(other,other.copy()))

    def test_motion_resize_and_featureless_view_are_rejected(self):
        frame=self.image('outer-default.png');h,w=frame.shape[:2]
        moved=cv2.warpAffine(frame,np.float32([[1,0,15],[0,1,0]]),(w,h))
        self.assertIsNone(outer_projection(frame,moved))
        self.assertIsNone(outer_projection(frame,frame[:-1]))
        self.assertIsNone(outer_projection(np.zeros_like(frame),np.zeros_like(frame)))

    def test_stopped_mapping_does_not_continue(self):
        frame=self.image('outer-default.png')
        with self.assertRaises(AdbStopped):outer_projection(frame,frame,stop=lambda:True)

    def test_terrain_registration_cannot_override_conflicting_red_boundary(self):
        frame=self.image('outer-default.png')
        with patch('coc_bot.attack.outer_ring.observe_boundary',return_value=SimpleNamespace(
                segments=[{'points':[[.15,.15],[.2,.15]]}])):
            self.assertIsNone(outer_projection(frame,frame.copy()))

    def test_reference_cache_preserves_fresh_camera_measurement(self):
        frame=self.image('outer-default.png');h,w=frame.shape[:2];cache=CameraFeatures()
        self.assertTrue(compare_camera(frame,frame,cache=cache)['verified'])
        moved=cv2.warpAffine(frame,np.float32([[1,0,15],[0,1,0]]),(w,h))
        for image in (moved,cv2.resize(frame,(w//2,h//2)),np.zeros_like(frame)):
            expected=compare_camera(frame,image);actual=compare_camera(frame,image,cache=cache)
            self.assertEqual(actual['verified'],expected['verified'])
            if expected['verified']:np.testing.assert_allclose(actual['transform'],expected['transform'])
        old_key=cache.key
        compare_camera(moved,frame,cache=cache)
        self.assertNotEqual(old_key,cache.key)


class RapidExecutorTests(TestCase):
    def executor(self,root,*,outer=False,local=False):
        frame=np.zeros((600,1000,3),np.uint8)
        session=Mock();session.config.data_dir=Path(root);session.config.adb_device='test'
        session.client.stop_check=lambda:False;session.input.dry_run=False
        plan=AttackPlan((ArmyEntry('electro_dragon','troop',3,True),),
                       (PlanStep('deploy_line','electro_dragon',3,(MapPoint(.055,.4),MapPoint(.055,.6))),))
        projection=Projection(((500,50),(900,300),(500,550),(100,300)),source=SOURCE if outer else 'measured')
        if local:
            from coc_bot.attack.edge_fallback import LocalEdge
            projection = LocalEdge((300,250),(300,350))
        exe=VerifiedExecutor(session,plan,projection,frame,Mock(),spam=True)
        exe.frame=Mock(return_value=frame);exe.position=Mock(return_value=(frame,(300,300)))
        exe.target=Mock(return_value=(300,300))
        def card(n):return ArmyCard('0',(100,500,70,95),'electro_dragon','troop',n)
        exe.find=Mock(return_value=(frame,card(3)))
        exe.select=Mock(side_effect=[(frame,card(3)),(frame,card(2))])
        exe.resolve=Mock(side_effect=[card(2),card(0)] if outer or local else [card(0)])
        return exe,session

    def test_outer_ring_confirms_single_troop_before_burst(self):
        with TemporaryDirectory() as root:
            exe,session=self.executor(root,outer=True)
            exe.deploy_batch('electro_dragon',[MapPoint(.055,.5)]*3,spam=True)
            session.input.tap.assert_called_once()
            session.input.tap_many.assert_called_once()
            self.assertEqual(exe.result.verified_taps,3)

    def test_outer_probe_failure_never_sends_burst_or_retries(self):
        for local in (False, True):
            with self.subTest(local=local), TemporaryDirectory() as root:
                exe,session=self.executor(root,outer=not local,local=local)
                exe.resolve=Mock(return_value=ArmyCard('0',(100,500,70,95),'electro_dragon','troop',3))
                with self.assertRaisesRegex(ValueError,'No verified deployment change'):
                    exe.deploy_batch('electro_dragon',[MapPoint(.055,.5)]*3,spam=True)
                session.input.tap.assert_called_once();session.input.tap_many.assert_not_called()
                self.assertTrue(exe.result.uncertain_tap)

    def test_persistent_transport_is_used_and_closed_after_verified_run(self):
        with TemporaryDirectory() as root,patch('coc_bot.adb.multitouch.Multitouch') as factory:
            exe,session=self.executor(root)
            transport=factory.return_value.__enter__.return_value
            result=exe.run()
            self.assertTrue(result.success);self.assertEqual(result.verified_taps,3)
            transport.taps.assert_called_once();transport.close.assert_called_once()
            session.input.tap_many.assert_not_called();session.input.tap.assert_not_called()

    def test_failed_transport_cannot_replay_on_shell(self):
        with TemporaryDirectory() as root,patch('coc_bot.adb.multitouch.Multitouch') as factory:
            exe,session=self.executor(root)
            transport=factory.return_value.__enter__.return_value
            transport.taps.side_effect=OSError('disconnect')
            result=exe.run()
            self.assertFalse(result.success);self.assertTrue(result.uncertain_tap)
            transport.taps.assert_called_once();transport.close.assert_called_once()
            session.input.tap_many.assert_not_called();session.input.tap.assert_not_called()

    def test_startup_failure_can_use_original_transport_before_any_touches(self):
        with TemporaryDirectory() as root,patch('coc_bot.adb.multitouch.Multitouch') as factory:
            exe,session=self.executor(root)
            factory.return_value.__enter__.side_effect=ValueError('not installed')
            self.assertTrue(exe.run().success)
            session.input.tap_many.assert_called_once()

    def test_dry_run_never_opens_real_touch_connection(self):
        with TemporaryDirectory() as root,patch('coc_bot.adb.multitouch.Multitouch') as factory:
            exe,session=self.executor(root);session.input.dry_run=True
            self.assertTrue(exe.run().success);factory.assert_not_called()

    def test_rapid_hero_waits_for_rising_health_bar_without_repeating_tap(self):
        with TemporaryDirectory() as root:
            exe,session=self.executor(root);exe.touch=Mock()
            frame=exe.frame.return_value
            hero=ArmyCard('h',(100,500,70,95),'king','hero',1)
            exe.select=Mock(return_value=(frame,hero));exe.resolve=Mock(return_value=hero)
            with patch('coc_bot.attack.executor.hero_health_visible',side_effect=[False,True]):
                exe.deploy('king',MapPoint(.055,.5))
            session._sleep.assert_called_once_with(.45)
            exe.touch.taps.assert_called_once()
            self.assertEqual(exe.result.verified_taps,1)
