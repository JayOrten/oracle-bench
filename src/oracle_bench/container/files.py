"""Explicit file transfers over the Docker SDK's tar archive interface."""

import tarfile
import tempfile
from pathlib import Path, PurePosixPath


def upload(container, source: Path, destination: str, *, contents=False) -> None:
    target = PurePosixPath(destination)
    with tempfile.TemporaryFile() as buffer:
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            if contents:
                for child in sorted(source.iterdir()):
                    archive.add(child, arcname=child.name)
                parent = str(target)
            else:
                archive.add(source, arcname=target.name)
                parent = str(target.parent)
        buffer.seek(0)
        container.put_archive(parent, buffer)


def download(container, source: str, destination: Path, *, contents=False, secrets=()) -> None:
    """Export regular files only; never let container paths choose host targets."""
    from oracle_bench.container.output import RedactedOutput

    chunks, metadata = container.get_archive(source)
    with tempfile.TemporaryFile() as buffer:
        for chunk in chunks:
            buffer.write(chunk)
        buffer.seek(0)
        with tarfile.open(fileobj=buffer) as archive:
            members = archive.getmembers()
            for member in members:
                path = PurePosixPath(member.name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or not (member.isfile() or member.isdir())
                ):
                    raise ValueError(f"Unsafe container archive entry: {member.name}")
                if contents and (not path.parts or path.parts[0] != metadata["name"]):
                    raise ValueError(f"Unexpected container archive root: {member.name}")
            files = [member for member in members if member.isfile()]
            if not contents and (len(files) != 1 or len(members) != 1):
                raise ValueError("Expected exactly one regular file in container archive")
            for member in files:
                # Docker archives include the requested directory as their root.
                relative = PurePosixPath(member.name).parts[1:]
                target = destination.joinpath(*relative) if contents else destination
                if target.is_symlink() or any(parent.is_symlink() for parent in target.parents):
                    raise ValueError(f"Refusing to overwrite a host symlink: {target}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as stream, RedactedOutput(target, secrets) as out:
                    while chunk := stream.read(65536):
                        out.write(chunk)
                target.chmod(member.mode & 0o777)
