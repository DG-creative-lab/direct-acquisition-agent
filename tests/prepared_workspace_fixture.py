"""Private copies of a quiescent workspace prepared through the real workflow."""

from copy import deepcopy
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory


def prepared_workspace(test_class, setup, model_attribute):
    seed = test_class('runTest')
    try:
        setup(seed)
        # All preparation steps are synchronous and Database.connect closes its
        # connections. Refuse an uncheckpointed WAL rather than copy a live store.
        if list(seed.root.rglob('*.sqlite-wal')):
            raise RuntimeError('Prepared workspace must have closed SQLite connections')
        directory = TemporaryDirectory()
        test_class.addClassCleanup(directory.cleanup)
        copytree(seed.root, directory.name, dirs_exist_ok=True)
        return {'root': Path(directory.name), 'now': seed.now,
                'c': seed.c, 'sid': seed.sid,
                'model': deepcopy(getattr(seed, model_attribute))}
    finally:
        seed.doCleanups()
