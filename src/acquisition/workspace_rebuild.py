"""Inspect or rebuild owned workspace projections without starting an executor."""
import argparse
import json
import sqlite3
from pathlib import Path

from acquisition.bootstrap import build_workspace_projection
from acquisition.contracts import Conflict, NotFound


def main():
    parser=argparse.ArgumentParser(description='Offline workspace projection recovery. Legacy data stays protected; verified execution stays paused.')
    parser.add_argument('--root',type=Path,required=True,help='Existing server-owned workspace root')
    parser.add_argument('--expected-plan',help='Require the exact plan_id returned by inspection')
    parser.add_argument('operation',choices=('inspect','rebuild'))
    args=parser.parse_args()
    try:
        result=build_workspace_projection(args.root).run(apply=args.operation=='rebuild',expected_plan=args.expected_plan)
        print(json.dumps(result,indent=2))
        if result['blocked']:parser.exit(2,'Projection rebuild is blocked. Preserve the legacy journal and resolve the reported conflicts.\n')
    except (Conflict,NotFound,ValueError,OSError) as error:
        parser.exit(2,str(error)+'\n')
    except (sqlite3.Error,KeyError,TypeError,RecursionError):
        parser.exit(2,'Recovery metadata is incomplete or invalid. Preserve the original files and inspect the authoritative stores and legacy journal.\n')


if __name__=='__main__':main()
