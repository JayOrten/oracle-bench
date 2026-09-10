"""Wall-clock deadlines for synchronous SDK image operations on Unix hosts."""

import signal
from contextlib import contextmanager


@contextmanager
def setup_deadline(seconds: float):
    """Interrupt even a silent pull/build stream and restore the caller's handler.

    The CLI runs on the main thread. Docker's streaming APIs can disable socket
    timeouts, so their HTTP timeout alone cannot enforce our setup budget.
    """

    def expired(signum, frame):
        raise TimeoutError(f"Docker setup exceeded {seconds:g} seconds")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
