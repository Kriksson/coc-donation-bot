"""Bounded, sequence-numbered activity history for reconnecting interfaces."""
from collections import deque
from datetime import datetime, timezone
import threading
import time
from coc_bot.control.event_labels import present_event


class EventHistory:
    def __init__(self, capacity=500):
        self._entries = deque(maxlen=capacity)
        self._sequence = 0
        self._lock = threading.Lock()
        self._last_at = 0.0

    def append(self, level, text):
        with self._lock:
            text=str(text)[:4000]
            now=time.monotonic()
            previous=self._entries[-1] if self._entries else None
            repeated=bool(previous and previous['level']==level and previous['text']==text
                          and now-self._last_at<10)
            self._sequence += 1
            entry={"id": self._sequence, "level": level,"text":text,
                   "group":previous['group'] if repeated else self._sequence,
                   "at":datetime.now(timezone.utc).isoformat(),
                   "count":previous['count']+1 if repeated else 1,
                   **present_event(level,text)}
            if repeated:
                entry['replaces']=previous['id']
                self._entries.pop()
            self._entries.append(entry)
            self._last_at=now

    def since(self, cursor=0):
        with self._lock:
            first = self._entries[0]["id"] if self._entries else self._sequence + 1
            return {"cursor": self._sequence, "reset": cursor < first - 1,
                    "entries": [dict(e) for e in self._entries if e["id"] > cursor]}
