"""Retry policy for agent turns interrupted by transient provider failures."""

TRANSIENT_ERROR_MARKERS = (
    "429 too many requests",
    "502 bad gateway",
    "503 service unavailable",
    "504 gateway timeout",
    "connection reset",
    "error decoding response body",
    "network error",
    "stream closed before completion",
    "stream disconnected",
    "the operation was aborted",
)

# These are delays before three retries, not three total attempts. Provider
# throttles often outlast the harness's own rapid request retries.
RETRY_DELAYS_SECONDS = (30, 90, 180)


def is_transient_failure(result: dict) -> bool:
    """Return whether a failed turn ended for a recognized transport reason."""
    if result["status"] != "failed":
        return False
    details = " ".join(str(error).lower() for error in result["errors"])
    return any(marker in details for marker in TRANSIENT_ERROR_MARKERS)
