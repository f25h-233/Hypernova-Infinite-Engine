import pytest

from hn_json import ParseError, loads


def test_comments_trailing_commas_and_single_quotes():
    text = """
    # hash comment
    {
      // slash comment
      'id': 'mod_x',   /* block */
      "name": "X",
      "nested": { "a": 1, },
      "list": [ 1, 2, ],
    }
    """
    assert loads(text) == {
        "id": "mod_x",
        "name": "X",
        "nested": {"a": 1},
        "list": [1, 2],
    }


def test_bare_enum_values_and_semicolon_separator():
    text = '{ "renderHints": [ RENDER_LOADED_MISSILES ], "a": 1; "b": 2 }'
    assert loads(text) == {"renderHints": ["RENDER_LOADED_MISSILES"], "a": 1, "b": 2}


def test_numbers_in_mod_dialect():
    text = '{"a": +100, "b": .97, "c": 1., "d": 0x1F, "e": 1.0f, "f": 033}'
    assert loads(text) == {"a": 100, "b": 0.97, "c": 1.0, "d": 31, "e": 1.0, "f": 33}


def test_hash_inside_string_is_preserved():
    assert loads('{"a": "x # y", "b": "http://z"}') == {"a": "x # y", "b": "http://z"}


def test_windows_paths_survive():
    assert loads(r'{"p": "graphics\\ships\\a.png"}') == {"p": "graphics\\ships\\a.png"}


def test_single_quoted_string_with_double_quote():
    assert loads('{"a": \'say "hi"\'}') == {"a": 'say "hi"'}


def test_trailing_closers_are_tolerated():
    assert loads('{"a": 1},') == {"a": 1}
    assert loads('{"a": 1}}') == {"a": 1}


def test_unterminated_string_raises():
    with pytest.raises(ParseError):
        loads('{"a": "oops}')
