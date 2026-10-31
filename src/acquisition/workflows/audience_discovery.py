"""Installed read-only audience capabilities, separate from brief submission."""
from acquisition.reasoning import tool_contract
from acquisition.contracts import digest


def audience_tool_contracts():
    def wire(name, description, properties, required):
        return {'type':'function','function':{'name':name,'description':description,
                'parameters':{'type':'object','properties':properties,'required':required,'additionalProperties':False}}}
    identity={'type':'string','minLength':1,'maxLength':100,'pattern':'^[A-Za-z0-9_.-]+$'}
    listing=wire('list_audience_datasets','List synthetic campaign-linked dataset versions. Ambiguous matches require an explicit selection.',
                 {'campaign_key':identity},[])
    read=wire('read_audience_dataset','Read an exact scoped synthetic dataset version. Grants no campaign or sending authority.',
              {'dataset_id':identity,'version':identity,'checksum':{'type':'string','pattern':'^[a-f0-9]{64}$'},
               'manifest_id':{'type':'string','pattern':'^dataset_[a-f0-9]{64}$'}},['dataset_id','version','checksum','manifest_id'])
    contracts=[tool_contract(listing,'v1','read_context',['server_resolved_source_scope'],['bounded_catalogue_candidates']),
               tool_contract(read,'v1','read_context',['explicit_manifest_version_and_checksum','complete_fresh_source'],['verified_snapshot_summary'])]
    for contract in contracts:
        del contract['hash']
        contract.update(scope='server_resolved_source_organization',
                        replay='read_only_no_effect_receipt; exact_version_checksum_and_manifest_on_read',
                        limits='100_catalogue_entries; 4MB_per_dataset; 10000_records',
                        failure='missing_changed_stale_incomplete_or_invalid_source_rejected')
        contract['hash']=digest(contract)
    return contracts
