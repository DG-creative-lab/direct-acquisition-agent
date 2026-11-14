"""Retrieve minimal reviewed synthetic recipient context or inspect its immutable provenance."""

import argparse
import json
from pathlib import Path

from acquisition.bootstrap import build_recipient_contexts
from acquisition.contracts import NotFound


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',required=True,type=Path)
    parser.add_argument('--organization',required=True,help='Trusted local scope, not hosted authentication')
    parser.add_argument('--profile',required=True,choices=('iwoca','fielddesk'))
    commands = parser.add_subparsers(dest='command',required=True)
    command = commands.add_parser('prepare')
    command.add_argument('--request-id',required=True)
    command.add_argument('--assessment-id',required=True)
    command.add_argument('--contact-id',required=True)
    command.add_argument('--source',required=True)
    command.add_argument('--source-version',required=True,type=int)
    command.add_argument('--slots',nargs='+',required=True,
        choices=('contact_role','prior_interaction','account_activity','business_signal'))
    command.add_argument('--max-facts',type=int,default=2)
    commands.add_parser('inspect').add_argument('--request-id',required=True)
    command = commands.add_parser('validate')
    command.add_argument('--request-id',required=True)
    command.add_argument('--fact-id',required=True)
    command.add_argument('--statement',required=True)
    command.add_argument('--target-id',required=True)
    args = parser.parse_args()
    try:
        service = build_recipient_contexts(args.db,args.organization,args.profile,read_only=args.command!='prepare')
        if args.command=='prepare':
            result = service.prepare(args.organization,args.request_id,args.assessment_id,args.contact_id,args.source,
                args.source_version,slots=tuple(args.slots),max_facts=args.max_facts)
        elif args.command=='inspect': result = service.inspect(args.organization,args.request_id)
        else:
            result = service.validate(args.organization,args.request_id,({'fact_id':args.fact_id,
                'statement':args.statement,'target_id':args.target_id},))
    except (ValueError,NotFound) as error:
        parser.exit(2,f'{type(error).__name__}: {error}\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
