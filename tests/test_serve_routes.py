"""Flask route tests for serve.py using test_client + the fake sqlite layer.

The real routes depend on __main__-time globals (db, DATE_SORTED_PAPERS, ...)
and a sqlite3 connection; conftest's `app` fixture supplies both (fake_db.py).
"""

import json

import pytest


class TestStaticAndIndex:

    def test_index_renders(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'var papers =' in html
        assert 'Recurrent Neural Networks' in html

    def test_index_vfilter(self, client):
        resp = client.get('/?vfilter=1')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Recurrent Neural Networks' in html
        assert 'Deep Residual Learning' not in html  # fixture v2 is filtered out

    def test_unknown_non_pid_path_returns_empty(self, client):
        # route /<request_pid> swallows malformed ids (favicon etc.) with ''
        resp = client.get('/robots.txt')
        assert resp.status_code == 200
        assert resp.data == b''


class TestRankRoute:

    def test_valid_pid_renders_similar_papers(self, client):
        resp = client.get('/1511.08198v1')
        assert resp.status_code == 200
        assert 'Deep Residual Learning' in resp.data.decode('utf-8')


class TestSearchRoute:

    def test_search_hit(self, client):
        resp = client.get('/search?q=neural networks')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Recurrent Neural Networks' in html

    def test_search_miss(self, client):
        resp = client.get('/search?q=quantum')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Recurrent Neural Networks' not in html

    def test_empty_query(self, client):
        resp = client.get('/search')
        assert resp.status_code == 200


class TestTopAndTwitter:

    def test_top_renders(self, client):
        resp = client.get('/top')
        assert resp.status_code == 200

    def test_top_timefilter(self, client):
        # fixture papers were published in 2015 -> outside a 'day' window
        resp = client.get('/top?timefilter=day')
        assert resp.status_code == 200
        assert 'Recurrent Neural Networks' not in resp.data.decode('utf-8')
        resp = client.get('/top?timefilter=alltime')
        assert resp.status_code == 200
        assert 'Recurrent Neural Networks' in resp.data.decode('utf-8')

    def test_toptwtr_renders(self, client):
        resp = client.get('/toptwtr')
        assert resp.status_code == 200
        assert 'Recurrent Neural Networks' in resp.data.decode('utf-8')


class TestRecommendRoute:

    def test_anonymous_gets_login_message(self, client):
        resp = client.get('/recommend')
        assert resp.status_code == 200
        assert 'You must be logged in' in resp.data.decode('utf-8')

    def test_logged_in_user_gets_svm_list(self, client, app):
        with client.session_transaction() as sess:
            sess['user_id'] = 7
        app.fake_db.users.append({'user_id': 7, 'username': 'ada',
                                  'pw_hash': 'x', 'creation_time': 0})
        # 'all' is not in the legend, so recent_days stays None -> no time
        # filter (fixture papers are from 2015 and would fail a 'week' window)
        resp = client.get('/recommend?timefilter=all')
        assert resp.status_code == 200
        assert 'Recurrent Neural Networks' in resp.data.decode('utf-8')

    def test_logged_in_week_filter_excludes_old_papers(self, client, app):
        with client.session_transaction() as sess:
            sess['user_id'] = 7
        app.fake_db.users.append({'user_id': 7, 'username': 'ada',
                                  'pw_hash': 'x', 'creation_time': 0})
        resp = client.get('/recommend?timefilter=week')
        assert resp.status_code == 200
        assert 'Recurrent Neural Networks' not in resp.data.decode('utf-8')


class TestLibraryAndAuth:

    def test_library_anonymous(self, client):
        resp = client.get('/library')
        assert resp.status_code == 200
        assert 'You must be logged in' in resp.data.decode('utf-8')

    def test_login_creates_account_and_logs_in(self, client, app):
        resp = client.post('/login', data={'username': 'ada', 'password': 'pw'})
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/')
        assert len(app.fake_db.users) == 1
        user = app.fake_db.users[0]
        assert user['username'] == 'ada'
        assert user['pw_hash'] != 'pw'  # stored hashed
        with client.session_transaction() as sess:
            assert sess['user_id'] == user['user_id']

    def test_login_existing_user_wrong_password(self, client, app):
        client.post('/login', data={'username': 'ada', 'password': 'pw'})
        resp = client.post('/login', data={'username': 'ada', 'password': 'bad'})
        assert resp.status_code == 302
        # still only one account, session not re-established with new id
        assert len(app.fake_db.users) == 1

    def test_login_existing_user_right_password(self, client, app):
        client.post('/login', data={'username': 'ada', 'password': 'pw'})
        app.fake_db.users.clear()
        with client.session_transaction() as sess:
            sess.clear()
        # re-add the user with a real hash to test the check_password_hash path
        from werkzeug.security import generate_password_hash
        app.fake_db.users.append({'user_id': 5, 'username': 'ada',
                                  'pw_hash': generate_password_hash('pw'),
                                  'creation_time': 0})
        resp = client.post('/login', data={'username': 'ada', 'password': 'pw'})
        assert resp.status_code == 302
        with client.session_transaction() as sess:
            assert sess['user_id'] == 5

    def test_logout_clears_session(self, client, app):
        client.post('/login', data={'username': 'ada', 'password': 'pw'})
        resp = client.get('/logout')
        assert resp.status_code == 302
        with client.session_transaction() as sess:
            assert 'user_id' not in sess

    def test_libtoggle_requires_login(self, client):
        resp = client.post('/libtoggle', data={'pid': '1511.08198v1'})
        assert resp.status_code == 200
        assert resp.data == b'NO'

    def test_libtoggle_on_then_off(self, client, app):
        client.post('/login', data={'username': 'ada', 'password': 'pw'})
        resp = client.post('/libtoggle', data={'pid': '1511.08198v1'})
        assert resp.data == b'ON'
        assert len(app.fake_db.library) == 1
        assert app.fake_db.library[0]['paper_id'] == '1511.08198'  # version stripped
        resp = client.post('/libtoggle', data={'pid': '1511.08198v1'})
        assert resp.data == b'OFF'
        assert app.fake_db.library == []

    def test_libtoggle_rejects_malformed_pid(self, client, app):
        client.post('/login', data={'username': 'ada', 'password': 'pw'})
        resp = client.post('/libtoggle', data={'pid': 'not-a-real-id'})
        assert resp.data == b'NO'
        assert app.fake_db.library == []

    def test_libtoggle_rejects_unknown_paper(self, client, app):
        client.post('/login', data={'username': 'ada', 'password': 'pw'})
        resp = client.post('/libtoggle', data={'pid': '9999.99999v1'})
        assert resp.data == b'NO'
        assert app.fake_db.library == []

    def test_library_shows_saved_papers(self, client, app):
        client.post('/login', data={'username': 'ada', 'password': 'pw'})
        client.post('/libtoggle', data={'pid': '1511.08198v1'})
        resp = client.get('/library')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Recurrent Neural Networks' in html
        assert '1 papers in your library' in html
