"""Creation policy, separate from frozen legacy planning and approval contracts."""
from acquisition.contracts import Conflict


LEGACY_COMPANY_CONTRACT = 'legacy-fixed-product/v1'
COMPANY_CONTEXT_CONTRACT = 'company-context/v2'
COMPANY_CONTRACTS = (LEGACY_COMPANY_CONTRACT, COMPANY_CONTEXT_CONTRACT)


class CompanyContextRequired(Conflict):
    code = 'company_context_required'


def validate_company_contract(value):
    if type(value) is not str or value not in COMPANY_CONTRACTS:
        raise ValueError('Unsupported company-context contract')
    return value


def require_company_source(contract, selected):
    validate_company_contract(contract)
    if contract == COMPANY_CONTEXT_CONTRACT and selected is None:
        raise CompanyContextRequired(
            'Select a saved Company & brief before planning company-specific work. '
            'The fictional Fielddesk sequence and authored YouTube example are also available.'
        )
