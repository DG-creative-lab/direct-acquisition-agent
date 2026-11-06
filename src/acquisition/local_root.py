"""Local workspace filesystem controls shared by online and offline entry points."""
import os
import stat
from contextlib import contextmanager
from pathlib import Path

from acquisition.contracts import Conflict


CHECKPOINT_FILE = '.acquisition-checkpoint.json'
INSPECTION_ONLY = 'This checkpoint is inspection-only. Workers and workspace mutations are disabled.'


def inspection_only(path):
    absolute = Path(os.path.abspath(path))
    if any(os.path.lexists(parent / CHECKPOINT_FILE) for parent in (absolute, *absolute.parents)):
        return True
    resolved = absolute.resolve()
    return resolved != absolute and any(
        os.path.lexists(parent / CHECKPOINT_FILE) for parent in (resolved, *resolved.parents)
    )


def require_live_root(path):
    if inspection_only(path):
        raise Conflict(INSPECTION_ONLY)


@contextmanager
def workspace_root_lock(root):
    """Keep the lock inode in place across server starts and offline operations."""
    import fcntl

    fd = os.open(Path(root) / 'server.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Conflict('Use the original regular workspace lock file')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)
