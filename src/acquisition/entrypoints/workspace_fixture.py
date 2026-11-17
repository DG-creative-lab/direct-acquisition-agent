"""Initialize a new verified workspace for the offline fixture journey."""
import argparse
import json
from pathlib import Path

from acquisition.bootstrap import initialize_fixture_workspace
from acquisition.bootstrap import build_recovery_error_boundary
from acquisition.application import RecoveryStorageUnavailable
from acquisition.contracts import Conflict


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    try:
        with build_recovery_error_boundary():
            initialize_fixture_workspace(args.root)
    except (Conflict, ValueError, OSError, RecoveryStorageUnavailable) as error:
        parser.exit(2, str(error) + '\n')
    print(json.dumps({'status': 'initialized', 'execution': 'fixture-only', 'paid_inference': 'paused'}))


if __name__ == '__main__':
    main()
