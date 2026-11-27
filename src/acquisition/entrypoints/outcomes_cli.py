"""Recorded external outcomes, deliberately separate from synthetic learning commands."""
from pathlib import Path


def add_outcome_commands(commands):
    for name in ('outcomes-register','outcomes-import','outcomes-finalize','outcomes-show','outcomes-show-report','outcomes-receipt'):
        p=commands.add_parser(name,help='Operator-attested external evidence; no sending or provider verification')
        if name not in {'outcomes-show','outcomes-show-report'}:
            p.add_argument('--actor',required=True);p.add_argument('--request-id',required=True)
        if name not in {'outcomes-register','outcomes-receipt'}:p.add_argument('--cohort',required=True)
        if name in {'outcomes-register','outcomes-import'}:p.add_argument('--file',type=Path,required=True)
        if name=='outcomes-show-report':p.add_argument('--report',required=True)
        if name=='outcomes-receipt':p.add_argument('--operation',choices=('register','import','finalize'),required=True)


def outcome_command(app,args):
    org=args.organization
    if args.command=='outcomes-register':return app.register_file(org,args.actor,args.request_id,args.file)
    if args.command=='outcomes-import':return app.ingest_file(org,args.actor,args.request_id,args.cohort,args.file)
    if args.command=='outcomes-finalize':return app.finalize(org,args.actor,args.request_id,args.cohort)
    if args.command=='outcomes-show':return app.view(org,args.cohort)
    if args.command=='outcomes-show-report':return app.snapshot(org,args.cohort,args.report)
    return app.receipt(org,args.actor,args.operation,args.request_id)
