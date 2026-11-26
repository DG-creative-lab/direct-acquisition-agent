"""Atomic offline intake proposals, using existing native artifact tables."""

from dataclasses import asdict

from acquisition.campaigns import evaluate_preparation_eligibility, grounding_request_from
from acquisition.contracts import Conflict, NotFound, canonical, digest

from .admission_guard import verified_required
from .audiences import write_snapshot, read_snapshot
from .creative import read_context
from .drafts import read_draft
from .preparation_context import SqlitePreparationContexts


PREFIX = 'intake-preparation:'
CONTEXT_PREFIX = 'intake-preparation-context:'


class SqliteIntakePreparation:
    def __init__(self, database, build, clock, *, read_only=False):
        self.database, self.build, self.read_only = database, build, read_only
        self.clock = clock

    @staticmethod
    def _row(db, organization, request_id):
        row = db.execute('SELECT * FROM preparation_contexts WHERE organization=? AND request_id=?',
                         (organization, request_id)).fetchone()
        if row is None:
            raise NotFound('Reviewed input context not found in this organization')
        return row

    @classmethod
    def _preview(cls, db, organization, context_request_id, now, *, historical=False):
        row = cls._row(db, organization, context_request_id)
        view = SqlitePreparationContexts._view(db, row, now)
        if historical:
            # Reconstruct the original publication, not a fresh authorization.
            c = view['context']
            view['review_required'] = ([] if c['reviewed_at'] <= now < c['review_expires_at']
                                       else ['The preparation input review is expired or future-dated.'])
        return evaluate_preparation_eligibility(view, now) | {'context': view['context']}

    def preview(self, organization, context_request_id, now):
        with self.database.connect() as db:
            result = self._preview(db, organization, context_request_id, now)
            original = db.execute('SELECT draft_id FROM draft_operations WHERE organization=? AND operation_id=?',
                                  (organization, CONTEXT_PREFIX + result['context_fingerprint'])).fetchone()
            if original is not None:
                draft = read_draft(db, organization, original[0])
                result['original_preparation_request_id'] = draft.manifest['brief']['plan']['request_id']
            if self.read_only or self.database.inspection_only or verified_required(db):
                result['blockers'].append('This store permits inspection only for this preparation format. Execution remains paused.')
            return result

    def _original(self, db, organization, request_id):
        row = db.execute('SELECT draft_id FROM draft_operations WHERE organization=? AND operation_id=?',
                         (organization, PREFIX + request_id)).fetchone()
        return read_draft(db, organization, row[0]) if row else None

    def _validate(self, db, organization, request_id, draft):
        try:
            plan = draft.manifest['brief']['plan']
            binding = plan['intake_grounding']
            request = grounding_request_from(binding['request'])
            preview = self._preview(db, organization, request.context_request_id, binding['prepared_at'], historical=True)
            snapshot, bundles, expected = self.build(organization, binding['actor'], request_id, request,
                                                     preview, binding['prepared_at'])
            if draft != expected or plan['request_id'] != request_id:
                raise Conflict('Intake proposal differs from its original source, review or recipe')
            if read_snapshot(db, organization, snapshot.id) != snapshot:
                raise Conflict('Intake proposal audience differs from its exact synthetic recipe')
            for context, pair in bundles:
                identity = 'context_' + digest({'organization': organization, **context})
                if canonical(read_context(db, organization, identity)) != canonical(context):
                    raise Conflict('Intake proposal context differs from its selected grounded material')
                row = db.execute('SELECT payload FROM generated_catalogues WHERE organization=? AND operation_id=?',
                    (organization, context['plan_id'] + ':' + context['segment'])).fetchone()
                if row is None or row[0] != canonical([asdict(v) for v in pair]):
                    raise Conflict('Intake proposal catalogue differs from its frozen recipe')
            slot = db.execute('SELECT draft_id FROM draft_operations WHERE organization=? AND operation_id=?',
                (organization, CONTEXT_PREFIX + preview['context_fingerprint'])).fetchone()
            if slot is None or slot[0] != draft.id:
                raise Conflict('Intake proposal lost its original context binding')
            return binding
        except (KeyError, TypeError, ValueError) as error:
            raise Conflict('Intake preparation integrity failed') from error

    def _result(self, db, organization, request_id, draft, now, replayed):
        binding = self._validate(db, organization, request_id, draft)
        current = self._preview(db, organization, binding['context_request_id'], now)
        reasons = list(current['blockers'])
        if not binding['prepared_at'] <= now < binding['review_expires_at']:
            reasons.append('The source evidence review is expired or future-dated.')
        return {'request_id': request_id, 'store_id': binding['store_id'], 'draft_id': draft.id,
            'manifest': draft.manifest, 'grounding': binding, 'current': not reasons,
            'product_evidence': read_context(db, organization, draft.manifest['creatives'][0]['context_id'])['product_facts'],
            'review_required': reasons, 'replayed': replayed, 'approval': 'not_granted',
            'execution': 'not_performed', 'model_calls': 0, 'semantic_screen': 'not_evaluated',
            'observation': 'historical_proposal' if replayed else 'prepared_proposal'}

    def request(self, organization, request_id, now):
        with self.database.connect() as db:
            draft = self._original(db, organization, request_id)
            if draft is None:
                raise NotFound('Preparation request not found in this organization')
            return self._result(db, organization, request_id, draft, now, True)

    def not_committed(self, organization, request_id):
        if self.read_only or self.database.inspection_only:
            return False
        with self.database.connect() as db:
            return self._original(db, organization, request_id) is None

    def publish(self, organization, actor, request_id, request, preview, bundle, now):
        if self.read_only:
            raise Conflict('This preparation store is open for inspection only')
        with self.database.transaction() as db:
            now = self.clock()
            if verified_required(db):
                raise Conflict('Intake fixture preparation has no verified execution capability; execution stays paused')
            old = self._original(db, organization, request_id)
            if old is not None:
                result = self._result(db, organization, request_id, old, now, True)
                if (canonical(result['grounding']['request']) != canonical(asdict(request))
                        or result['grounding']['actor'] != actor):
                    raise Conflict('Preparation request already binds different exact inputs')
                return result
            fresh = self._preview(db, organization, request.context_request_id, now)
            if fresh['id'] != preview['id'] or fresh['blockers']:
                raise Conflict('Preparation sources or eligibility changed before publication')
            # Rebuild through the injected composition inside the writer lock.
            # This validates sources and freshness at the actual commit boundary.
            expected = self.build(organization, actor, request_id, request, fresh,
                                  bundle[2].manifest['brief']['plan']['intake_grounding']['prepared_at'])
            if canonical(asdict(expected[0])) != canonical(asdict(bundle[0])) or expected[1:] != bundle[1:]:
                raise Conflict('Candidate differs from the exact reviewed preparation')
            snapshot, bundles, draft = bundle
            slot_id = CONTEXT_PREFIX + preview['context_fingerprint']
            if db.execute('SELECT 1 FROM draft_operations WHERE organization=? AND operation_id=?',
                          (organization, slot_id)).fetchone():
                raise Conflict('This input review already has an original preparation request. Reconcile it before preparing again.')
            write_snapshot(db, snapshot)
            for context, pair in bundles:
                identity = 'context_' + digest({'organization': organization, **context})
                db.execute('INSERT OR IGNORE INTO creative_contexts VALUES(?,?,?)', (organization, identity, canonical(context)))
                db.execute('INSERT OR IGNORE INTO generated_catalogues VALUES(?,?,?)',
                           (organization, context['plan_id'] + ':' + context['segment'], canonical([asdict(v) for v in pair])))
            db.execute('INSERT OR IGNORE INTO drafts VALUES(?,?,?,?,?)',
                       (organization, draft.id, canonical(draft.manifest), draft.mailing_csv, draft.assignments_csv))
            for operation in (PREFIX + request_id, slot_id):
                db.execute('INSERT INTO draft_operations VALUES(?,?,?)', (organization, operation, draft.id))
            result = self._result(db, organization, request_id, read_draft(db, organization, draft.id), self.clock(), False)
            if not result['current']:
                raise Conflict('Preparation source review is no longer current at publication')
            return result
