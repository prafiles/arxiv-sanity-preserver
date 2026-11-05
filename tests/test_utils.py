"""Unit tests for utils.py: arxiv-id helpers, atomic writes, config defaults."""

import os
import pickle

import pytest

from utils import (Config, isvalidid, open_atomic, safe_pickle_dump,
                   strip_version)


class TestStripVersion:

    def test_strips_version_suffix(self):
        assert strip_version('1511.08198v1') == '1511.08198'

    def test_strips_multi_digit_version(self):
        assert strip_version('1511.08198v12') == '1511.08198'

    def test_noop_without_version(self):
        assert strip_version('1511.08198') == '1511.08198'

    def test_bug_splits_on_any_v_not_only_version_suffix(self):
        """BUG (documented, not fixed): split('v') splits on *any* 'v'.

        An id whose digits contain a 'v' anywhere (or a leading 'v') is
        mangled instead of passed through. Correct output would be
        'v1511.08198'; the function returns ''. Recorded in the report.
        """
        assert strip_version('v1511.08198') == ''


class TestIsValidId:

    @pytest.mark.parametrize('pid', [
        '1511.08198',
        '1511.08198v1',
        '1512.03385v23',
        '1706.03762v7',
    ])
    def test_accepts_valid_ids(self, pid):
        assert isvalidid(pid)

    @pytest.mark.parametrize('pid', [
        '',
        'nonsense',
        '1511.08198v',        # version marker without digits
        '1511.08198v1x',
        '1511.08198 v1',
        'v1',
        'arxiv/1511.08198',
    ])
    def test_rejects_invalid_ids(self, pid):
        assert not isvalidid(pid)


class TestAtomicWrites:

    def test_open_atomic_writes_file(self, tmp_path):
        fp = tmp_path / 'out.txt'
        with open_atomic(str(fp), 'w') as f:
            f.write('hello')
        assert fp.read_text() == 'hello'

    def test_open_atomic_replaces_existing(self, tmp_path):
        fp = tmp_path / 'out.txt'
        fp.write_text('old')
        with open_atomic(str(fp), 'w') as f:
            f.write('new')
        assert fp.read_text() == 'new'

    def test_open_atomic_leaves_no_temp_files(self, tmp_path):
        fp = tmp_path / 'out.txt'
        with open_atomic(str(fp), 'w') as f:
            f.write('x')
        assert [p.name for p in tmp_path.iterdir()] == ['out.txt']

    def test_open_atomic_aborts_on_exception(self, tmp_path):
        fp = tmp_path / 'out.txt'
        fp.write_text('keepme')
        with pytest.raises(ValueError):
            with open_atomic(str(fp), 'w') as f:
                f.write('discard')
                raise ValueError('boom')
        # atomicity: original content survives, no stray temp file
        assert fp.read_text() == 'keepme'
        assert [p.name for p in tmp_path.iterdir()] == ['out.txt']

    def test_bug_fsync_path_raises_nameerror(self, tmp_path):
        """BUG (documented, not fixed): open_atomic(..., fsync=True) crashes.

        The fsync branch references an undefined name `file` instead of `f`
        (utils.py), so any fsync=True call raises NameError *after* the
        partial write, aborting the atomic rename.
        """
        fp = tmp_path / 'out.txt'
        with pytest.raises(NameError):
            with open_atomic(str(fp), 'w', fsync=True) as f:
                f.write('hello')

    def test_safe_pickle_dump_roundtrip(self, tmp_path):
        fp = tmp_path / 'obj.p'
        obj = {'a': [1, 2, {'b': 'c'}]}
        safe_pickle_dump(obj, str(fp))
        assert pickle.load(open(str(fp), 'rb')) == obj


class TestConfig:

    def test_default_paths(self):
        """Config loading: the module-level defaults the whole pipeline shares."""
        assert Config.db_path == 'db.p'
        assert Config.pdf_dir == os.path.join('data', 'pdf')
        assert Config.txt_dir == os.path.join('data', 'txt')
        assert Config.thumbs_dir == os.path.join('static', 'thumbs')
        assert Config.database_path == 'as.db'
        assert Config.tmp_dir == 'tmp'
        for attr in ('tfidf_path', 'meta_path', 'sim_path', 'user_sim_path',
                     'tweet_path', 'search_dict_path'):
            assert getattr(Config, attr).endswith('.p')

    def test_config_is_monkeypatchable_for_tests(self, monkeypatch, tmp_path):
        """The pipeline scripts read Config attributes at call time, so tests
        (and users) can override them; verify that override path works."""
        monkeypatch.setattr(Config, 'db_path', str(tmp_path / 'other.p'))
        assert Config.db_path == str(tmp_path / 'other.p')
