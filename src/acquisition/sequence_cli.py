"""Prepare, review and simulate exact synthetic email/call strategies. No real sending."""

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
    start.add_argument('--approval-id',required=True)
    for name in ('advance','inspect','stop','observe'):
        command=commands.add_parser(name);command.add_argument('--simulation-id',required=True)
        if name in {'stop','observe'}: command.add_argument('--request-id',required=True)
        if name=='advance': command.add_argument('--max-steps',type=int,default=18)
        if name=='observe':
            command.add_argument('--step-id',required=True); command.add_argument('--provider-effect-id',required=True)
            command.add_argument('--kind',required=True,choices=('delivered','bounced','replied','objected','task_completed'))
            command.add_argument('--occurred-at',required=True,type=float)
    preview=commands.add_parser('review-preview');preview.add_argument('--proposal-id',required=True)
    opened=commands.add_parser('review-open')
    for flag in ('request-id','proposal-id','actor'):opened.add_argument('--'+flag,required=True)
    shown=commands.add_parser('review-show');shown.add_argument('--subject-id',required=True)
    decided=commands.add_parser('review-decide')
    for flag in ('request-id','subject-id','actor','reason'):decided.add_argument('--'+flag,required=True)
    decided.add_argument('--decision',required=True,choices=('approve','reject'))
    decided.add_argument('--ttl-seconds',type=int,default=86400)
    revoked=commands.add_parser('review-revoke')
    for flag in ('request-id','approval-id','actor','reason'):revoked.add_argument('--'+flag,required=True)
    output=commands.add_parser('validate-output');output.add_argument('--subject-id',required=True)
    output.add_argument('--input',type=Path,required=True)
    args=parser.parse_args()
    try:
        app=build_sequence_simulation(args.db,args.organization,args.profile,email_scenario=args.email_scenario,
            call_scenario=args.call_scenario,read_only=args.command in {'inspect','inspect-proposal','review-preview','review-show','validate-output'})
        if args.command=='propose':
            fields=SequenceRequest.__dataclass_fields__
            request=SequenceRequest(**{name:getattr(args,name if name!='profile_key' else 'profile') for name in fields})
            value=app.campaigns.prepare(args.organization,args.request_id,request)
        elif args.command=='inspect-proposal': value=app.campaigns.inspect(args.organization,args.proposal_id)
        elif args.command=='start': value=app.engagements.start(args.organization,args.request_id,args.proposal_id,args.approval_id)
        elif args.command=='review-preview':value=app.reviews.preview(args.organization,args.proposal_id)
        elif args.command=='review-open':value=app.reviews.open(args.organization,args.request_id,args.proposal_id,args.actor)
        elif args.command=='review-show':value=app.reviews.view(args.organization,args.subject_id)
        elif args.command=='review-decide':value=app.reviews.decide(args.organization,args.request_id,args.subject_id,args.actor,args.decision,args.reason,args.ttl_seconds)
        elif args.command=='review-revoke':value=app.reviews.revoke(args.organization,args.request_id,args.approval_id,args.actor,args.reason)
        elif args.command=='validate-output':value=app.reviews.validate_output(args.organization,args.subject_id,json.loads(args.input.read_text()))
        elif args.command=='advance': value=app.engagements.advance(args.organization,args.simulation_id,max_steps=args.max_steps)
        elif args.command=='inspect': value=app.engagements.inspect(args.organization,args.simulation_id)
        elif args.command=='stop': value=app.engagements.stop(args.organization,args.request_id,args.simulation_id)
        else: value=app.engagements.observe(args.organization,args.request_id,args.simulation_id,args.step_id,args.provider_effect_id,args.kind,args.occurred_at)
    except (ValueError,NotFound,LeaseLost) as error: parser.exit(2,f'{type(error).__name__}: {error}\n')
    print(json.dumps(value,indent=2))


if __name__=='__main__': main()
