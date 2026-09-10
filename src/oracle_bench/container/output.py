"""Write streamed agent evidence without persisting the selected credential."""

from pathlib import Path


class RedactedOutput:
    def __init__(self, path: Path, secrets: tuple[str, ...] = (), *, append=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("ab" if append else "wb")
        self.secrets = tuple(value.encode() for value in secrets if value)
        self.pending = b""

    def write(self, chunk: bytes) -> None:
        # Keep a possible secret prefix across SDK chunks. Replacing each chunk
        # independently would leak credentials split across network frames.
        data = self.pending + chunk
        for secret in self.secrets:
            data = data.replace(secret, b"[REDACTED]")
        keep = 0
        for secret in self.secrets:
            for size in range(1, min(len(secret), len(data) + 1)):
                if data.endswith(secret[:size]):
                    keep = max(keep, size)
        self.pending = data[-keep:] if keep else b""
        self.stream.write(data[:-keep] if keep else data)
        self.stream.flush()

    def close(self) -> None:
        self.stream.write(self.pending)
        self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
