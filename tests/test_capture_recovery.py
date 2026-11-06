"""Renderer recovery owns inputs, honors Stop, and never guesses from ICE errors."""
from contextlib import contextmanager
import json
import subprocess
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import numpy as np

from coc_bot.adb.client import AdbError, AdbStopped
from coc_bot.adb import capture_coordinator as captures
from coc_bot.control.capture_recovery import CaptureRecovery
from coc_bot.control.platform import Platform
from coc_bot.control.service import ControlService, BusyError


class CaptureFailureTests(TestCase):
    def tearDown(self):
        captures.set_failure_listener(None)
        captures.capture_succeeded('capture-test')

    def test_three_failures_trigger_and_a_good_frame_resets(self):
        listener=MagicMock();captures.set_failure_listener(listener)
        captures.capture_failed('capture-test');captures.capture_failed('capture-test')
        listener.assert_not_called()
        captures.publish_frame('capture-test',np.zeros((2,2,3),np.uint8))
        captures.capture_failed('capture-test');captures.capture_failed('capture-test')
        listener.assert_not_called()
        captures.capture_failed('capture-test');listener.assert_called_once_with('capture-test')

    def test_stops_and_observation_misses_do_not_count_as_capture_failure(self):
        class Source:
            client=SimpleNamespace(device='capture-test',stop_check=None)
            @captures.serialized_capture
            def screenshot(self,timeout_seconds=1): raise AdbStopped('Stop')
            @captures.serialized_capture
            def observe(self,timeout_seconds=1): raise AdbError('Optional sample failed')
        listener=MagicMock();captures.set_failure_listener(listener)
        for _ in range(4):
            with self.assertRaises(AdbStopped): Source().screenshot()
            with self.assertRaises(AdbError): Source().observe()
        listener.assert_not_called()

    def test_listener_failure_does_not_replace_capture_error(self):
        captures.set_failure_listener(MagicMock(side_effect=ValueError('Unreadable settings')))
        for _ in range(3):captures.capture_failed('capture-test')


class CaptureRecoveryTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.device = '192.0.2.77:5555'
        self.running = {'session': 'RUNNING', 'container': 'RUNNING', 'ip': '192.0.2.77', 'recovery_lease': True}
        self.stopped = {'session': 'STOPPED', 'container': 'STOPPED', 'ip': None, 'recovery_lease': True}
        self.config=SimpleNamespace(adb_device=self.device,data_dir=Path(self.temp.name))
        self.service=ControlService()
        self.service.platform=Platform();self.service.platform.update('ready','Ready',ready=True)
        self.state=SimpleNamespace(active=True,stop_requested=False,closing=False)
        self.service.operation='bot'
        self.service.controller=SimpleNamespace(stop=MagicMock(),wait=MagicMock(return_value=True),
            start=MagicMock(return_value=True),options=object(),snapshot=lambda:self.state)
        self.recovery=self.service.capture_recovery

    def test_restart_owns_stop_and_ensure_then_releases_before_adb_startup(self):
        trace=[]
        @contextmanager
        def lease(device, *, recovery):
            self.assertFalse(recovery)
            trace.append('lease');yield;trace.append('released')
        def request(action,**kwargs):
            trace.append(action)
            return self.running
        def prepare(**kwargs):
            self.assertEqual(trace[-1],'released')
            self.assertEqual(kwargs,{'skip_updates':True, 'android_ensured':True})
            self.service.platform.update('ready','Recovered',ready=True)
        with patch('coc_bot.runtime.device_lease.DeviceLease',lease),patch.object(self.recovery,'_probe',return_value=True),\
             patch('coc_bot.host_bridge.request',side_effect=request),patch.object(self.service.platform,'prepare',side_effect=prepare):
            self.recovery._run(self.config,True,self.service.controller.options)
        self.assertEqual(trace,['status','lease','status','status','stop','ensure','released'])
        self.service.controller.start.assert_called_once_with(self.service.controller.options)
        self.assertEqual(len(json.loads((self.config.data_dir/'runtime/renderer-recovery.json').read_text())['attempts']),1)

    def test_transient_capture_recovers_without_restart_or_spending(self):
        with patch('coc_bot.runtime.device_lease.DeviceLease'),patch.object(self.recovery,'_probe',return_value=False),\
             patch('coc_bot.host_bridge.request', return_value=self.running) as request:
            self.recovery._run(self.config,True,self.service.controller.options)
        self.assertEqual([c.args[0] for c in request.call_args_list], ['status', 'status'])
        self.service.controller.start.assert_called_once()
        self.assertFalse((self.config.data_dir/'runtime/renderer-recovery.json').exists())

    def test_stop_during_restart_never_prepares_or_resumes(self):
        with patch('coc_bot.runtime.device_lease.DeviceLease'),patch.object(self.recovery,'_probe',return_value=True),\
             patch('coc_bot.host_bridge.request',side_effect=lambda action,**k:
                   self.running if action == 'status' else self.service.stop()) as request,\
             patch.object(self.service.platform,'prepare') as prepare:
            self.recovery._run(self.config,True,self.service.controller.options)
        prepare.assert_not_called();self.service.controller.start.assert_not_called()
        self.assertEqual([c.args[0] for c in request.call_args_list], ['status', 'status', 'status', 'stop'])
        self.assertIn('canceled',self.service.platform.snapshot()['error'])

    def test_busy_owner_blocks_all_host_actions(self):
        with patch('coc_bot.runtime.device_lease.DeviceLease', side_effect=BusyError('Other owner')), \
                patch('coc_bot.host_bridge.request', return_value=self.stopped) as request:
            self.recovery._run(self.config, True, self.service.controller.options)
        request.assert_called_once_with('status')
        self.service.controller.start.assert_not_called()

    def test_stopped_without_ip_starts_once_and_resumes_only_after_health_check(self):
        client = MagicMock()
        lease = MagicMock()
        with patch('coc_bot.runtime.device_lease.DeviceLease', lease), \
                patch('coc_bot.host_bridge.request', return_value=self.stopped) as request, \
                patch.object(self.recovery, '_probe') as probe, \
                patch('coc_bot.config.load_config', return_value=SimpleNamespace(adb_device='192.0.2.78:5555')), \
                patch('coc_bot.adb.client.AdbClient', return_value=client), \
                patch('coc_bot.runtime.processes.run_process') as disconnect, \
                patch.object(self.service.platform, 'wait_for_android'), \
                patch('coc_bot.adb.app.AppController'), patch('coc_bot.control.game_updates.update_game') as update:
            self.recovery._run(self.config, True, self.service.controller.options)
        self.assertEqual([c.args[0] for c in request.call_args_list], ['status', 'status', 'ensure'])
        self.assertEqual(lease.call_args_list[0].kwargs, {'recovery': True})
        self.assertEqual([c.args[0] for c in lease.call_args_list], [self.device, '192.0.2.78:5555'])
        disconnect.assert_called_once()
        self.assertEqual(disconnect.call_args.args[0], ['adb', 'disconnect', '192.0.2.78:5555'])
        probe.assert_not_called()
        update.assert_not_called()
        client.health_check.assert_called_once()
        self.service.controller.start.assert_called_once_with(self.service.controller.options)

    def test_uncertain_status_or_failed_startup_never_resumes(self):
        for status, actions in [
            (self.running | {'ip': None}, ['status', 'status']),
            (self.running | {'ip': '192.0.2.88'}, ['status', 'status']),
            (self.running | {'session': 'UNKNOWN', 'container': 'STOPPED'}, ['status', 'status']),
            (self.stopped, ['status', 'status', 'ensure']),
        ]:
            with self.subTest(status=status), patch('coc_bot.runtime.device_lease.DeviceLease'), \
                    patch.object(self.recovery, '_probe') as probe, \
                    patch('coc_bot.host_bridge.request', side_effect=[status, status, RuntimeError('Startup failed')]) as request:
                self.recovery._run(self.config, True, self.service.controller.options)
                self.assertEqual([c.args[0] for c in request.call_args_list], actions)
                probe.assert_not_called()
                self.service.controller.start.assert_not_called()

    def test_legacy_stopped_helper_requires_admin_before_lease_or_startup(self):
        legacy = dict(self.stopped)
        del legacy['recovery_lease']
        with patch('coc_bot.host_bridge.request', return_value=legacy) as request, \
                patch('coc_bot.runtime.device_lease.DeviceLease') as lease:
            self.recovery._run(self.config, True, self.service.controller.options)
        request.assert_called_once_with('status')
        lease.assert_not_called()
        self.service.controller.start.assert_not_called()
        self.assertIn('administrator', self.service.platform.snapshot()['error'])

    def test_running_session_that_freezes_during_probe_is_left_idle(self):
        frozen = self.running | {'container': 'FROZEN'}
        with patch('coc_bot.host_bridge.request', side_effect=[self.running, self.running, frozen]) as request, \
                patch('coc_bot.runtime.device_lease.DeviceLease'), patch.object(self.recovery, '_probe', return_value=True):
            self.recovery._run(self.config, True, self.service.controller.options)
        self.assertEqual([c.args[0] for c in request.call_args_list], ['status'] * 3)
        self.service.controller.start.assert_not_called()
        self.assertFalse((self.config.data_dir/'runtime/renderer-recovery.json').exists())

    def test_legacy_frozen_session_unfreezes_under_live_lease_without_restart(self):
        live = dict(self.running)
        del live['recovery_lease']
        frozen = live | {'container': 'FROZEN'}
        for resumed, stalled in [(live, False), (live, True), (frozen, False)]:
            with self.subTest(resumed=resumed, stalled=stalled), \
                    patch('coc_bot.host_bridge.request', side_effect=[frozen, frozen, resumed]) as request, \
                    patch('coc_bot.runtime.device_lease.DeviceLease') as lease, \
                    patch.object(self.recovery, '_probe', return_value=stalled) as probe:
                self.service.controller.start.reset_mock()
                self.recovery._run(self.config, True, self.service.controller.options)
                lease.assert_called_once_with(self.device, recovery=False)
                self.assertEqual([c.args[0] for c in request.call_args_list], ['status', 'status', 'resume'])
                self.assertEqual(probe.called, resumed == live)
                self.assertEqual(self.service.controller.start.called, resumed == live and not stalled)
                self.assertFalse((self.config.data_dir/'runtime/renderer-recovery.json').exists())

    def test_pending_or_unreadable_receipts_survive_without_restart(self):
        for name, value in [('attack-planner/attack-pending.json', b'{"phase":"deploying"}'),
                            ('upgrades/state.json', b'{"pending":{"kind":"wall"}}'),
                            ('builder_base/visit.json', b'{"phase":"returning"}'),
                            ('layouts/state.json', b'{"last_survey":{"payment":true}}'),
                            ('upgrades/state.json', b'{')]:
            with self.subTest(name=name), patch('coc_bot.runtime.device_lease.DeviceLease'), \
                    patch('coc_bot.host_bridge.request', return_value=self.stopped) as request:
                path = self.config.data_dir / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(value)
                self.recovery._run(self.config, True, self.service.controller.options)
                request.assert_called_once_with('status')
                self.service.controller.start.assert_not_called()
                self.assertEqual(path.read_bytes(), value)
                self.assertFalse((self.config.data_dir/'runtime/renderer-recovery.json').exists())
                path.unlink()

    def test_restart_limit_survives_new_recovery_object_and_corruption_blocks(self):
        self.recovery._reserve_restart(self.config);self.recovery._reserve_restart(self.config)
        with self.assertRaisesRegex(RuntimeError,'limit reached'):
            CaptureRecovery(self.service)._reserve_restart(self.config)
        path=self.config.data_dir/'runtime/renderer-recovery.json';path.write_text('')
        with self.assertRaisesRegex(RuntimeError,'history needs review'):
            self.recovery._reserve_restart(self.config)
        self.assertEqual(path.read_text(),'')

    def test_probe_requires_shell_response_and_renderer_timeout(self):
        with patch('coc_bot.adb.client.AdbClient') as client,patch('coc_bot.adb.capture.ScreenCapture') as capture:
            capture.return_value.screenshot.side_effect=AdbError('capture timeout')
            timeout = AdbError('ADB command timed out')
            timeout.__cause__ = subprocess.TimeoutExpired('adb', 5)
            client.return_value.run_shell.side_effect=[SimpleNamespace(stdout='coc-render-probe\n'),timeout]
            self.assertTrue(self.recovery._probe(self.config))
            client.return_value.run_shell.side_effect=[SimpleNamespace(stdout='coc-render-probe\n'),AdbError('transport timeout')]
            with self.assertRaisesRegex(AdbError, 'transport timeout'):self.recovery._probe(self.config)
            client.return_value.run_shell.side_effect=[SimpleNamespace(stdout='coc-render-probe\n'),SimpleNamespace(stdout='Game layers')]
            with self.assertRaisesRegex(RuntimeError,'renderer responded'):self.recovery._probe(self.config)
            client.return_value.run_shell.side_effect=[AdbError('ADB offline')]
            with self.assertRaises(AdbError):self.recovery._probe(self.config)

    def test_single_recovery_blocks_tools_and_stop_prevents_retry(self):
        entered,release=threading.Event(),threading.Event()
        def work(*args):entered.set();release.wait(3)
        with patch('coc_bot.config.load_config',return_value=self.config),patch.object(self.recovery,'_run',side_effect=work):
            self.recovery.request('wrong-device');self.assertIsNone(self.recovery.thread)
            self.service.manual_owner='test';self.recovery.request(self.device);self.assertIsNone(self.recovery.thread)
            self.service.manual_owner=None
            self.recovery.request(self.device);self.assertTrue(entered.wait(1));thread=self.recovery.thread
            try:
                self.recovery.request(self.device);self.assertIs(self.recovery.thread,thread)
                with self.assertRaises(BusyError):self.service.idle()
                self.service.stop();self.assertTrue(self.recovery.cancel.is_set())
            finally:release.set();thread.join(3)
        self.service.controller.start.assert_not_called()
