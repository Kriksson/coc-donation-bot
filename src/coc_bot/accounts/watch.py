"""Count verified donor chat time separately from maintenance and travel."""
import math


class DonorWatch:
    def __init__(self, clock):
        self.clock = clock
        self.started = clock()
        self.seconds = 0.0
        self.visit_start = 0.0

    def begin_visit(self):
        self.visit_start = self.seconds

    def credit(self, seconds):
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
            return
        # Credits describe work within this coordinator's lifetime, not time
        # from an older bot or a stopped session.
        self.seconds = min(max(0, self.clock() - self.started), self.seconds + seconds)

    def funded(self):
        away = max(0, self.clock() - self.started - self.seconds)
        return self.seconds >= 2 * away

    def ready(self, required):
        return self.seconds - self.visit_start >= required and self.funded()
