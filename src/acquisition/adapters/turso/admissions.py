"""Reconcile an uncertain admission acknowledgement against original authority."""
from acquisition.adapters.sqlite.admissions import SqliteAdmissions
from acquisition.contracts import Conflict
from .transport import CommitUncertain


class TursoAdmissions(SqliteAdmissions):
    def admit(self, intent, now):
        try:return super().admit(intent, now)
        except CommitUncertain:
            # find_request verifies the persisted request, plan, owner and receipt.
            receipt = self.find_request(intent.organization, intent.request_id)
            if receipt is None:raise
            if receipt.fingerprint != intent.fingerprint:
                raise Conflict('Admission request already binds different inputs')
            return receipt
