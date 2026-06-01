"""Timestamped logging for pipeline runs.

Installs a global wrapper around builtins.print that prefixes every output
line with a wall-clock timestamp. Per-line timestamps let a long pipeline run
be read as a profile — you can see where time goes between steps and within a
step (which website's crawl stalls, which extraction is slow, etc.).

Scoped to the pipeline entry point: main.py calls install(). Standalone module
or script usage is unaffected.
"""

import builtins
import time
from datetime import datetime

_real_print = builtins.print

# Whether the next write begins a fresh line. Tracked so that a print(..., end=' ')
# followed by another print (e.g. uploader's "Uploading x... " then "✓") does not
# stamp a second timestamp mid-line. Safe under asyncio: print is synchronous and
# never yields, so concurrent workers can't interleave a single call.
_at_line_start = True


def timestamp():
    """Return current wall-clock time as HH:MM:SS."""
    return datetime.now().strftime('%H:%M:%S')


def _timestamped_print(*args, sep=' ', end='\n', **kwargs):
    global _at_line_start
    text = sep.join(str(a) for a in args) + end
    if not text:
        return

    ts = timestamp()
    segments = text.split('\n')
    out = []
    for i, seg in enumerate(segments):
        if _at_line_start and seg:
            out.append(f'[{ts}] ')
        out.append(seg)
        is_last = i == len(segments) - 1
        if not is_last:
            out.append('\n')
            _at_line_start = True
        else:
            _at_line_start = seg == ''

    _real_print(''.join(out), end='', **kwargs)


def install():
    """Replace builtins.print with the timestamped variant (idempotent)."""
    builtins.print = _timestamped_print


def format_duration(seconds):
    """Render a duration as e.g. '8s', '4m12s', or '1h03m07s'."""
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m{secs:02d}s"


class StepTimer:
    """Records wall-clock duration of named pipeline steps for profiling.

    Call start(name) at each step boundary; the previously running step is
    closed out automatically. steps/total expose the collected timings for an
    end-of-run summary.
    """

    def __init__(self):
        self._steps = []
        self._current = None
        self._start = None

    def start(self, name):
        """Begin timing a step, closing out any step already in progress."""
        self.stop()
        self._current = name
        self._start = time.monotonic()

    def stop(self):
        """Close the running step. Returns (name, seconds) or None if idle."""
        if self._current is None:
            return None
        elapsed = time.monotonic() - self._start
        name = self._current
        self._steps.append((name, elapsed))
        self._current = None
        return name, elapsed

    @property
    def steps(self):
        return list(self._steps)

    @property
    def total(self):
        return sum(seconds for _, seconds in self._steps)
