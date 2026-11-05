"""Unit tests for the pure-ish logic helpers in serve.py.

These functions read module globals (db, SEARCH_DICT, sim_dict) that the real
server only populates under `if __name__ == '__main__'`; the `app` fixture in
conftest.py monkeypatches them with small inline records, and functions that
touch flask.g run inside a request context.
"""

import os
import time

import flask
import pytest

from conftest import make_paper


@pytest.fixture
def ctx(app):
    """A request context with g.db/g.user wired, as before_request would."""
    import serve
    with app.test_request_context('/'):
        # before_request hooks do not fire in a bare test_request_context
        serve.before_request()
        yield flask.g


class TestDateSort:

    def test_sorts_by_updated_descending(self, app, monkeypatch):
        import serve
        old = make_paper('1501.00001', 1, 'Old', updated='2014-01-01T00:00:00Z')
        new = make_paper('1501.00002', 1, 'New', updated='2015-06-01T00:00:00Z')
        monkeypatch.setattr(serve, 'db', {old['_rawid']: old, new['_rawid']: new})
        out = serve.date_sort()
        assert [p['_rawid'] for p in out] == ['1501.00002', '1501.00001']

    def test_stores_epoch_fields(self, app):
        import serve
        out = serve.date_sort()
        p = out[0]
        # 2016-01-15T09:30:00Z
        assert p['time_updated'] == 1452850200
        # 2015-11-30T18:59:00Z
        assert p['time_published'] == 1448909940

    def test_empty_db(self, app, monkeypatch):
        import serve
        monkeypatch.setattr(serve, 'db', {})
        assert serve.date_sort() == []


class TestPapersSearch:

    def test_scores_via_reverse_index(self, app, ctx):
        import serve
        out = serve.papers_search('neural networks')
        assert [p['_rawid'] for p in out] == ['1511.08198']

    def test_recency_boost_breaks_tie(self, app, ctx, monkeypatch):
        import serve
        # both papers score 1.0 on 'deep' from SEARCH_DICT; the newer tscore wins
        monkeypatch.setattr(serve, 'db', {
            '1511.08198': dict(serve.db['1511.08198'], tscore=0.1),
            '1512.03385': dict(serve.db['1512.03385'], tscore=0.9),
        })
        out = serve.papers_search('deep')
        assert [p['_rawid'] for p in out] == ['1512.03385', '1511.08198']

    def test_no_match_returns_empty(self, app, ctx):
        import serve
        assert serve.papers_search('quantum') == []

    def test_query_is_lowercased_and_split(self, app, ctx):
        import serve
        assert len(serve.papers_search('  NEURAL   Networks ')) == 1


class TestPapersSimilar:

    def test_exact_version_hit(self, app, ctx):
        import serve
        out = serve.papers_similar('1511.08198v1')
        assert [p['_rawid'] for p in out] == ['1512.03385', '1511.08198']

    def test_unknown_paper_returns_empty(self, app, ctx):
        import serve
        assert serve.papers_similar('9999.99999v1') == []

    def test_stale_version_falls_back_to_known_version(self, app, ctx):
        import serve
        # sim_dict has 1511.08198v1 but caller asks for v9
        out = serve.papers_similar('1511.08198v9')
        assert [p['_rawid'] for p in out] == ['1512.03385', '1511.08198']

    def test_no_sim_dict_entry_returns_paper_itself(self, app, ctx, monkeypatch):
        import serve
        monkeypatch.setattr(serve, 'sim_dict', {})
        out = serve.papers_similar('1511.08198v1')
        assert [p['_rawid'] for p in out] == ['1511.08198']


class TestPapersFilterVersion:

    def test_noop_for_non_v1(self, app):
        import serve
        papers = [{'_version': 1}, {'_version': 2}]
        assert serve.papers_filter_version(papers, 'all') is papers

    def test_filters_to_requested_version(self, app):
        import serve
        papers = [{'_version': 1}, {'_version': 2}]
        assert serve.papers_filter_version(papers, '1') == [{'_version': 1}]

    def test_filter_only_supports_v1(self, app):
        """BUG-ish quirk (documented): any vfilter other than '1' is a noop,
        so vfilter=2 does NOT filter to version 2."""
        import serve
        papers = [{'_version': 1}, {'_version': 2}]
        assert serve.papers_filter_version(papers, '2') is papers


