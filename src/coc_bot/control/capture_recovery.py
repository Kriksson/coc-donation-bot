"""Bounded managed-session recovery after repeated Android capture failures."""
import json
import math
import subprocess
import threading
import time
from contextvars import copy_context

from loguru import logger


class CaptureRecovery:
    def __init__(self, service):
        self.service = service
        self.cancel = threading.Event()
        self.thread = None
        self.last_attempt = float('-inf')

    @property
    def active(self):
        return self.thread is not None and self.thread.is_alive()

    def request(self, device):
        from coc_bot.config import load_config
        service = self.service
        with service.lock:
            platform = service.platform
            if (platform is None or self.active or self.cancel.is_set() or
                    platform.snapshot()['busy'] or not platform.snapshot()['ready'] or
                    service.manual_owner or service.settings_update or
                    any(p.controller.snapshot().active or p.manual_owner or p.settings_update for p in service.peers)):
                return
            state = service.controller.snapshot()
            if state.closing or state.stop_requested or state.active and service.operation != 'bot':
                return
            config = load_config()
            if device != config.adb_device or time.monotonic() - self.last_attempt < 300:
                return
            self.last_attempt = time.monotonic()
            self.cancel = threading.Event()
            resume = state.active and service.operation == 'bot'
            options = service.controller.options
            platform.recovering = True
            platform.update('recovering', 'Checking stalled Android capture')
            self.thread = threading.Thread(target=copy_context().run, args=(self._run, config, resume, options),
                                           name='capture-recovery', daemon=True)
            self.thread.start()

    def check_cancel(self):
        if self.cancel.is_set():
            raise RuntimeError('Android recovery canceled by Stop. Use Retry startup when ready.')

    def _probe(self, config):
        """Must own the device. A web/ICE failure alone cannot restart Android."""
        from coc_bot.adb.client import AdbClient, AdbError
        from coc_bot.adb.capture import ScreenCapture
        client = AdbClient(config.adb_device)
        client.stop_check = self.cancel.is_set
        try:
            ScreenCapture(client).screenshot(timeout_seconds=6)
            return False
        except AdbError:
            self.check_cancel()
        result = client.run_shell('echo coc-render-probe', timeout=4)
        if result.stdout.strip() != 'coc-render-probe':
            raise RuntimeError('Android shell is unavailable; automatic renderer restart blocked')
        try:
            client.run_shell('dumpsys SurfaceFlinger --list', timeout=5)
        except AdbError as exc:
            self.check_cancel()
            if isinstance(exc.__cause__, subprocess.TimeoutExpired):
                return True
            raise
        raise RuntimeError('Capture failed but Android renderer responded; automatic restart blocked')

    def _reserve_restart(self, config):
        from coc_bot.upgrades.runner import write_json
        path = config.data_dir / 'runtime/renderer-recovery.json'
        try:
            value = json.loads(path.read_text()) if path.exists() else {}
            attempts = value.get('attempts', [])
            if not isinstance(attempts, list) or any(type(t) not in (float, int) or not math.isfinite(t) for t in attempts):
                raise ValueError('invalid restart history')
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise RuntimeError('Renderer restart history needs review; automatic restart blocked') from exc
        now = time.time()
        recent = [t for t in attempts if t >= now - 3600]
        if len(recent) >= 2:
            raise RuntimeError('Android recovery limit reached (two restarts per hour). Inspect the host.')
        write_json(path, {'attempts': [*recent, now]})

    def _check_receipts(self, config):
        from coc_bot.accounts.startup import unresolved
        from coc_bot.accounts.store import read
        from coc_bot.config import load_config
        if self.service.accounts:
            store = self.service.accounts.store
            store.require_ready()
            with store.scope():
                config = load_config()
        if (unresolved(config) or read(config.data_dir / 'builder_base/upgrades.json', {}).get('pending')
                or read(config.data_dir / 'reinforcements/state.json', {}).get('status')
                in ('send_pending', 'send_unconfirmed')):
            raise RuntimeError('Review the pending action before Android recovery')

    def _probe_running(self, config, status):
        from coc_bot.host_bridge import request

        def running_device(status):
            return (status['session'] == 'RUNNING' and status['ip']
                    and config.adb_device == str(status['ip']) + ':5555')

        if not running_device(status):
            raise RuntimeError('Waydroid device or session is uncertain; automatic restart blocked')
        frozen = status['container'] == 'FROZEN'
        if frozen:
            self.check_cancel()
            status = request('resume')
        if not running_device(status) or status['container'] != 'RUNNING':
            raise RuntimeError('Waydroid is not confirmed running; automatic restart blocked')
        self.check_cancel()
        restart = self._probe(config)
        if restart and frozen:
            raise RuntimeError('Capture is still unavailable after unfreezing Waydroid; retry startup')
        return restart

    def _ensure_capture_session(self, config, platform):
        from coc_bot.runtime.device_lease import DeviceLease
        from coc_bot.host_bridge import request, startup_status, HELPER_REFRESH_REQUIRED, STARTUP_TIMEOUT_SECONDS
        initial = startup_status()
        stopped = initial['session'] == initial['container'] == 'STOPPED'
        with DeviceLease(config.adb_device, recovery=stopped):
            self.check_cancel()
            self._check_receipts(config)
            status = startup_status()
            if stopped != (status['session'] == status['container'] == 'STOPPED'):
                raise RuntimeError('Waydroid session changed during capture recovery')
            if stopped and status['ip'] and config.adb_device != str(status['ip']) + ':5555':
                raise RuntimeError('Managed device changed during capture recovery')
            if not stopped and not self._probe_running(config, status):
                return False
            self.check_cancel()
            if status.get('recovery_lease') is not True:
                raise RuntimeError(HELPER_REFRESH_REQUIRED)
            if not stopped:
                # Android may have gone idle while screencap and dumpsys timed
                # out. Only stop a renderer that is still on the owned device.
                latest = startup_status()
                if (latest['session'], latest['container'], latest['ip']) != ('RUNNING', 'RUNNING', status['ip']):
                    raise RuntimeError('Waydroid changed during the renderer probe; automatic restart blocked')
            self._reserve_restart(config)
            self.check_cancel()
            if not stopped:
                platform.update('recovering', 'Restarting stalled Waydroid renderer')
                request('stop', timeout=60)
                self.check_cancel()
            platform.update('recovering', 'Starting managed Waydroid session')
            request('ensure', timeout=STARTUP_TIMEOUT_SECONDS)
        return True

    def _run(self, config, resume, options):
        service, platform = self.service, self.service.platform
        try:
            logger.warning('Repeated capture failures — pausing inputs to check Android renderer')
            service.controller.stop()
            deadline = time.monotonic() + 45
            while not service.controller.wait(.2):
                self.check_cancel()
                if time.monotonic() >= deadline:
                    raise RuntimeError('Bot did not release Android; automatic restart blocked')
            self.check_cancel()
            if self._ensure_capture_session(config, platform):
                self.check_cancel()
                platform.cancel = self.cancel
                # Startup may publish a new IP. Reacquire its ordinary lease
                # before disconnecting ADB, launching Clash or checking capture.
                platform.prepare(skip_updates=True, android_ensured=True)
                self.check_cancel()
                if not platform.snapshot()['ready']:
                    raise RuntimeError(platform.snapshot()['error'] or 'Android recovery failed')
            else:
                platform.update('ready', 'Android capture recovered', ready=True)
            with service.lock:
                self.check_cancel()
                if resume and not service.controller.snapshot().closing:
                    if not service._start_bot(options):
                        raise RuntimeError('Android recovered, but the bot could not resume')
            logger.info('Android capture recovered{}', ' — bot resumed with checkpoint recovery' if resume else '')
        except Exception as exc:
            platform.update('error', str(exc), error=str(exc))
            logger.error('Automatic Android recovery stopped: {}', exc)
        finally:
            platform.recovering = False
