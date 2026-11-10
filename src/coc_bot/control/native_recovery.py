"""Bounded local Waydroid recovery; no root/container or shared ADB-server restart."""
import os
from pathlib import Path
import subprocess
import time

from coc_bot.control.platform import Platform
from coc_bot.runtime.processes import run_process


class NativeRecoveryPlatform(Platform):
    def __init__(self):
        super().__init__()
        self.update('ready', 'Локальная сессия Android', ready=True)

    def read_status(self):
        result = run_process(['waydroid', 'status'], text=True, timeout=6, stop_check=self.cancel.is_set)
        if result.returncode:
            raise RuntimeError('Не удалось проверить состояние локального Waydroid')
        fields = dict(line.split(':', 1) for line in result.stdout.splitlines() if ':' in line)
        return {key.strip(): value.strip() for key, value in fields.items()}

    def status(self, config):
        fields = self.read_status()
        if (fields.get('Session') != 'RUNNING' or fields.get('Container') != 'RUNNING'
                or fields.get('IP address', '') + ':5555' != config.adb_device
                or not fields.get('Session user', '').endswith(f'({os.getuid()})')):
            raise RuntimeError('Локальная сессия или владелец Waydroid не подтверждены; перезапуск заблокирован')
        return fields

    def check_receipts(self, config):
        from coc_bot.accounts.store import read
        from coc_bot.attack.recovery import pending
        layout = read(config.data_dir/'layouts/state.json', {})
        visit = read(config.data_dir/'builder_base/visit.json', {})
        if (pending(config) or read(config.data_dir/'upgrades/state.json', {}).get('pending')
                or read(config.data_dir/'builder_base/upgrades.json', {}).get('pending')
                or layout.get('pending') or layout.get('last_survey', {}).get('payment')
                or read(config.data_dir/'reinforcements/state.json', {}).get('status') in ('send_pending','send_unconfirmed')
                or visit.get('phase') not in (None, 'collecting_resources', 'builder_home',
                                              'checking_upgrades', 'returning_to_home_village')):
            raise RuntimeError('Незавершённый бой или действие требует проверки; перезапуск Android заблокирован')

    def probe(self, config):
        """True only for failed Android capture/transport or active boot animation."""
        from coc_bot.adb.client import AdbClient, AdbError, AdbStopped
        from coc_bot.adb.capture import ScreenCapture
        client = AdbClient(config.adb_device)
        client.stop_check = self.cancel.is_set
        try:
            client.ensure_connected()
            ScreenCapture(client).screenshot(timeout_seconds=6)
            animation = client.run_shell('getprop init.svc.bootanim', timeout=4).stdout.strip()
            return animation == 'running'
        except AdbStopped:
            raise
        except AdbError:
            self.check_cancel()
            return True

    def ensure_capture(self, recovery, config):
        from coc_bot.runtime.device_lease import DeviceLease
        with DeviceLease(config.adb_device):
            self.cancel = recovery.cancel
            self.check_cancel()
            self.status(config)
            self.check_receipts(config)
            if not self.probe(config):return False
            if self.cancel.wait(20):self.check_cancel()
            if not self.probe(config):return False
            self.status(config)
            self.check_receipts(config)
            recovery._reserve_restart(config)
            self.check_cancel()
            self.update('recovering', 'Перезапускаю недоступную локальную сессию Waydroid')
            stopped = run_process(['waydroid', 'session', 'stop'], timeout=25, stop_check=self.cancel.is_set)
            self.check_cancel()
            if stopped.returncode or self.read_status().get('Session') != 'STOPPED':
                raise RuntimeError('Остановка локального Waydroid не подтверждена; повторный запуск заблокирован')
            log = config.data_dir/'runtime/waydroid-recovery.log'
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open('ab') as output:
                process = subprocess.Popen(['waydroid', 'session', 'start'], stdin=subprocess.DEVNULL,
                                           stdout=output, stderr=output, start_new_session=True)
            deadline = time.monotonic()+60
            while True:
                self.check_cancel()
                try:
                    self.status(config)
                    break
                except RuntimeError:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError('Waydroid не запустился; проверьте waydroid-recovery.log')
                    self.cancel.wait(1)
        return True

    def prepare(self, *, skip_updates=False, android_ensured=False):
        from coc_bot.adb.client import AdbClient
        from coc_bot.adb.capture import ScreenCapture
        from coc_bot.adb.app import AppController
        from coc_bot.config import load_config
        from coc_bot.runtime.device_lease import DeviceLease
        try:
            config = load_config()
            with DeviceLease(config.adb_device):
                self.check_cancel()
                client = AdbClient(config.adb_device)
                client.stop_check = self.cancel.is_set
                client.ensure_connected()
                self.update('checking_android', 'Ожидаю готовности локального Android')
                self.wait_for_android(client)
                self.check_cancel()
                app = AppController(client, config, ScreenCapture(client))
                app.stop_check = self.cancel.is_set
                self.update('opening_game', 'Запускаю Clash после восстановления Android')
                app.launch()
                if not app.wait_until_ready(timeout_seconds=90):
                    raise RuntimeError('Clash не загрузился после восстановления Android')
                self.check_cancel()
                self.update('ready', 'Android и Clash восстановлены', ready=True)
        except Exception as exc:
            self.update('error', str(exc), error=str(exc))
