"""How much of the stream arrives: frames received against frames streamed.

The token streams at a fixed rate (scaled by its own clock, see device.py's
ODR window), so the frames it sent over a stretch of stream are known from the
time between the first and the last frame that arrived. A rate switch over the
live link starts a new stretch. Stretches shorter than MIN_SPAN_S say nothing
and are left out.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_SPAN_S = 2.0
# A session counts toward the repair issue only with this much stream: a quick
# press-and-sleep says little about the link.
SESSION_MIN_S = 20.0
LOSSY_PCT = 70.0  # a session that got less than this is lossy
CLEAN_PCT = 90.0  # one that got this much clears the issue
LOSSY_SESSIONS = 3  # lossy sessions in a row before the owner is told


@dataclass(slots=True)
class _Stretch:
    rate: float
    first: float | None = None
    last: float = 0.0
    frames: int = 0  # after the first one


class LinkQuality:
    """Frames received, % of streamed, for the current or the last session."""

    def __init__(self) -> None:
        self._stretch: _Stretch | None = None
        self._got = 0.0
        self._sent = 0.0
        self._span = 0.0
        self.lossy_in_a_row = 0
        self.last_pct: float | None = None  # the last finished session

    def start(self, rate: float) -> None:
        """A stream starts, or switches rate, at ``rate`` frames per second."""
        self._close()
        self._stretch = _Stretch(rate)

    def stop(self) -> None:
        """The stream is stopped on purpose (a battery pause): the silence until
        the next start is not loss."""
        self._close()

    def frame(self, t: float) -> None:
        s = self._stretch
        if s is None:
            return
        if s.first is None:
            s.first = t
        else:
            s.frames += 1
        s.last = t

    def _close(self) -> None:
        s, self._stretch = self._stretch, None
        if s is None or s.first is None:
            return
        span = s.last - s.first
        if span < MIN_SPAN_S:
            return
        self._got += s.frames
        self._sent += span * s.rate
        self._span += span

    @property
    def pct(self) -> float | None:
        """Received, % of streamed, over the session so far (closed stretches
        plus the open one)."""
        got, sent = self._got, self._sent
        s = self._stretch
        if s is not None and s.first is not None and s.last - s.first >= MIN_SPAN_S:
            got += s.frames
            sent += (s.last - s.first) * s.rate
        if sent <= 0:
            return None
        return round(min(100.0, 100.0 * got / sent), 1)

    def end_session(self) -> float | None:
        """The link is gone: settle the session. Returns its % or None when it
        streamed too briefly to count."""
        self._close()
        pct = self.pct if self._span >= SESSION_MIN_S else None
        self._got = self._sent = self._span = 0.0
        if pct is None:
            return None
        self.last_pct = pct
        if pct < LOSSY_PCT:
            self.lossy_in_a_row += 1
        elif pct >= CLEAN_PCT:
            self.lossy_in_a_row = 0
        return pct

    @property
    def lossy(self) -> bool:
        return self.lossy_in_a_row >= LOSSY_SESSIONS
