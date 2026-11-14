"""Prepare or inspect immutable offline audience decisions. No outbound authority."""

import argparse
import json
from pathlib import Path

from acquisition.bootstrap import build_audience_decisions
from acquisition.contracts import NotFound


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',required=True,type=Path)
    parser.add_argument('--organization',required=True,help='Trusted local scope, not hosted authentication')
    parser.add_argument('--profile',required=True,choices=('iwoca','fielddesk'))
    parser.add_argument('--strategy',default='taxonomy-order',choices=('taxonomy-order','reverse-taxonomy-test'))
    commands = parser.add_subparsers(dest='command',required=True)
    command = commands.add_parser('prepare')
    command.add_argument('--request-id',required=True)
    command.add_argument('--assessment-id',required=True)
    command.add_argument('--budget-pence',type=int,required=True)
    command.add_argument('--unit-cost-pence',type=int,required=True,help='Synthetic estimate, not a sender price')
    command.add_argument('--max-candidates',type=int,required=True)
    command.add_argument('--seed',type=int,required=True)
    commands.add_parser('inspect').add_argument('--request-id',required=True)
    args = parser.parse_args()
    try:
        service = build_audience_decisions(args.db,args.organization,args.profile,args.strategy,read_only=args.command=='inspect')
        if args.command=='inspect':
            result = service.inspect(args.organization,args.request_id)
        else:
            result = service.prepare(args.organization,args.request_id,args.assessment_id,
                budget_pence=args.budget_pence,unit_cost_pence=args.unit_cost_pence,
                max_candidates=args.max_candidates,seed=args.seed)
    except (ValueError,NotFound) as error:
        parser.exit(2,f'{type(error).__name__}: {error}\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
