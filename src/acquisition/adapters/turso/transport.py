"""Bounded Hrana HTTP transport. Never retries a submitted statement."""
import base64
import json
import math
import re
import sqlite3
import time
from http.client import HTTPConnection, HTTPSConnection
from threading import Lock
from urllib.parse import urlsplit


class RemoteUnavailable(RuntimeError):
    """Provider outcome could not be established. Resume the original command."""

    def __init__(self, message, *, reason='unclassified', http_status=None):
        super().__init__(message)
        # Only adapter-owned categories and numeric status, never provider text,
        # SQL, parameters, credentials or response bodies.
        self.reason, self.http_status = reason, http_status


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
    def __init__(self, url, token, timeout=10, *, deadline=None):
        self.url = endpoint(url)
        if not token or '\n' in token or '\r' in token:
            raise ValueError('A server-side database token is required')
        self._token, self.timeout, self.deadline = token, timeout, deadline
        self._connection = None
        self._last_response = None
        self._lock = Lock()

    def close(self):
        self._last_response = None
        connection = getattr(self, '_connection', None)
        if connection is not None:
            connection.close()
            self._connection = None

    def __del__(self):self.close()

    def __call__(self, payload):
        # Serialize socket use, not database transactions. Independent Hrana
        # streams still require provider-side concurrency and commit authority.
        with self._lock:
            remaining = self.timeout if self.deadline is None else min(self.timeout,self.deadline-time.monotonic())
            if remaining <= 0:
                raise RemoteUnavailable('Invocation storage budget exhausted',reason='invocation_budget_exhausted')
            # Retire idle physical sockets before submission. Hrana's logical
            # transaction and baton are independent of this HTTP connection.
            if self._last_response is not None and time.monotonic()-self._last_response>=1:
                self.close()
            target = urlsplit(self.url)
            try:
                if self._connection is None:
                    connection_type = HTTPSConnection if target.scheme == 'https' else HTTPConnection
                    self._connection = connection_type(target.hostname,target.port,timeout=remaining)
                connection = self._connection
                connection.timeout = remaining
                if connection.sock is not None:connection.sock.settimeout(remaining)
                connection.request('POST',target.path,body=json.dumps(payload).encode(),headers={
                    'Authorization':'Bearer '+self._token,'Content-Type':'application/json'})
                response = connection.getresponse()
                raw = response.read()
                # Never follow a redirect or forward credentials to another host.
                if response.status != 200:
                    raise RemoteUnavailable('Remote HTTP response rejected',reason='http_response_rejected',http_status=response.status)
                result = json.loads(raw)
                self._last_response = time.monotonic()
                return result
            except RemoteUnavailable:
                self.close();raise
            except Exception as error:
                self.close()
                # No reconnect-and-repeat, including a lost response on a reused socket.
                reason=('invocation_budget_exhausted' if self.deadline is not None and time.monotonic()>=self.deadline
                        else 'transport_timeout' if isinstance(error,TimeoutError) else 'transport_ack_unavailable')
                raise RemoteUnavailable('Remote storage acknowledgement unavailable',reason=reason) from None



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


# SQLite parameter tokens, with strings, identifiers and comments kept opaque.
# Named slots may repeat; ?NNN and anonymous slots share SQLite's slot numbering.
_BINDING_TOKEN = re.compile(
    r"(?P<opaque>'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\[[^\]]*\]|"
    r"--[^\n]*(?:\n|$)|/\*[\s\S]*?(?:\*/|$))|"
    r"(?P<parameter>\?[0-9]*|[:@$](?:[\w$\u0080-\U0010ffff]|::)+(?:\([^\s)]*\))?)|"
    r"[A-Za-z_\u0080-\U0010ffff][A-Za-z_0-9$\u0080-\U0010ffff]*"
)


def _float_binding(marker, value):
    """Reconstruct an exact binary64 from one exactly representable integer.

    Some providers round JSON float bindings by one ULP. Decimal CAST also
    rounds some finite values. Integer significands and power-of-two scaling
    avoid both conversions, preserving REAL type, subnormals and signed zero.
    """
    if not math.isfinite(value):raise ValueError('Unsupported SQL binding value')
    fraction, exponent = math.frexp(value)
    significand = int(fraction * (1 << 53)); exponent -= 53
    if significand:
        while significand % 2 == 0:significand //= 2;exponent += 1
    else:exponent = 0
    expression = 'CAST('+marker+' AS REAL)'
    if value == 0 and math.copysign(1,value)<0:expression += ' * -1.0'
    while exponent:
        bits = min(abs(exponent),52)
        expression += (' * ' if exponent>0 else ' / ')+str(1 << bits)
        exponent += -bits if exponent>0 else bits
    return '('+expression+')', significand


def _exact_parameters(sql, parameters):
    if not any(isinstance(v,float) for v in (parameters.values() if isinstance(parameters,dict) else parameters)):
        return sql, parameters
    largest=0; named={}
    def replace(match):
        nonlocal largest
        marker=match.group('parameter')
        if marker is None:return match[0]
        if marker.startswith('?') and len(marker)>1:
            slot=int(marker[1:]);largest=max(largest,slot)
        elif marker=='?':largest+=1;slot=largest
        else:
            if marker not in named:largest+=1;named[marker]=largest
            slot=named[marker]
        value=(parameters.get(marker[1:]) if isinstance(parameters,dict)
               else parameters[slot-1] if 1<=slot<=len(parameters) else None)
        return _float_binding(marker,value)[0] if isinstance(value,float) else marker
    sql=_BINDING_TOKEN.sub(replace,sql)
    def wire(value):return _float_binding('?',value)[1] if isinstance(value,float) else value
    return sql, ({k:wire(v) for k,v in parameters.items()} if isinstance(parameters,dict) else tuple(wire(v) for v in parameters))


