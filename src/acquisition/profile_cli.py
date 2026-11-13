"""Prepare source-grounded synthetic profile proposals. No approval or execution."""

import argparse
import json
from pathlib import Path

from acquisition.bootstrap import build_profile_preparation
from acquisition.contracts import Conflict, NotFound


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--organization', required=True, help='Trusted local scope, not hosted authentication')
    parser.add_argument('--profile', required=True, choices=('iwoca', 'fielddesk'))
    parser.add_argument('--version', required=True)
    parser.add_argument('--request-id', required=True)
    parser.add_argument('--objective', required=True)
    parser.add_argument('--budget-pence', type=int, required=True)
    parser.add_argument('--segments', nargs='+', required=True)
    parser.add_argument('--country', required=True)
    parser.add_argument('--currency', required=True)
    parser.add_argument('--channel', required=True)
    parser.add_argument('--size', type=int, default=100)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    try:
        service = build_profile_preparation(args.db, args.organization, args.profile)
        result = service.prepare(args.organization, args.request_id, args.profile, args.version,
            objective=args.objective, budget_pence=args.budget_pence, segments=tuple(args.segments),
            country=args.country, currency=args.currency, channel=args.channel, size=args.size, seed=args.seed)
    except (ValueError, Conflict, NotFound) as error:
        parser.exit(2, f'{type(error).__name__}: {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
