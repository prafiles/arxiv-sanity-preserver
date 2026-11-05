"""
A tiny hand-rolled fake for the sqlite3 connection that serve.py uses.

serve.py touches the database through only a few seams:

  g.db = connect_db()                       # before_request
  g.db.execute(query, args) -> cursor       # + .fetchall() / .fetchone()
  cur.fetchall()                            # via query_db()
  g.db.execute(...); g.db.commit()          # writes
  g.db.close()                              # teardown_request

Rather than pull in mongomock/sqlalchemy, this module implements just enough
of that surface for the SQL strings serve.py actually issues (selects and
inserts/deletes against `user` and `library`, plus `select last_insert_rowid()`).
Rows are returned as dicts, which behave like sqlite3.Row for the subscripting
serve.py performs (row['col']). Unknown SQL raises, so tests can never silently
pass against a query the fake doesn't implement.
"""

import re


class FakeRow(object):
    """Stand-in for sqlite3.Row: supports both row['col'] and positional row[0].

    serve.py relies on both forms (query_db callers use ['paper_id'], while
    get_user_id does rv[0] to pull the scalar out of a one-column row), and
    Jinja renders g.user.username via getattr-then-getitem fallback.
    """

    def __init__(self, mapping):
        self._d = dict(mapping)

    def __getitem__(self, key):
        return self._d[key] if isinstance(key, str) else list(self._d.values())[key]

    def __iter__(self):
        return iter(self._d)

    def __len__(self):
        return len(self._d)

    def __bool__(self):
        return bool(self._d)

    def keys(self):
        return self._d.keys()

    def __repr__(self):
        return 'FakeRow(%r)' % (self._d,)


class FakeCursor(object):

    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


class FakeSQLite(object):
    """In-memory stand-in for the sqlite3 connection serve.py opens on as.db."""

    def __init__(self):
        self.users = []      # dicts: user_id, username, pw_hash, creation_time
        self.library = []    # dicts: lib_id, paper_id, user_id, update_time
        self.closed = False
        self.commits = 0
        self._next_user_id = 1
        self._next_lib_id = 1
        self._last_insert_rowid = 0

    # -- sqlite3.Connection surface -----------------------------------------

    def execute(self, query, args=()):
        q = ' '.join(query.split())  # normalize whitespace/newlines
        m = re.match(r'select \* from user where username = \?$', q)
        if m:
            username = args[0]
            return FakeCursor([FakeRow(u) for u in self.users if u['username'] == username])

        m = re.match(r'select user_id from user where username = \?$', q)
        if m:
            username = args[0]
            return FakeCursor([FakeRow({'user_id': u['user_id']})
                               for u in self.users if u['username'] == username])

        m = re.match(r'select username from user where user_id = \?$', q)
        if m:
            uid = args[0]
            return FakeCursor([FakeRow({'username': u['username']})
                               for u in self.users if u['user_id'] == uid])

        m = re.match(r'select \* from user where user_id = \?$', q)
        if m:
            uid = args[0]
            return FakeCursor([FakeRow(u) for u in self.users if u['user_id'] == uid])

        m = re.match(r'select \* from library where user_id = \?$', q)
        if m:
            uid = args[0]
            return FakeCursor([FakeRow(r) for r in self.library if r['user_id'] == uid])

        m = re.match(r'select \* from library where user_id = \? and paper_id = \?$', q)
        if m:
            uid, pid = args[0], args[1]
            return FakeCursor([FakeRow(r) for r in self.library
                               if r['user_id'] == uid and r['paper_id'] == pid])

        m = re.match(r'select last_insert_rowid\(\)$', q)
        if m:
            return FakeCursor([[self._last_insert_rowid]])

        m = re.match(r'insert into user \(username, pw_hash, creation_time\)'
                     r' values \(\?, \?, \?\)$', q)
        if m:
            username, pw_hash, creation_time = args
            row = {'user_id': self._next_user_id, 'username': username,
                   'pw_hash': pw_hash, 'creation_time': creation_time}
            self.users.append(row)
            self._last_insert_rowid = self._next_user_id
            self._next_user_id += 1
            return FakeCursor([])

        m = re.match(r'insert into library \(paper_id, user_id, update_time\)'
                     r' values \(\?, \?, \?\)$', q)
        if m:
            paper_id, uid, update_time = args
            row = {'lib_id': self._next_lib_id, 'paper_id': paper_id,
                   'user_id': uid, 'update_time': update_time}
            self.library.append(row)
            self._last_insert_rowid = self._next_lib_id
            self._next_lib_id += 1
            return FakeCursor([])

        m = re.match(r'delete from library where user_id = \? and paper_id = \?$', q)
        if m:
            uid, pid = args[0], args[1]
            self.library = [r for r in self.library
                            if not (r['user_id'] == uid and r['paper_id'] == pid)]
            return FakeCursor([])

        raise AssertionError('FakeSQLite: unhandled SQL: %r' % (q,))

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True
