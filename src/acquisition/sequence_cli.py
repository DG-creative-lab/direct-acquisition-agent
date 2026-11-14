"""Prepare and simulate exact synthetic email/call strategies. No real sending or approval."""

import argparse
import json
from pathlib import Path

from acquisition.bootstrap import build_sequence_simulation
from acquisition.campaigns import SequenceRequest
from acquisition.contracts import NotFound
from acquisition.runtime import LeaseLost


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',required=True,type=Path)
    parser.add_argument('--organization',required=True,help='Trusted local scope, not hosted authentication')
    parser.add_argument('--profile',required=True,choices=('iwoca','fielddesk'))
    parser.add_argument('--email-scenario',default='success',choices=('success','rejection','partial','timeout'))
    parser.add_argument('--call-scenario',default='success',choices=('success','rejection','partial','timeout'))
    commands=parser.add_subparsers(dest='command',required=True)
    prepare=commands.add_parser('propose')
    for flag in ('request-id','decision-request','initial-content','call-content','followup-content'):
        prepare.add_argument('--'+flag,required=True)
    for flag in ('starts-at','expires-at'): prepare.add_argument('--'+flag,required=True,type=float)
    for flag in ('budget-pence','call-capacity','step-capacity'): prepare.add_argument('--'+flag,required=True,type=int)
    for flag,default in (('email-cost-pence',2),('call-cost-pence',100),('call-delay-seconds',86400),
        ('followup-delay-seconds',259200),('arm-b-call-delay-seconds',172800),('arm-b-followup-delay-seconds',345600)):
        prepare.add_argument('--'+flag,type=int,default=default)
    prepare.add_argument('--stop-scope',choices=('contact','account'),default='account')
    commands.add_parser('inspect-proposal').add_argument('--proposal-id',required=True)
    start=commands.add_parser('start'); start.add_argument('--request-id',required=True);start.add_argument('--proposal-id',required=True)
    for name in ('advance','inspect','stop','observe'):
        command=commands.add_parser(name);command.add_argument('--simulation-id',required=True)
        if name in {'stop','observe'}: command.add_argument('--request-id',required=True)
        if name=='advance': command.add_argument('--max-steps',type=int,default=18)
        if name=='observe':
            command.add_argument('--step-id',required=True); command.add_argument('--provider-effect-id',required=True)
            command.add_argument('--kind',required=True,choices=('delivered','bounced','replied','objected','task_completed'))
            command.add_argument('--occurred-at',required=True,type=float)
    args=parser.parse_args()
    try:
        app=build_sequence_simulation(args.db,args.organization,args.profile,email_scenario=args.email_scenario,
            call_scenario=args.call_scenario,read_only=args.command in {'inspect','inspect-proposal'})
        if args.command=='propose':
            fields=SequenceRequest.__dataclass_fields__
            request=SequenceRequest(**{name:getattr(args,name if name!='profile_key' else 'profile') for name in fields})
            value=app.campaigns.prepare(args.organization,args.request_id,request)
        elif args.command=='inspect-proposal': value=app.campaigns.inspect(args.organization,args.proposal_id)
        elif args.command=='start': value=app.engagements.start(args.organization,args.request_id,args.proposal_id)
        elif args.command=='advance': value=app.engagements.advance(args.organization,args.simulation_id,max_steps=args.max_steps)
        elif args.command=='inspect': value=app.engagements.inspect(args.organization,args.simulation_id)
        elif args.command=='stop': value=app.engagements.stop(args.organization,args.request_id,args.simulation_id)
        else: value=app.engagements.observe(args.organization,args.request_id,args.simulation_id,args.step_id,args.provider_effect_id,args.kind,args.occurred_at)
    except (ValueError,NotFound,LeaseLost) as error: parser.exit(2,f'{type(error).__name__}: {error}\n')
    print(json.dumps(value,indent=2))


if __name__=='__main__': main()
