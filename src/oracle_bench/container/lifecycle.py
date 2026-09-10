"""Failure handling shared by container execution and evidence collection."""

import sys
from contextlib import contextmanager
from threading import Event, Timer

from docker.errors import DockerException


@contextmanager
def preserve_failure(note: str):
    """Use inside a finally block when cleanup must preserve the original error.

    Cleanup failures still propagate after successful work. During unwinding,
    annotate the original failure instead of replacing it with a secondary one.
    """
    original = sys.exception()
    try:
        yield
    except Exception:
        if original is None:
            raise
        original.add_note(note)


@contextmanager
def execution_watchdog(container, timeout: float):
    """Stop a stalled supervisor after its own deadline and cleanup grace period."""
    fired = Event()

    def abort():
        fired.set()
        try:
            container.kill()
        except DockerException:
            pass  # The foreground exec reports the transport or supervisor failure.

    # Allow ten seconds for child-process cleanup plus time for SDK transport.
    timer = Timer(timeout + 30, abort)
    timer.daemon = True
    timer.start()
    try:
        yield fired
    finally:
        timer.cancel()
        timer.join()
