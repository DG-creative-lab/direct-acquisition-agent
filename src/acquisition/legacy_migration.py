"""Print a read-only, versioned migration proposal. No apply or activation command."""
import argparse
import json
import sqlite3
from pathlib import Path

from acquisition.bootstrap import build_legacy_migration_inventory
from acquisition.contracts import Conflict


def main():
    parser = argparse.ArgumentParser(description='Read-only legacy inventory. No migration, certification or execution activation.')
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('operation',choices=('inspect',))
    args = parser.parse_args()
    try:
        result = build_legacy_migration_inventory(args.root).inspect()
        print(json.dumps(result,indent=2))
    except (Conflict,ValueError,OSError) as error:
        parser.exit(2,str(error)+'\n')
    except (sqlite3.Error,KeyError,TypeError,RecursionError):
        parser.exit(2,'Inspection metadata is unsupported or incomplete. Preserve the original files; no migration was performed.\n')


if __name__ == '__main__':main()
