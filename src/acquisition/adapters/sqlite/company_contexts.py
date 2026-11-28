"""Versioned conversation creation policy; never rewrites saved request payloads."""
from acquisition.conversations import COMPANY_CONTEXT_CONTRACT, LEGACY_COMPANY_CONTRACT, require_company_source


GUARDS = """
CREATE TRIGGER IF NOT EXISTS conversation_company_contract_immutable
BEFORE UPDATE OF product_contract ON conversations
WHEN NEW.product_contract IS NOT OLD.product_contract
BEGIN SELECT RAISE(ABORT,'Conversation company contract is immutable'); END;
CREATE TRIGGER IF NOT EXISTS conversation_company_contract_no_replace
BEFORE INSERT ON conversations
WHEN EXISTS(SELECT 1 FROM conversations
 WHERE organization=NEW.organization AND id=NEW.id
 AND product_contract IS NOT NEW.product_contract)
BEGIN SELECT RAISE(ABORT,'Conversation company contract cannot be replaced'); END;
"""


def company_context_migration(db):
    columns = {row[1] for row in db.execute('PRAGMA table_info(conversations)')}
    alter = '' if 'product_contract' in columns else (
        "ALTER TABLE conversations ADD COLUMN product_contract TEXT NOT NULL "
        "DEFAULT 'legacy-fixed-product/v1' "
        "CHECK(product_contract IN ('legacy-fixed-product/v1','company-context/v2'));"
    )
    return alter + GUARDS + 'PRAGMA user_version=28;'


def validate_company_context_schema(db):
    db.execute('SELECT product_contract FROM conversations LIMIT 0')
    if db.execute("SELECT 1 FROM conversations WHERE product_contract IS NULL OR "
                  "product_contract NOT IN (?,?) LIMIT 1",
                  (LEGACY_COMPANY_CONTRACT, COMPANY_CONTEXT_CONTRACT)).fetchone():
        raise ValueError('Invalid saved company-context contract')
    for name in ('conversation_company_contract_immutable', 'conversation_company_contract_no_replace'):
        if not db.execute("SELECT 1 FROM sqlite_schema WHERE type='trigger' AND name=?", (name,)).fetchone():
            raise ValueError('Conversation company-context guard is unavailable')


def require_planning_company_source(db, organization, conversation_id, revision):
    from .conversations import scoped_conversation
    from .intake_planning import planning_source
    row = dict(scoped_conversation(db, organization, conversation_id))
    require_company_source(row.get('product_contract', LEGACY_COMPANY_CONTRACT),
                           planning_source(db, organization, conversation_id, revision))
