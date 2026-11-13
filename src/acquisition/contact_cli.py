"""Inspect and prepare synthetic contact evidence. No sending or campaign authority."""

import argparse
import json
from pathlib import Path

from acquisition.bootstrap import build_contact_directory
from acquisition.contracts import Conflict, NotFound


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',required=True,type=Path)
    parser.add_argument('--organization',required=True,help='Trusted local scope, not hosted authentication')
    parser.add_argument('--profile',required=True,choices=('iwoca','fielddesk'))
    commands = parser.add_subparsers(dest='command',required=True)
    for action in ('prepare','refresh'):
        command = commands.add_parser(action)
        command.add_argument('--request-id',required=True)
        command.add_argument('--connection',required=True)
        command.add_argument('--version',type=int,required=True)
        if action == 'prepare':
            command.add_argument('--channel',required=True,choices=('email','human_call','direct_mail'))
            command.add_argument('--purpose',default='acquisition')
    command = commands.add_parser('object')
    command.add_argument('--request-id',required=True)
    command.add_argument('--contact-id',required=True)
    command.add_argument('--channel',required=True)
    command.add_argument('--purpose',required=True)
    command.add_argument('--reason',required=True)
    commands.add_parser('inspect').add_argument('--assessment-id',required=True)
    args = parser.parse_args()
    try:
        directory = build_contact_directory(args.db,args.organization,args.profile,read_only=args.command=='inspect')
        if args.command == 'prepare':
            result = directory.prepare(args.organization,args.request_id,args.connection,args.version,args.channel,args.purpose)
        elif args.command == 'refresh':
            result = directory.refresh(args.organization,args.request_id,args.connection,args.version)
        elif args.command == 'object':
            result = directory.object(args.organization,args.request_id,args.contact_id,args.channel,args.purpose,args.reason)
        else:
            result = directory.inspect(args.organization,args.assessment_id)
    except (ValueError,NotFound) as error:
        parser.exit(2,f'{type(error).__name__}: {error}\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
