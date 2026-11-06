"""Inspect legacy history and explicitly apply supported paused ownership bindings."""
import argparse
import json
import sqlite3
from pathlib import Path

from acquisition.bootstrap import build_legacy_migration_inventory
from acquisition.contracts import Conflict


def main():
    parser = argparse.ArgumentParser(description='Inspect legacy history, apply a paused migration or read its receipt.')
    parser.add_argument('--root',type=Path,required=True)
    commands = parser.add_subparsers(dest='operation', required=True)
    commands.add_parser('inspect', help='Read-only inventory and migration plan')
    apply = commands.add_parser('apply', help='Bind supported legacy ownership in a sealed store')
    apply.add_argument('--plan-id', required=True)
    receipt = commands.add_parser('receipt', help='Read an existing migration receipt without applying anything')
    receipt.add_argument('--plan-id', required=True)
    args = parser.parse_args()
    try:
        migration = build_legacy_migration_inventory(args.root)
        if args.operation == 'inspect':
            result = migration.inspect()
        elif args.operation == 'receipt':
            result = migration.receipt(args.plan_id)
        else:
            result = migration.apply(args.plan_id)
        print(json.dumps(result,indent=2))
    except (Conflict,ValueError,OSError) as error:
        parser.exit(2,str(error)+'\n')
    except (sqlite3.Error,KeyError,TypeError,RecursionError):
        parser.exit(2,'Legacy sources are unavailable, busy or unsupported. Preserve the original files and inspect again.\n')


if __name__ == '__main__':main()
