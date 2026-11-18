"""Prepare synthetic grounded email/call content through bounded offline inference. No sending."""

import argparse
import json
from pathlib import Path

from acquisition.bootstrap import build_channel_preparation
from acquisition.contracts import Conflict, NotFound


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',required=True,type=Path)
    parser.add_argument('--organization',required=True,help='Trusted local scope, not hosted authentication')
    parser.add_argument('--profile',required=True,choices=('iwoca','fielddesk'))
    sub = parser.add_subparsers(dest='command',required=True)
    for name in ('prepare','start'):
        command = sub.add_parser(name)
        command.add_argument('--request-id',required=True)
        command.add_argument('--recipient-requests',required=True,nargs='+')
        command.add_argument('--channel',required=True,choices=('email','human_call'))
        command.add_argument('--style',default='explore',choices=('explore','practical'))
        command.add_argument('--parent-id')
    for name in ('inspect','work','cancel'):
        sub.add_parser(name).add_argument('--request-id',required=True)
    sub.add_parser('ownership',help='Inspect a scoped channel run and its historical ownership').add_argument('--run',required=True)
    reconcile = sub.add_parser('reconcile-ownership',help='Record proven legacy ownership against an exact scoped inspection')
    reconcile.add_argument('--run',required=True)
    reconcile.add_argument('--fingerprint',required=True)
    args = parser.parse_args()
    try:
        app = build_channel_preparation(args.db,args.organization,args.profile,read_only=args.command in {'inspect','ownership'})
        if args.command in ('prepare','start'):
            result = getattr(app,args.command)(args.organization,args.request_id,args.profile,args.recipient_requests,
                args.channel,style=args.style,parent_id=args.parent_id)
            if args.command=='start': result = {'run_id':result,'authority':'none'}
        elif args.command=='ownership':
            result = app.ownership(args.organization,args.run)
        elif args.command=='reconcile-ownership':
            result = app.reconcile_ownership(args.organization,args.run,args.fingerprint)
        else:
            view = app.inspect(args.organization,args.request_id)
            if args.command=='work': app.worker.drain(args.organization,run_id=view['run_id'])
            elif args.command=='cancel': app.tasks.cancel(args.organization,view['run_id'],app.store._now())
            result = app.inspect(args.organization,args.request_id)
    except (ValueError,Conflict,NotFound) as error:
        parser.exit(2,f'{type(error).__name__}: {error}\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
