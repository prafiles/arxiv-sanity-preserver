"""
Shared fixtures and import-time shims for the arxiv-sanity-preserver test suite.

The app is a python3 *port* of a python2 codebase and several of its imports
target APIs that no longer exist in the versions Flask/Flask-Limiter/Werkzeug
ship today. The shims below are applied here (never in the app code) so that
`import serve` and `import fetch_papers` succeed on Python 3.13:

1. werkzeug.check_password_hash / generate_password_hash
   Removed from the `werkzeug` top-level namespace in Werkzeug >= 2.3
   (they live in `werkzeug.security`). serve.py imports them from the old
   location, so we re-export them onto the `werkzeug` module.

2. flask._app_ctx_stack
   Removed in Flask >= 2.3. serve.py imports it but never uses it; we install
   a None placeholder so the import statement succeeds.

3. flask_limiter.Limiter(app, global_limits=[...])
   The `global_limits` keyword was replaced by `default_limits` in
   Flask-Limiter >= 3. We wrap Limiter.__init__ to translate the old kwarg.

4. `socks` module + IP_ROTATING_PROXY env var
   fetch_papers.py / download_pdfs.py configure a PySocks proxy at import
   time from an env var. Neither is available (or desirable) in tests, so a
   no-op `socks` stub is registered in sys.modules.

numpy is imported by serve.py (unused there) and is installed for real rather
than stubbed.
"""

import inspect
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import werkzeug
import werkzeug.security

for _fn in ('check_password_hash', 'generate_password_hash'):
    if not hasattr(werkzeug, _fn):
        setattr(werkzeug, _fn, getattr(werkzeug.security, _fn))

import flask

if not hasattr(flask, '_app_ctx_stack'):
    flask._app_ctx_stack = None

import flask_limiter

if 'global_limits' not in inspect.signature(flask_limiter.Limiter.__init__).parameters:
    _limiter_init = flask_limiter.Limiter.__init__

    def _limiter_init_patched(self, app=None, *args, **kwargs):
        legacy = kwargs.pop('global_limits', None)
        if legacy is not None and 'default_limits' not in kwargs:
            kwargs['default_limits'] = legacy
        return _limiter_init(self, app, *args, **kwargs)

    flask_limiter.Limiter.__init__ = _limiter_init_patched

if 'socks' not in sys.modules:
    _socks = types.ModuleType('socks')
    _socks.PROXY_TYPE_HTTP = 3
    _socks.setdefaultproxy = lambda *args, **kwargs: None
    _socks.socksocket = object
    sys.modules['socks'] = _socks

os.environ.setdefault('IP_ROTATING_PROXY', '127.0.0.1')

import pytest

from fake_db import FakeSQLite


def make_paper(rawid='1511.08198', version=1, title='A Paper', **overrides):
    """Build one feedparser-shaped paper record as stored in db.p."""
    paper = {
        'id': 'http://arxiv.org/abs/%sv%d' % (rawid, version),
        'title': title,
        'summary': 'We study things about %s.' % title.lower(),
        'link': 'http://arxiv.org/abs/%sv%d' % (rawid, version),
        'authors': [{'name': 'Ada Lovelace'}, {'name': 'Alan Turing'}],
        'tags': [{'term': 'cs.CV', 'scheme': 'http://arxiv.org/schemas/atom'}],
        'arxiv_primary_category': {'term': 'cs.CV', 'scheme': 'http://arxiv.org/schemas/atom'},
        'published': '2015-11-30T18:59:00Z',
        'updated': '2016-01-15T09:30:00Z',
        'arxiv_comment': '10 pages, 3 figures',
        '_rawid': rawid,
        '_version': version,
        'tscore': 0.5,
        'time_updated': 1452850200,
        'time_published': 1448909940,
    }
    paper.update(overrides)
    return paper


@pytest.fixture
def papers():
    """Two small paper records, the inline fixture used across the suite."""
    return [
        make_paper('1511.08198', 1, 'Recurrent Neural Networks'),
        make_paper('1512.03385', 2, 'Deep Residual Learning'),
    ]


@pytest.fixture
def app(tmp_path, monkeypatch, papers):
    """serve.py's Flask app with its __main__-time globals filled in."""
    import serve

    db = {p['_rawid']: p for p in papers}
    monkeypatch.setattr(serve, 'db', db, raising=False)
    monkeypatch.setattr(serve, 'SEARCH_DICT', {
        '1511.08198': {'neural': 5.0, 'networks': 5.0, 'deep': 1.0},
        '1512.03385': {'deep': 5.0, 'residual': 5.0},
    })
    monkeypatch.setattr(serve, 'sim_dict', {
        '1511.08198v1': ['1512.03385v2', '1511.08198v1'],
        '1512.03385v2': ['1512.03385v2', '1511.08198v1'],
    }, raising=False)
    monkeypatch.setattr(serve, 'user_sim', {7: ['1511.08198', '1512.03385']}, raising=False)
    monkeypatch.setattr(serve, 'TWITTER_TOP', [db['1511.08198']], raising=False)
    monkeypatch.setattr(serve, 'DATE_SORTED_PAPERS', serve.date_sort(), raising=False)
    monkeypatch.setattr(serve, 'TOP_SORTED_PAPERS', list(db.values()), raising=False)
    monkeypatch.setattr(serve, 'args', types.SimpleNamespace(num_results=200), raising=False)

    fake_db = FakeSQLite()
    serve.app.real_connect_db = serve.connect_db
    monkeypatch.setattr(serve, 'connect_db', lambda: fake_db, raising=False)
    serve.app.config.update(TESTING=True, SECRET_KEY='test-secret')
    # suite-wide request budget would otherwise trip the 20/min default limit
    serve.limiter.enabled = False
    serve.app.fake_db = fake_db
    return serve.app


@pytest.fixture
def client(app):
    return app.test_client()
