import json
from copy import deepcopy
from importlib.resources import files
import pytest
from fastlanelabs_sdk.themes import ThemeError, validate_theme


def theme():
    return json.loads(files('fastlanelabs_sdk.registry_data').joinpath('default-theme.json').read_text())


def test_default_is_complete_and_returns_an_independent_token_map():
    original = theme()
    validated = validate_theme(original)
    validated['tokens']['primitives']['ink-900'] = '#000000'
    assert original['tokens']['primitives']['ink-900'] == '#1a1b21'


@pytest.mark.parametrize('change', [
    lambda t: t.update(api_version=1),
    lambda t: t.update(registry_revision=3),
    lambda t: t['tokens']['primitives'].pop('ink-900'),
    lambda t: t['tokens']['primitives'].update({'font-sans': 'url(https://example.com/font)'}),
    lambda t: t['tokens']['semantic'].update({'surface': '#fff;display:none'}),
    lambda t: t['layout']['sidebar'].update({'style': 'custom-js'}),
    lambda t: t.update(id='../escape'),
    lambda t: t.update(script='alert(1)'),
    lambda t: t['tokens']['primitives'].update({'ink-900': '#ffffff'}),
])
def test_unsupported_or_executable_themes_are_rejected(change):
    candidate = deepcopy(theme())
    change(candidate)
    with pytest.raises(ThemeError):
        validate_theme(candidate)


def test_a_rail_layout_is_supported_without_changing_tokens():
    candidate = theme()
    candidate['layout']['sidebar'].update(style='rail', width=56)
    assert validate_theme(candidate)['layout']['sidebar']['style'] == 'rail'
    assert validate_theme(candidate)['tokens'] == theme()['tokens']