class Row:
    def __init__(self, names, values):self.names, self.values = names, tuple(values)
    def keys(self):return self.names
    def __getitem__(self, key):return self.values[self.names.index(key)] if isinstance(key, str) else self.values[key]
    def __iter__(self):return iter(self.values)
    def __len__(self):return len(self.values)


class Cursor:
    def __init__(self, result):
        self._wire_result = result
        names = [c['name'] for c in result['cols']]
        self.rows = iter([Row(names, [decode(v) for v in row]) for row in result['rows']])
        self.rowcount = result['affected_row_count']
        rowid = result.get('last_insert_rowid')
        self.lastrowid = int(rowid) if rowid is not None else None
    def fetchone(self):return next(self.rows, None)
    def fetchall(self):return list(self.rows)
    def __iter__(self):return self.rows


class Connection:
    def __init__(self, send, *, memoize_transactions=False):
        self.send, self.baton, self.failed, self.in_transaction = send, None, False, False
        self.memoize_transactions = memoize_transactions
        self._memo, self._memo_bytes = {}, 0

    @staticmethod
    def _plain_read(sql):
        # Closed built-in set over unchanged rows. Unknown functions, comments,
        # quoted function names and SQL clocks always execute and clear the memo.
        text=sql.strip().removesuffix(';')
        read = re.match(r'SELECT\b',text,re.I) is not None
        if re.match(r'WITH\b',text,re.I):
            read = (re.search(r'\bSELECT\b',text,re.I) is not None and
                    re.search(r'\b(?:INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER|PRAGMA|ATTACH|DETACH)\b',text,re.I) is None)
        if (not text.isascii() or not read or ';' in text or '--' in text or '/*' in text
                or '"' in text or '`' in text or re.search(r"['\]]\s*\(",text)
                or re.search(r'\bCURRENT_(?:DATE|TIME|TIMESTAMP)\b',text,re.I)):
            return False
        names={name.upper() for name in re.findall(r'\b([a-zA-Z_][a-zA-Z_0-9]*)\s*\(',text)}
        stable={'COUNT','JSON_EXTRACT','JSON_VALID','MIN','MAX','SUM','COALESCE','CAST',
                'IN','EXISTS','AND','OR','NOT','WHERE','ON','FROM','AS','SELECT'}
        return names<=stable

    def _clear_memo(self):
        self._memo.clear(); self._memo_bytes=0

    def pipeline(self, statements):
        if self.failed:raise RemoteUnavailable('Remote connection requires reconciliation')
        if any(not self._plain_read(sql) for sql, _ in statements):self._clear_memo()
        requests = []
        for sql, parameters in statements:
            sql,parameters=_exact_parameters(sql,parameters)
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
            if item['type'] == 'error':raise RemoteUnavailable('Remote batch rejected',reason='provider_batch_rejected')
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
                    raise RemoteUnavailable('Remote statement rejected',reason='provider_statement_rejected')
                if step is None:raise RemoteUnavailable('Remote transaction is no longer active',reason='transaction_inactive')
                cursors.append(Cursor(step))
            for sql, _ in statements:
                verb = sql.strip().split(None,1)[0].upper()
                if verb == 'BEGIN':self.in_transaction = True
                elif verb in {'COMMIT','ROLLBACK'}:self.in_transaction = False
            return cursors
        except (sqlite3.IntegrityError, Busy):raise
        except RemoteUnavailable:
            self.failed=True;raise
        except Exception:
            self.failed = True
            raise RemoteUnavailable('Remote storage outcome requires reconciliation',reason='protocol_invalid') from None

    def execute(self, sql, parameters=()):
        if self.failed:raise RemoteUnavailable('Remote connection requires reconciliation')
        parameters=dict(parameters) if isinstance(parameters,dict) else tuple(parameters)
        memoize=self.memoize_transactions and self.in_transaction and self._plain_read(sql)
        key=None
        if memoize:
            bindings=({k:encode(v) for k,v in parameters.items()} if isinstance(parameters,dict)
                      else [encode(v) for v in parameters])
            key=json.dumps([sql,bindings],sort_keys=True)
            if key in self._memo:
                cursor=Cursor(json.loads(self._memo[key]));del cursor._wire_result
                return cursor
        cursor=self.pipeline([(sql,parameters)])[0]
        if memoize:
            payload=json.dumps(cursor._wire_result)
            size=len(key)+len(payload)
            if len(payload)<=1024*1024 and len(key)<=1024*1024:
                if len(self._memo)>=4096 or self._memo_bytes+size>16*1024*1024:self._clear_memo()
                self._memo[key]=payload;self._memo_bytes+=size
        del cursor._wire_result
        return cursor
    def executemany(self, sql, parameters):
        cursors = self.pipeline([(sql, values) for values in parameters])
        return cursors[-1] if cursors else None

    def commit(self):
        if not self.in_transaction:return
        try:self.execute('COMMIT')
        except RemoteUnavailable as error:
            raise CommitUncertain('Reconcile the original command before further writes',
                                  reason=error.reason,http_status=error.http_status) from None
    def rollback(self):
        if not self.failed and self.in_transaction:self.execute('ROLLBACK')
    def close(self):
        self._clear_memo()
        if self.baton is not None:
            try:self.send({'baton': self.baton, 'requests': [{'type': 'close'}]})
            except Exception:pass
            self.baton = None
