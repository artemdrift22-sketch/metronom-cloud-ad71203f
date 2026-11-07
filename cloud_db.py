"""Small DB-API adapter for libSQL embedded replicas. No silent local fallback."""
import os
import tempfile

class Row:
    def __init__(self, names, values): self.names, self.values = names, values
    def keys(self): return self.names
    def __getitem__(self, key): return self.values[self.names.index(key)] if isinstance(key, str) else self.values[key]

class Cursor:
    def __init__(self, cur):
        self.rowcount, self.lastrowid = cur.rowcount, cur.lastrowid
        self.names = [i[0] for i in (cur.description or [])]
        self.rows = [Row(self.names, r) for r in cur.fetchall()] if self.names else []
        self.pos = 0
    def fetchone(self):
        if self.pos >= len(self.rows): return None
        row = self.rows[self.pos]; self.pos += 1; return row
    def fetchall(self):
        rows = self.rows[self.pos:]; self.pos = len(self.rows); return rows
    def __iter__(self): return iter(self.fetchall())

class Connection:
    def __init__(self, raw): self.raw = raw
    def execute(self, sql, args=()): return Cursor(self.raw.execute(sql, tuple(args)))
    def executescript(self, sql): return self.raw.executescript(sql)
    def commit(self): return self.raw.commit()
    def close(self): return self.raw.close()

def open_remote(prefix):
    url, token = os.environ.get(prefix + '_DB_URL'), os.environ.get(prefix + '_DB_TOKEN')
    if not url or not token: raise RuntimeError(prefix + ' DB URL/token must both be set')
    if not url.startswith('libsql://'): raise RuntimeError('Expected libsql:// database URL')
    import libsql
    # The replica is expendable: the remote primary is authoritative.
    path = os.path.join(tempfile.gettempdir(), 'metronom-' + prefix.lower() + '.db')
    c = libsql.connect(path, sync_url=url, auth_token=token, isolation_level=None)
    c.sync()  # bootstrap from remote before touching the schema
    return Connection(c)
