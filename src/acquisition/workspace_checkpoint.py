"""Create, verify, restore or reconcile a local workspace checkpoint offline."""
import argparse
import json
import sqlite3
from pathlib import Path

from acquisition.bootstrap import build_checkpoint_reconciliation, build_workspace_checkpoint
from acquisition.contracts import Conflict


def main():
    parser = argparse.ArgumentParser(description='Cold SQLite checkpoints for inspection-only recovery')
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create', help='Snapshot a quiesced, verified-paused workspace')
    verify = commands.add_parser('verify', help='Validate a bundle without writing to it')
    restore = commands.add_parser('restore', help='Restore a verified bundle into a new or empty root')
    reconcile = commands.add_parser('reconcile', help='Inspect scoped evidence from a later checkpoint without writing')
    for command in (create, verify, restore, reconcile):
        command.add_argument('--bundle', type=Path, required=True)
    for command in (create, restore):
        command.add_argument('--root', type=Path, required=True)
    restore.add_argument('--checkpoint-id', required=True)
    reconcile.add_argument('--checkpoint-id', required=True)
    reconcile.add_argument('--organization', required=True)
    reconcile.add_argument('--later-bundle', type=Path)
    reconcile.add_argument('--later-checkpoint-id')
    args = parser.parse_args()
    try:
        if args.command == 'reconcile':
            report = build_checkpoint_reconciliation().inspect(
                args.bundle, args.checkpoint_id, args.organization,
                later_bundle=args.later_bundle, later_checkpoint_id=args.later_checkpoint_id,
            )
            print(json.dumps(report, indent=2))
            return
        checkpoint = build_workspace_checkpoint()
        if args.command == 'create':
            manifest = checkpoint.create(args.root, args.bundle)
        elif args.command == 'verify':
            manifest = checkpoint.verify(args.bundle)
        else:
            manifest = checkpoint.restore(args.bundle, args.root, args.checkpoint_id)
        print(json.dumps({
            'status': {'create': 'created', 'verify': 'verified', 'restore': 'restored'}[args.command],
            'mode': 'inspection-only', 'post_checkpoint_effects': 'unknown',
            'manifest': manifest,
        }, indent=2))
    except BlockingIOError:
        parser.exit(2, 'The workspace is locked. Stop the server and local writers before backup.\n')
    except Conflict as error:
        parser.exit(2, str(error) + '\n')
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
        parser.exit(2, 'Checkpoint files are unavailable, busy or invalid. Preserve the originals and inspect the sources.\n')


if __name__ == '__main__':
    main()