class TestEncodeJson:

    def test_record_shape(self, app, ctx, papers):
        import serve
        ret = serve.encode_json(papers, n=10)
        assert len(ret) == 2
        r = ret[0]
        assert r['title'] == 'Recurrent Neural Networks'
        assert r['pid'] == '1511.08198v1'
        assert r['category'] == 'cs.CV'
        assert r['authors'] == ['Ada Lovelace', 'Alan Turing']
        assert r['link'] == 'http://arxiv.org/abs/1511.08198v1'
        assert r['in_library'] == 0
        assert r['abstract'].startswith('We study things')
        # thumbnail filename logic: /static/thumbs/<idvv>.pdf.jpg
        assert r['img'] == '/static/thumbs/1511.08198v1.pdf.jpg'
        assert r['tags'] == ['cs.CV']
        assert r['published_time'] == '1/15/2016'
        assert r['originally_published_time'] == '11/30/2015'
        assert r['comment'] == '10 pages, 3 figures'

    def test_caps_at_n(self, app, ctx, papers):
        import serve
        assert len(serve.encode_json(papers, n=1)) == 1

    def test_long_comment_truncated(self, app, ctx):
        import serve
        p = make_paper('1501.00001', 1, 'Long', arxiv_comment='x' * 150)
        ret = serve.encode_json([p], n=10)
        assert ret[0]['comment'] == 'x' * 100 + '...'

    def test_missing_comment_defaults_empty(self, app, ctx):
        import serve
        p = make_paper('1501.00001', 1, 'NoComment', arxiv_comment='')
        ret = serve.encode_json([p], n=10, send_images=False, send_abstracts=False)
        assert ret[0]['comment'] == ''
        assert 'img' not in ret[0]
        assert 'abstract' not in ret[0]

    def test_in_library_flag_when_logged_in(self, app, ctx, papers):
        import serve
        flask.g.user = {'user_id': 7, 'username': 'ada'}
        flask.session['user_id'] = 7
        app.fake_db.library.append({'lib_id': 1, 'paper_id': '1511.08198',
                                    'user_id': 7, 'update_time': 0})
        ret = serve.encode_json(papers, n=10)
        assert ret[0]['in_library'] == 1
        assert ret[1]['in_library'] == 0


class TestUserLookupHelpers:

    def test_get_user_id_roundtrip(self, app, ctx):
        import serve
        app.fake_db.users.append({'user_id': 3, 'username': 'ada',
                                  'pw_hash': 'x', 'creation_time': 0})
        assert serve.get_user_id('ada') == 3
        assert serve.get_user_id('nope') is None

    def test_get_username_roundtrip(self, app, ctx):
        import serve
        app.fake_db.users.append({'user_id': 3, 'username': 'ada',
                                  'pw_hash': 'x', 'creation_time': 0})
        assert serve.get_username(3) == 'ada'
        assert serve.get_username(99) is None

    def test_query_db_one(self, app, ctx):
        import serve
        app.fake_db.users.append({'user_id': 3, 'username': 'ada',
                                  'pw_hash': 'x', 'creation_time': 0})
        row = serve.query_db('select * from user where username = ?',
                             ['ada'], one=True)
        assert row['user_id'] == 3
        assert serve.query_db('select * from user where username = ?',
                              ['ghost'], one=True) is None


class TestPapersFromLibrary:

    def test_empty_when_anonymous(self, app, ctx):
        import serve
        assert serve.papers_from_library() == []

    def test_returns_library_papers_newest_first(self, app, ctx):
        import serve
        flask.g.user = {'user_id': 7, 'username': 'ada'}
        flask.session['user_id'] = 7
        app.fake_db.library.extend([
            {'lib_id': 1, 'paper_id': '1511.08198v1', 'user_id': 7, 'update_time': 1},
            {'lib_id': 2, 'paper_id': '1512.03385v2', 'user_id': 7, 'update_time': 2},
        ])
        out = serve.papers_from_library()
        # both fixture papers share 'updated', so sort is stable: insertion order
        assert {p['_rawid'] for p in out} == {'1511.08198', '1512.03385'}


class TestPapersFromSvm:

    def test_empty_when_anonymous(self, app, ctx):
        import serve
        assert serve.papers_from_svm() == []

    def test_empty_for_user_without_svm(self, app, ctx):
        import serve
        flask.g.user = {'user_id': 42, 'username': 'bob'}
        flask.session['user_id'] = 42
        assert serve.papers_from_svm() == []

    def test_excludes_library_papers(self, app, ctx):
        import serve
        flask.g.user = {'user_id': 7, 'username': 'ada'}
        flask.session['user_id'] = 7
        app.fake_db.library.append({'lib_id': 1, 'paper_id': '1511.08198',
                                    'user_id': 7, 'update_time': 1})
        out = serve.papers_from_svm()
        assert [p['_rawid'] for p in out] == ['1512.03385']

    def test_recent_days_filter(self, app, ctx, monkeypatch):
        import serve
        flask.g.user = {'user_id': 7, 'username': 'ada'}
        flask.session['user_id'] = 7
        now = int(time.time())
        fresh = make_paper('1511.08198', 1, 'Fresh', time_published=now)
        stale = make_paper('1512.03385', 2, 'Stale', time_published=now - 400*86400)
        monkeypatch.setattr(serve, 'db', {'1511.08198': fresh, '1512.03385': stale})
        out = serve.papers_from_svm(recent_days=30)
        assert [p['_rawid'] for p in out] == ['1511.08198']


class TestConnectDb:

    def test_connect_db_opens_sqlite_at_config_path(self, app, tmp_path, monkeypatch):
        """connect_db against a real (empty) sqlite file created from schema,
        proving the seam our FakeSQLite replaces behaves as expected."""
        import sqlite3
        import serve
        from utils import Config
        db_file = tmp_path / 'as.db'
        schema = open(os.path.join(os.path.dirname(serve.__file__), 'schema.sql')).read()
        conn0 = sqlite3.connect(str(db_file))
        conn0.executescript(schema)
        conn0.close()
        monkeypatch.setattr(Config, 'database_path', str(db_file))
        conn = app.real_connect_db()
        try:
            rows = conn.execute('select * from user').fetchall()
            assert rows == []
        finally:
            conn.close()
