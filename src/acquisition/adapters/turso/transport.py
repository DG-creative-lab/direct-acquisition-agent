"""Bounded Hrana HTTP transport. Never retries a submitted statement."""
import base64
import json
import math
import sqlite3
import urllib.request
from urllib.parse import urlsplit


class RemoteUnavailable(RuntimeError):
    """Provider outcome could not be established. Resume the original command."""


class CommitUncertain(RemoteUnavailable):
    """Commit acknowledgement was lost; reconcile the original receipt."""


class Busy(RemoteUnavailable):
    """The provider positively rejected lock acquisition."""


def endpoint(url):
    parsed = urlsplit(url)
    if (parsed.scheme not in {'https', 'libsql'} or not parsed.hostname or
            not parsed.hostname.endswith('.turso.io') or parsed.username or parsed.password or
            parsed.port or parsed.path not in {'', '/'} or parsed.query or parsed.fragment):
        raise ValueError('Use an explicit Turso database URL without credentials or path')
    return 'https://' + parsed.hostname + '/v3/pipeline'


class Http:
    def __init__(self, url, token, timeout=10):
        self.url = endpoint(url)
        if not token or '\n' in token or '\r' in token:
            raise ValueError('A server-side database token is required')
        self._token, self.timeout = token, timeout
        # A redirect must never forward the bearer credential to another host.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        self.opener = urllib.request.build_opener(NoRedirect())

    def __call__(self, payload):
        request = urllib.request.Request(self.url, json.dumps(payload).encode(),
            {'Authorization': 'Bearer ' + self._token, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return json.load(response)
        except Exception:
            raise RemoteUnavailable('Remote storage acknowledgement unavailable') from None


def encode(value):
    if value is None:return {'type': 'null'}
    if isinstance(value, int):
        if not -(2**63) <= value < 2**63:raise OverflowError('SQLite integer out of range')
        return {'type': 'integer', 'value': str(int(value))}
    if isinstance(value, float) and math.isfinite(value):return {'type': 'float', 'value': value}
    if isinstance(value, str):return {'type': 'text', 'value': value}
    if isinstance(value, bytes):return {'type': 'blob', 'base64': base64.b64encode(value).decode()}
    raise ValueError('Unsupported SQL binding value')


def decode(value):
    kind = value['type']
    if kind == 'null':return None
    if kind == 'integer':return int(value['value'])
    if kind == 'float':return float(value['value'])
    if kind == 'text':return value['value']
    if kind == 'blob':return base64.b64decode(value['base64'] + '=' * (-len(value['base64']) % 4), validate=True)
    raise ValueError('Unsupported remote SQL value')


class Row:
    def __init__(self, names, values):self.names, self.values = names, tuple(values)
    def keys(self):return self.names
    def __getitem__(self, key):return self.values[self.names.index(key)] if isinstance(key, str) else self.values[key]
    def __iter__(self):return iter(self.values)
    def __len__(self):return len(self.values)


class Cursor:
    def __init__(self, result):
        names = [c['name'] for c in result['cols']]
        self.rows = iter([Row(names, [decode(v) for v in row]) for row in result['rows']])
        self.rowcount = result['affected_row_count']
        rowid = result.get('last_insert_rowid')
        self.lastrowid = int(rowid) if rowid is not None else None
    def fetchone(self):return next(self.rows, None)
    def fetchall(self):return list(self.rows)
    def __iter__(self):return self.rows


class Connection:
    def __init__(self, send):self.send, self.baton, self.failed, self.in_transaction = send, None, False, False

    def pipeline(self, statements):
        if self.failed:raise RemoteUnavailable('Remote connection requires reconciliation')
        requests = []
        for sql, parameters in statements:
            stmt = {'sql': sql}
            if isinstance(parameters, dict):
                stmt['named_args'] = [{'name': k, 'value': encode(v)} for k, v in parameters.items()]
            else:stmt['args'] = [encode(v) for v in parameters]
            conditions = []
            if self.in_transaction:
                conditions.append({'type':'not','cond':{'type':'is_autocommit'}})
            if requests:
                conditions.append({'type':'ok','step':len(requests)-1})
            step = {'stmt':stmt}
            if conditions:step['condition'] = {'type':'and','conds':conditions}
            requests.append(step)
        try:
            result = self.send({'baton': self.baton, 'requests': [{'type':'batch','batch':{'steps':requests}}]})
            self.baton = result['baton']
            if len(result['results']) != 1:raise ValueError('Missing batch result')
            item = result['results'][0]
            if item['type'] == 'error':raise RemoteUnavailable('Remote batch rejected')
            batch = item['response']['result']
            if len(batch['step_results']) != len(requests) or len(batch['step_errors']) != len(requests):
                raise ValueError('Missing statement results')
            cursors = []
            for step, error in zip(batch['step_results'],batch['step_errors']):
                if error is not None:
                    code = error.get('code', '')
                    if code.startswith('SQLITE_CONSTRAINT'):
                        raise sqlite3.IntegrityError('Remote storage constraint rejected the operation')
                    if code in {'SQLITE_BUSY', 'SQLITE_LOCKED'}:raise Busy('Remote writer is busy')
                    raise RemoteUnavailable('Remote statement rejected')
                if step is None:raise RemoteUnavailable('Remote transaction is no longer active')
                cursors.append(Cursor(step))
            for sql, _ in statements:
                verb = sql.strip().split(None,1)[0].upper()
                if verb == 'BEGIN':self.in_transaction = True
                elif verb in {'COMMIT','ROLLBACK'}:self.in_transaction = False
            return cursors
        except (sqlite3.IntegrityError, Busy):raise
        except Exception:
            self.failed = True
            raise RemoteUnavailable('Remote storage outcome requires reconciliation') from None

    def execute(self, sql, parameters=()):return self.pipeline([(sql, parameters)])[0]
    def executemany(self, sql, parameters):
        cursors = self.pipeline([(sql, values) for values in parameters])
        return cursors[-1] if cursors else None

    def commit(self):
        if not self.in_transaction:return
        try:self.execute('COMMIT')
        except RemoteUnavailable:
            raise CommitUncertain('Reconcile the original command before further writes') from None
    def rollback(self):
        if not self.failed and self.in_transaction:self.execute('ROLLBACK')
    def close(self):
        if self.baton is not None:
            try:self.send({'baton': self.baton, 'requests': [{'type': 'close'}]})
            except Exception:pass
            self.baton = None
