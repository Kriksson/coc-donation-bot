import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import cv2
import numpy as np

from coc_bot.adb.client import AdbError
from coc_bot.control.native_recovery import NativeRecoveryPlatform
from coc_bot.control.service import ControlService, BusyError
from coc_bot.runtime.watchdog import ProgressWatchdog
from coc_bot.vision.android_boot import android_boot_frame


class NativeRecoveryTests(TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.config=SimpleNamespace(data_dir=Path(self.temp.name),adb_device='192.0.2.77:5555')
        self.platform=NativeRecoveryPlatform()
        self.recovery=SimpleNamespace(cancel=Event(),_reserve_restart=Mock())
        self.text=f'Session:\tRUNNING\nContainer:\tRUNNING\nIP address:\t192.0.2.77\nSession user:\ttest({os.getuid()})\n'

    def test_status_requires_this_device_and_user(self):
        with patch('coc_bot.control.native_recovery.run_process',return_value=SimpleNamespace(stdout=self.text,returncode=0)):
            self.platform.status(self.config)
        for bad in (self.text.replace('RUNNING','STOPPED'),self.text.replace('192.0.2.77','192.0.2.78'),self.text.replace(f'({os.getuid()})','(999999)')):
            with patch('coc_bot.control.native_recovery.run_process',return_value=SimpleNamespace(stdout=bad,returncode=0)):
                with self.assertRaisesRegex(RuntimeError,'не подтверждены'):self.platform.status(self.config)

    def test_transient_failure_never_restarts_or_spends_limit(self):
        with patch('coc_bot.runtime.device_lease.DeviceLease'),patch.object(self.platform,'status'), \
             patch.object(self.platform,'probe',side_effect=[True,False]), \
             patch.object(self.recovery.cancel,'wait',return_value=False), \
             patch('coc_bot.control.native_recovery.run_process') as run:
            self.assertFalse(self.platform.ensure_capture(self.recovery,self.config))
        run.assert_not_called();self.recovery._reserve_restart.assert_not_called()

    def test_two_failures_restart_under_lease_and_keep_saved_collection(self):
        trace=[]
        class Lease:
            def __init__(self,*a,**kw):pass
            def __enter__(self):trace.append('lease')
            def __exit__(self,*a):trace.append('release')
        self.config.data_dir.joinpath('builder_base').mkdir()
        saved={'phase':'collecting_resources'}
        self.config.data_dir.joinpath('builder_base/visit.json').write_text(json.dumps(saved))
        def stop(args,**kw):
            self.assertEqual(trace[-1],'lease');trace.append('stop');return SimpleNamespace(returncode=0)
        with patch('coc_bot.runtime.device_lease.DeviceLease',Lease),patch.object(self.platform,'status'), \
             patch.object(self.platform,'probe',return_value=True) as probe, \
             patch.object(self.recovery.cancel,'wait',return_value=False), \
             patch('coc_bot.control.native_recovery.run_process',side_effect=stop), \
             patch.object(self.platform,'read_status',return_value={'Session':'STOPPED'}), \
             patch('coc_bot.control.native_recovery.subprocess.Popen') as start:
            self.assertTrue(self.platform.ensure_capture(self.recovery,self.config))
        self.assertEqual(probe.call_count,2);self.recovery._reserve_restart.assert_called_once_with(self.config)
        self.assertEqual(start.call_args.args[0],['waydroid','session','start'])
        self.assertEqual(trace,['lease','stop','release'])
        self.assertEqual(json.loads(self.config.data_dir.joinpath('builder_base/visit.json').read_text()),saved)

    def test_pending_payments_and_battles_block_before_probes(self):
        for path,state in [('upgrades/state.json',{'pending':{'kind':'building'}}),
                           ('builder_base/upgrades.json',{'pending':{'kind':'wall'}}),
                           ('builder_base/visit.json',{'phase':'battle'}),
                           ('layouts/state.json',{'last_survey':{'payment':True}})]:
            with self.subTest(path=path):
                p=self.config.data_dir/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(state))
                with patch('coc_bot.runtime.device_lease.DeviceLease'),patch.object(self.platform,'status'), \
                     patch.object(self.platform,'probe') as probe:
                    with self.assertRaisesRegex(RuntimeError,'перезапуск Android заблокирован'):
                        self.platform.ensure_capture(self.recovery,self.config)
                probe.assert_not_called();self.recovery._reserve_restart.assert_not_called();p.unlink()

    def test_stop_cannot_send_restart_input(self):
        self.recovery.cancel.set()
        with patch('coc_bot.runtime.device_lease.DeviceLease'), \
             patch('coc_bot.control.native_recovery.run_process') as run:
            with self.assertRaises(RuntimeError):self.platform.ensure_capture(self.recovery,self.config)
        run.assert_not_called();self.recovery._reserve_restart.assert_not_called()

    def test_local_adapter_is_selected_without_changing_managed_runtime(self):
        service=ControlService()
        with patch.dict(os.environ,{},clear=True),patch('shutil.which',return_value='/usr/bin/waydroid'):
            self.assertIsInstance(service.capture_recovery.recovery_platform(),NativeRecoveryPlatform)
        service.platform=Mock()
        self.assertIs(service.capture_recovery.recovery_platform(),service.platform)

    def test_manual_tools_cannot_race_native_recovery(self):
        service=ControlService();service.capture_recovery.thread=Mock()
        service.capture_recovery.thread.is_alive.return_value=True
        with self.assertRaisesRegex(BusyError,'Восстанавливается Android'):service.idle()

    def test_probe_detects_boot_animation_even_when_png_is_valid(self):
        with patch('coc_bot.adb.client.AdbClient') as client,patch('coc_bot.adb.capture.ScreenCapture'):
            client.return_value.run_shell.return_value.stdout='running\n'
            self.assertTrue(self.platform.probe(self.config))
            client.return_value.run_shell.return_value.stdout='stopped\n'
            self.assertFalse(self.platform.probe(self.config))

    def test_inspected_boot_logo_is_not_a_valid_bot_frame(self):
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/progression/android-boot-native.png'))
        self.assertTrue(android_boot_frame(frame))
        self.assertTrue(android_boot_frame(cv2.resize(frame,(960,540))))
        for other in (np.zeros_like(frame),np.full_like(frame,120),frame.copy()):
            other[490:640,760:1140]=0
            self.assertFalse(android_boot_frame(other))
        village=cv2.imread(str(Path(__file__).parent/'fixtures/progression/star-bonus-builder-native.png'))
        self.assertFalse(android_boot_frame(village))
        monitor=ProgressWatchdog(self.config,lambda:False)
        with self.assertRaisesRegex(AdbError,'загрузочный экран'):monitor.observe(frame)
        self.assertTrue((self.config.data_dir/'verification/android-boot-stalled.png').exists())
        monitor.observe(np.full_like(frame,100))
        self.assertIsNone(monitor.status)

    def test_boot_recovery_signal_is_not_reset_by_viewer_frames(self):
        from coc_bot.adb.capture_coordinator import publish_frame
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/progression/android-boot-native.png'))
        monitor=ProgressWatchdog(self.config,lambda:False)
        with patch('coc_bot.adb.capture_coordinator.request_capture_recovery') as request:
            for _ in range(3):
                publish_frame(self.config.adb_device,frame)
                with self.assertRaises(AdbError):monitor.observe(frame)
            request.assert_called_once_with(self.config.adb_device)

    def test_local_worker_resumes_bot_only_after_successful_preparation(self):
        service=ControlService();service.operation='bot'
        service.controller=Mock();service.controller.wait.return_value=True
        service.controller.snapshot.return_value=SimpleNamespace(closing=False)
        service._start_bot=Mock(return_value=True)
        recovery=service.capture_recovery
        def prepare(**kw):self.platform.update('ready','ready',ready=True)
        with patch.object(recovery,'recovery_platform',return_value=self.platform), \
             patch.object(recovery,'_ensure_capture_session',return_value=True), \
             patch.object(self.platform,'prepare',side_effect=prepare):
            recovery._run(self.config,True,'saved-options')
        service._start_bot.assert_called_once_with('saved-options')

    def test_failed_stop_cannot_launch_a_second_session(self):
        with patch('coc_bot.runtime.device_lease.DeviceLease'),patch.object(self.platform,'status'), \
             patch.object(self.platform,'probe',return_value=True), \
             patch.object(self.recovery.cancel,'wait',return_value=False), \
             patch('coc_bot.control.native_recovery.run_process',return_value=SimpleNamespace(returncode=0)), \
             patch.object(self.platform,'read_status',return_value={'Session':'RUNNING'}), \
             patch('coc_bot.control.native_recovery.subprocess.Popen') as start:
            with self.assertRaisesRegex(RuntimeError,'Остановка локального Waydroid не подтверждена'):
                self.platform.ensure_capture(self.recovery,self.config)
        start.assert_not_called()
