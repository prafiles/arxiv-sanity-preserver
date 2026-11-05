"""Unit tests for the two pure functions in fetch_papers.py.

conftest.py installs a no-op `socks` stub and IP_ROTATING_PROXY so this module
is importable offline (the real module configures a Tor/HTTP proxy at import).
"""

import feedparser
import pytest

from fetch_papers import encode_feedparser_dict, parse_arxiv_url


def feed(d):
    """Wrap a plain dict the way feedparser returns parsed entries."""
    return feedparser.FeedParserDict(d)


class TestEncodeFeedparserDict:

    def test_scalar_passthrough(self):
        assert encode_feedparser_dict('title') == 'title'
        assert encode_feedparser_dict(42) == 42
        assert encode_feedparser_dict(None) is None

    def test_converts_feedparser_dict_to_plain_dict(self):
        out = encode_feedparser_dict(feed({'title': 'hi'}))
        assert out == {'title': 'hi'}
        assert type(out) is dict

    def test_deep_conversion(self):
        nested = feed({
            'title': 't',
            'links': [feed({'href': 'u1', 'type': 'application/pdf'}),
                      feed({'href': 'u2'})],
            'author': 'someone',
        })
        out = encode_feedparser_dict(nested)
        assert out == {'title': 't',
                       'links': [{'href': 'u1', 'type': 'application/pdf'},
                                 {'href': 'u2'}],
                       'author': 'someone'}
        assert type(out['links']) is list
        assert all(type(el) is dict for el in out['links'])

    def test_plain_dict_and_list_also_convert(self):
        out = encode_feedparser_dict({'a': [{'b': 1}]})
        assert out == {'a': [{'b': 1}]}
        assert type(out) is dict and type(out['a'][0]) is dict


class TestParseArxivUrl:

    def test_bug_function_is_broken_and_raises_nameerror(self):
        """BUG (documented, not fixed): parse_arxiv_url references `j`, a name
        that does not exist in its scope (serve/fetch author intended the
        caller's entry dict `j['id']`; the parameter is `url`). Every call
        raises NameError, so fetch_papers' __main__ loop would crash on the
        first entry. The intended behavior — parse
        'http://arxiv.org/abs/1512.08756v2' into ('1512.08756', 2) — is
        untestable until the one-line fix lands; this test pins the *current*
        behavior so the fix will visibly flip this test to red.
        """
        with pytest.raises(NameError):
            parse_arxiv_url('http://arxiv.org/abs/1512.08756v2')
