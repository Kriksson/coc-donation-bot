"""Detect ineffective inputs without treating an idle village as a stalled game."""
from contextlib import contextmanager
import json
import time

import cv2
import numpy as np
from loguru import logger


class StalledScreen(RuntimeError):
    pass


class RecoveryLimit(RuntimeError):
    pass


class ProgressWatchdog:
    def __init__(self, config, stopping, *, clock=time.monotonic, timeout=90):
        self.config, self.stopping, self.clock = config, stopping, clock
        self.timeout = timeout
        self.reference = None
        self.since = None
        self.actions = 0
        self.last_action = None
        self.blocked = False
        self.suspended = 0
        self.status = None
        self.boot_frames = 0

    def action(self):
        if not self.suspended and self.reference is not None:
            # Begin the deadline on the first input, never on passive waiting.
            now = self.clock()
            if self.last_action is not None and now-self.last_action > self.timeout:
                self.actions = 0
            if not self.actions:self.since = now
            self.last_action = now
            self.actions += 1

    def observe(self, frame):
        if self.suspended or self.stopping():return
        from coc_bot.vision.android_boot import android_boot_frame
        if android_boot_frame(frame):
            from coc_bot.adb.client import AdbError
            from coc_bot.runtime.verification import save_frame
            if not self.status:
                save_frame(self.config, 'android-boot-stalled', frame)
            self.status = 'Android показывает загрузочный экран — проверяю соединение'
            self.boot_frames += 1
            if self.boot_frames >= 3:
                from coc_bot.adb.capture_coordinator import request_capture_recovery
                request_capture_recovery(self.config.adb_device)
            raise AdbError(self.status)
        self.boot_frames = 0
        if self.status and self.status.startswith('Android показывает'):self.status = None
        if self.blocked:
            raise StalledScreen('Экран завис: ожидается восстановление игры')
        small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (96, 54), interpolation=cv2.INTER_AREA)
        changed = self.reference is None
        if not changed:
            difference = cv2.absdiff(small, self.reference)
            changed = float(difference.mean()) > 2 or float((difference > 15).mean()) > .025
        if changed:
            self.reference = small
            self.since = None
            self.actions = 0
            return
        if self.actions < 3 or self.clock() - self.since < self.timeout:return
        self.blocked = True
        from coc_bot.runtime.verification import save_frame, record_failure
        evidence = save_frame(self.config, 'watchdog-stalled', frame)
        self.status = 'Экран не меняется после действий — восстанавливаю игру'
        record_failure(self.config, 'watchdog', self.status, evidence=evidence)
        logger.warning('{}; действий: {}, ожидание: {:.0f} с', self.status, self.actions, self.clock()-self.since)
        raise StalledScreen(self.status)

    @contextmanager
    def recovery(self):
        self.suspended += 1
        try:
            yield
        finally:
            self.suspended -= 1
            self.reference = None
            self.since = None
            self.actions = 0
            self.blocked = False


class RecoveryBudget:
    """Survives worker restarts; recovery itself is never evidence of progress."""
    def __init__(self, config, *, clock=time.time):
        self.path = config.data_dir / 'runtime/watchdog-recovery.json'
        self.clock = clock

    def reserve(self, reason):
        from coc_bot.upgrades.runner import write_json
        import math
        try:
            state = json.loads(self.path.read_text()) if self.path.exists() else {}
            attempts = state.get('attempts', [])
            if not isinstance(attempts, list) or any(type(t) not in (int,float) or not math.isfinite(t) for t in attempts):
                raise ValueError('invalid attempts')
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise RecoveryLimit('Не удалось проверить историю восстановления — бот остановлен') from exc
        now = self.clock()
        recent = [t for t in attempts if t >= now - 900]
        if len(recent) >= 2:
            raise RecoveryLimit('Восстановление не помогло: лимит 2 попытки за 15 минут. Бот остановлен; проверьте снимок и журнал')
        write_json(self.path, {'attempts': [*recent, now], 'reason': reason, 'updated_at': now})
        return len(recent)+1
