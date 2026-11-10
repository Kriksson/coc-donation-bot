from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from coc_bot.config import BotConfig
from coc_bot.runtime.persistence import load_runtime_state, save_runtime_state


class RuntimeTracker:
    """Track active donation-loop runtime with persisted state."""

    def __init__(self, config: BotConfig, state_path: Path | None = None) -> None:
        self.config = config
        self.state_path = state_path or config.data_dir / "runtime_state.json"
        self.state = load_runtime_state(self.state_path)
        self._loop_start: float | None = None
        self._paused = False
        # Runtime and attack receipts share this persisted state across threads.
        self._lock = threading.RLock()

    @property
    def active_seconds(self) -> float:
        return self.state.active_seconds


    def start_loop_timing(self) -> None:
        with self._lock:
            if self._loop_start is None:
                self._loop_start = time.monotonic()

    def pause(self) -> None:
        with self._lock:
            self._flush()
            self._paused = True
            self._loop_start = None

    def resume(self) -> None:
        with self._lock:
            self._paused = False
            self._loop_start = time.monotonic()

    def _flush(self) -> None:
        with self._lock:
            if self._loop_start is None or self._paused:
                return
            now = time.monotonic()
            elapsed = now - self._loop_start
            self.state.active_seconds += elapsed
            self._loop_start = now
            save_runtime_state(self.state_path, self.state)

    def tick(self) -> None:
        self._flush()

    def farm_interval_due(self, interval_seconds: int, *, now=None) -> bool | None:
        """Return due status from the last fought attack; None means bad persisted time."""
        if type(interval_seconds) is not int or not 60 <= interval_seconds <= 86400:
            raise ValueError('Farm interval must be between 60 and 86400 seconds')
        last=self.state.last_farm_at
        if last is None:return True
        try:
            moment=datetime.fromisoformat(last)
            if moment.tzinfo is None:return None
            current=(now or datetime.now(timezone.utc))
            if current.tzinfo is None:return None
            elapsed=(current.astimezone(timezone.utc)-moment.astimezone(timezone.utc)).total_seconds()
            if elapsed < 0:return None
        except (TypeError,ValueError,OverflowError):
            return None
        return elapsed >= interval_seconds


    def mark_farm_success(self, *, attack_id=None) -> None:
        """Record that a farm battle was fought (success or post-deploy leave fail)."""
        with self._lock:
            if attack_id and self.state.last_completed_attack_id == attack_id:
                return
            previous=(self.state.last_farm_at,self.state.farm_paused_at,
                      self.state.next_farm_interval_seconds,self.state.last_completed_attack_id)
            self.state.last_farm_at = datetime.now(timezone.utc).isoformat()
            self.state.farm_paused_at = None
            self.state.next_farm_interval_seconds = None
            if attack_id:
                from dataclasses import asdict
                from coc_bot.attack.recovery import atomic_json
                self.state.last_completed_attack_id = attack_id
                try:
                    atomic_json(self.state_path, asdict(self.state))
                except OSError:
                    (self.state.last_farm_at,self.state.farm_paused_at,
                     self.state.next_farm_interval_seconds,self.state.last_completed_attack_id)=previous
                    raise
            else:
                save_runtime_state(self.state_path, self.state)
        # Legacy interval fields remain readable for old state files. Normal
        # automation schedules its next attack from verified storage demand.
        logger.info("Recorded farm completion at {} — refill follows resource levels", self.state.last_farm_at)
