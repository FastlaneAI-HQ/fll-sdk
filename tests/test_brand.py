"""The brand: validate_brand, normalise_brand, the theme around it and the registry additions that came with it.

docs/brand-logo.md is the specification. Every rule has a negative test with the exact path and message; the limits (types, sizes,
alt, height, tagline) are read from the layout vocabulary's `brand.logo_limits`, which these tests also change to prove nothing is
hard-coded. tests/test_layout_tree_parity.py runs the TypeScript twin over `brand_cases()` below.
"""
import base64
import copy
import json
import random
from pathlib import Path

import pytest

from fastlanelabs_sdk import theme_registry as registry
from fastlanelabs_sdk import themes
from fastlanelabs_sdk.themes import ThemeError, brand_logo_for, brand_of, check_theme, default_theme_v2, normalise_brand, resolve_theme, validate_brand, validate_theme

ROOT = Path(__file__).resolve().parents[1]
VOCAB = registry.layout_vocabulary()
LIMITS = VOCAB['brand']['logo_limits']
IMAGE_MAX = LIMITS['max_image_bytes']
TOTAL_MAX = LIMITS['max_total_bytes']
ALT_MAX = LIMITS['alt_max']
TAGLINE_MAX = LIMITS['tagline_max']
HEIGHT = LIMITS['height']

PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
JPEG_MAGIC = b'\xff\xd8\xff\xe0'
WEBP_MAGIC = b'RIFF\x04\x00\x00\x00WEBP'
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#336"/></svg>'


def png(size=24):
    return PNG_MAGIC + b'\x00' * (size - len(PNG_MAGIC))


def uri(data, mime='image/png'):
    return f'data:{mime};base64,' + base64.b64encode(data).decode()


def svg_uri(text):
    return uri(text.encode('utf-8') if isinstance(text, str) else text, 'image/svg+xml')


def logo(**changes):
    return dict({'src': uri(png()), 'alt': 'Precision Hose'}, **changes)


def good():
    return {'logo': dict(logo(), height=36), 'mark': {'src': uri(JPEG_MAGIC + b'\x00' * 8, 'image/jpeg'), 'alt': 'Precision Hose mark'},
            'tagline': 'Hose & expansion joints'}


def verdict(brand, vocabulary=None):
    found = validate_brand(brand, vocabulary)
    assert found['warnings'] == []
    return found['errors']


def only(brand, vocabulary=None):
    """The single error of a brand, as (path, message)."""
    errors = verdict(brand, vocabulary)
    assert len(errors) == 1, errors
    return errors[0]['path'], errors[0]['message']


def with_svg(body):
    return {'logo': logo(src=svg_uri(body))}


# --- Valid brands ---------------------------------------------------------------------------------------------------------

def test_logo_only_mark_only_tagline_only_and_all_three_are_valid():
    full = good()
    for brand in (full, {'logo': full['logo']}, {'logo': logo()}, {'mark': full['mark']}, {'tagline': 'Hose'}, {'logo': logo(), 'tagline': 'x'},
                  {'logo': full['logo'], 'mark': full['mark']}):
        assert verdict(brand) == [], brand


def test_every_allowed_type_is_accepted_with_its_own_signature():
    payloads = {'image/png': png(), 'image/jpeg': JPEG_MAGIC + b'\x00' * 8, 'image/webp': WEBP_MAGIC + b'VP8 ', 'image/svg+xml': SVG.encode()}
    assert sorted(payloads) == sorted(LIMITS['types'])
    for mime, data in payloads.items():
        assert verdict({'logo': logo(src=uri(data, mime))}) == [], mime


def test_the_default_height_is_filled_and_the_text_is_trimmed_by_normalise_brand():
    brand = {'logo': logo(alt='  Precision Hose  '), 'tagline': '  Hose 　'}
    assert normalise_brand(brand) == {'logo': {'src': brand['logo']['src'], 'alt': 'Precision Hose', 'height': HEIGHT['default']},
                                      'logo_dark': None, 'mark': None, 'tagline': 'Hose'}
    assert normalise_brand(good())['logo']['height'] == 36
    assert normalise_brand({'mark': {'src': uri(png()), 'alt': ' m '}}) == {'logo': None, 'logo_dark': None, 'mark': {'src': uri(png()), 'alt': 'm'},
                                                                              'tagline': None}
    assert normalise_brand(None) is None
    assert brand == {'logo': logo(alt='  Precision Hose  '), 'tagline': '  Hose 　'}  # the input is not changed


def test_a_default_height_from_a_newer_vocabulary_is_used():
    vocab = copy.deepcopy(VOCAB)
    vocab['brand']['logo_limits']['height'].update(default=40, max=80)
    assert normalise_brand({'logo': logo()}, vocab)['logo']['height'] == 40
    assert verdict({'logo': logo(height=80)}, vocab) == []
    assert only({'logo': logo(height=80)}) == ('brand.logo.height', 'Must be a whole number 16-64')


# --- The shape ------------------------------------------------------------------------------------------------------------

def test_brand_must_be_an_object_with_something_in_it():
    for junk in (None, [], 'x', 3, True):
        assert only(junk) == ('brand', 'Brand must be an object with logo, mark and tagline')
    assert only({}) == ('brand', 'Brand must set logo, mark or tagline')


def test_unknown_keys_are_errors_in_alphabetical_order_at_every_level():
    errors = verdict({'zzz': 1, 'aaa': 2, 'logo': dict(logo(), zoom=2, color='red'), 'mark': dict(logo(), height=40), 'tagline': 'ok'})
    assert [(e['path'], e['message']) for e in errors] == [
        ('brand.aaa', 'Unknown key aaa'), ('brand.zzz', 'Unknown key zzz'),
        ('brand.logo.color', 'Unknown key color'), ('brand.logo.zoom', 'Unknown key zoom'),
        ('brand.mark.height', 'Unknown key height')]  # a mark has no height: it is drawn square at the host's badge size


def test_logo_and_mark_must_be_objects_with_src_and_alt():
    assert only({'logo': 'x'}) == ('brand.logo', 'Must be an object with src and alt')
    assert only({'mark': [1]}) == ('brand.mark', 'Must be an object with src and alt')
    assert [(e['path'], e['message']) for e in verdict({'logo': {}})] == [('brand.logo.src', 'Required'), ('brand.logo.alt', 'Required')]
    assert only({'logo': {'src': uri(png())}}) == ('brand.logo.alt', 'Required')
    assert only({'mark': {'alt': 'x'}}) == ('brand.mark.src', 'Required')


def test_problems_come_in_a_fixed_order_logo_mark_tagline_then_the_total():
    errors = verdict({'tagline': '', 'mark': {'src': 'http://x/y.png', 'alt': ''}, 'logo': {'src': 3, 'alt': 4, 'height': 5}})
    assert [e['path'] for e in errors] == ['brand.logo.src', 'brand.logo.alt', 'brand.logo.height', 'brand.mark.src', 'brand.mark.alt', 'brand.tagline']


# --- logo_dark: the logo drawn on dark backgrounds ------------------------------------------------------------------------

DARK_SRC = uri(PNG_MAGIC + b'\x01' * 8)


def dark(**changes):
    return dict({'src': DARK_SRC, 'alt': 'Precision Hose (light on dark)'}, **changes)


def with_dark(extra=None, **brand):
    return dict({'logo': logo(), 'logo_dark': dark(**(extra or {}))}, **brand)


def test_logo_dark_is_an_optional_image_with_the_rules_of_logo():
    assert verdict(with_dark()) == [] and verdict(with_dark({'height': 40})) == []
    assert verdict(dict(good(), logo_dark=dark())) == []
    for key, bad, message in (('src', 'http://x/y.png', "Must be a data: URI (data:image/png;base64,...); a theme's images are never fetched"),
                              ('alt', '', 'Must be 1 to 80 characters'), ('height', 15, 'Must be a whole number 16-64')):
        assert only(with_dark({key: bad})) == (f'brand.logo_dark.{key}', message.replace('80', str(ALT_MAX)).replace('16-64', f"{HEIGHT['min']}-{HEIGHT['max']}"))
    assert only(with_dark({'zoom': 2})) == ('brand.logo_dark.zoom', 'Unknown key zoom')
    assert only({'logo': logo(), 'logo_dark': 'x'}) == ('brand.logo_dark', 'Must be an object with src and alt')
    assert [(e['path'], e['message']) for e in verdict({'logo': logo(), 'logo_dark': {}})] == [('brand.logo_dark.src', 'Required'), ('brand.logo_dark.alt', 'Required')]


def test_logo_dark_needs_a_logo_and_the_error_sits_at_logo_dark():
    assert only({'logo_dark': dark()}) == ('brand.logo_dark', 'logo_dark needs a logo')
    assert only({'logo_dark': dark(), 'tagline': 'x'}) == ('brand.logo_dark', 'logo_dark needs a logo')
    assert only({'logo_dark': dark(), 'mark': {'src': uri(png()), 'alt': 'm'}}) == ('brand.logo_dark', 'logo_dark needs a logo')
    # the image is judged as well, right after: the author sees every problem at once
    assert [(e['path'], e['message']) for e in verdict({'logo_dark': dark(height=3, alt='')})] == [
        ('brand.logo_dark', 'logo_dark needs a logo'), ('brand.logo_dark.alt', 'Must be 1 to 80 characters'),
        ('brand.logo_dark.height', 'Must be a whole number 16-64')]
    # a logo that is present but broken still counts as set
    assert [e['path'] for e in verdict({'logo': {'src': 3, 'alt': 4}, 'logo_dark': dark()})] == ['brand.logo.src', 'brand.logo.alt']
    assert [(e['path'], e['message']) for e in verdict({'logo_dark': 'x'})] == [
        ('brand.logo_dark', 'logo_dark needs a logo'), ('brand.logo_dark', 'Must be an object with src and alt')]


def test_the_order_of_problems_is_unknown_keys_logo_logo_dark_mark_tagline_total():
    errors = verdict({'zzz': 1, 'tagline': '', 'mark': {'src': 'x', 'alt': ''}, 'logo_dark': {'src': 3, 'alt': 4, 'height': 5, 'x': 1},
                      'logo': {'src': 3, 'alt': 4, 'height': 5, 'y': 1}})
    assert [e['path'] for e in errors] == [
        'brand.zzz', 'brand.logo.y', 'brand.logo.src', 'brand.logo.alt', 'brand.logo.height',
        'brand.logo_dark.x', 'brand.logo_dark.src', 'brand.logo_dark.alt', 'brand.logo_dark.height',
        'brand.mark.src', 'brand.mark.alt', 'brand.tagline']
    big = with_dark({'src': uri(png(IMAGE_MAX))})
    big['logo'] = logo(src=uri(png(IMAGE_MAX)))
    assert only(big)[0] == 'brand'


def test_the_size_limits_count_logo_dark():
    assert verdict({'logo': logo(src=uri(png(IMAGE_MAX))), 'logo_dark': dark(src=uri(png(TOTAL_MAX - IMAGE_MAX)))}) == []
    assert only({'logo': logo(src=uri(png(IMAGE_MAX))), 'logo_dark': dark(src=uri(png(TOTAL_MAX - IMAGE_MAX + 1)))}) == (
        'brand', f'The images of a brand add up to {TOTAL_MAX + 1} bytes; at most {TOTAL_MAX // 1024} KiB')
    assert only({'logo': logo(), 'logo_dark': dark(src=uri(png(IMAGE_MAX + 1)))}) == (
        'brand.logo_dark.src', f'The image is {IMAGE_MAX + 1} bytes; at most {IMAGE_MAX // 1024} KiB')
    # three images: each under the per-image limit, together over the total
    three = {'logo': logo(src=uri(png(IMAGE_MAX))), 'logo_dark': dark(src=uri(png(IMAGE_MAX // 2))), 'mark': {'src': uri(png(IMAGE_MAX // 2)), 'alt': 'm'}}
    assert only(three)[0] == 'brand'
    # a broken logo_dark is not counted
    assert [e['path'] for e in verdict({'logo': logo(src=uri(png(IMAGE_MAX))), 'logo_dark': dark(src=uri(JPEG_MAGIC + b'\x00' * (TOTAL_MAX - IMAGE_MAX)))})] == ['brand.logo_dark.src']


def test_logo_dark_is_an_svg_checked_like_the_logo():
    assert verdict({'logo': logo(), 'logo_dark': dark(src=svg_uri(SVG))}) == []
    assert only({'logo': logo(), 'logo_dark': dark(src=svg_uri(svg('<script/>')))}) == ('brand.logo_dark.src', 'An SVG must not contain <script>')
    assert only({'logo': logo(), 'logo_dark': dark(src=svg_uri(SVG.encode() + b'\xc3'))}) == ('brand.logo_dark.src', 'An SVG must be UTF-8 text')
    assert only({'logo': logo(), 'logo_dark': dark(src=uri(png(), 'image/jpeg'))}) == (
        'brand.logo_dark.src', 'The data is not a JPEG image (wrong file signature)')


def test_logo_dark_height_defaults_to_the_logos_height_else_the_vocabulary_default():
    assert normalise_brand({'logo': logo(height=44), 'logo_dark': dark()})['logo_dark']['height'] == 44
    assert normalise_brand({'logo': logo(), 'logo_dark': dark()})['logo_dark']['height'] == HEIGHT['default']
    assert normalise_brand({'logo': logo(height=44), 'logo_dark': dark(height=20)})['logo_dark']['height'] == 20
    assert normalise_brand({'logo': logo(height=44), 'logo_dark': dark(height=20)})['logo']['height'] == 44
    assert normalise_brand({'logo_dark': dark()})['logo_dark']['height'] == HEIGHT['default']  # (invalid: no logo) the vocabulary's default
    vocab = copy.deepcopy(VOCAB)
    vocab['brand']['logo_limits']['height'].update(default=48, max=80)
    assert normalise_brand({'logo': logo(), 'logo_dark': dark()}, vocab)['logo_dark']['height'] == 48
    assert verdict({'logo': logo(height=80), 'logo_dark': dark(height=80)}, vocab) == []
    assert only({'logo': logo(), 'logo_dark': dark(height=80)}) == ('brand.logo_dark.height', 'Must be a whole number 16-64')


def test_normalise_brand_keeps_logo_dark_trims_its_alt_and_leaves_the_input_alone():
    brand = {'logo': logo(), 'logo_dark': dark(alt='  light on dark  ')}
    out = normalise_brand(brand)
    assert out['logo_dark'] == {'src': DARK_SRC, 'alt': 'light on dark', 'height': HEIGHT['default']}
    assert list(out) == ['logo', 'logo_dark', 'mark', 'tagline']
    assert brand['logo_dark']['alt'] == '  light on dark  ' and 'height' not in brand['logo_dark']
    assert normalise_brand({'logo': logo()})['logo_dark'] is None


def test_brand_logo_for_picks_the_logo_for_the_background():
    plain = normalise_brand({'logo': logo(height=40)})
    both = normalise_brand({'logo': logo(height=40), 'logo_dark': dark()})
    mark_only = normalise_brand({'mark': {'src': uri(png()), 'alt': 'm'}})
    assert brand_logo_for(plain, False) == brand_logo_for(plain, True) == plain['logo']
    assert brand_logo_for(both, False) == both['logo'] and brand_logo_for(both, True) == both['logo_dark'] != both['logo']
    assert brand_logo_for(both, True)['height'] == 40
    assert brand_logo_for(mark_only, False) is None and brand_logo_for(mark_only, True) is None
    assert brand_logo_for(None, False) is None and brand_logo_for(None, True) is None
    assert brand_logo_for(both, 0) == both['logo'] and brand_logo_for(both, 1) == both['logo_dark']  # truthiness, as in JavaScript


def test_a_theme_with_a_logo_dark_validates_and_resolves_like_one_without():
    theme = branded(with_dark(tagline='x'))
    assert check_theme(theme)['errors'] == [] and validate_theme(theme) == theme
    resolved = resolve_theme(theme)
    assert resolved['brand']['logo_dark'] == {'src': DARK_SRC, 'alt': 'Precision Hose (light on dark)', 'height': HEIGHT['default']}
    assert resolved['brand'] == brand_of(theme) and brand_logo_for(resolved['brand'], True) == resolved['brand']['logo_dark']
    for mode in ('light', 'dark'):
        dual = branded(with_dark(), color_scheme='auto', modes={'dark': themes.derive_dark(default_theme_v2())})
        assert resolve_theme(dual, mode)['brand'] == resolve_theme(branded(with_dark()))['brand']  # both palettes carry both logos


def test_the_brand_logo_doc_names_logo_dark_and_its_helper():
    doc = (ROOT / 'docs/brand-logo.md').read_text()
    assert '`logo_dark`' in doc and 'brand_logo_for' in doc and 'brandLogoFor' in doc and 'logo_dark needs a logo' in doc


# --- src ------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('src,message', [
    ('http://example.com/logo.png', "Must be a data: URI (data:image/png;base64,...); a theme's images are never fetched"),
    ('https://example.com/logo.png', "Must be a data: URI (data:image/png;base64,...); a theme's images are never fetched"),
    ('/static/logo.png', "Must be a data: URI (data:image/png;base64,...); a theme's images are never fetched"),
    ('logo.png', "Must be a data: URI (data:image/png;base64,...); a theme's images are never fetched"),
    ('blob:https://x/1234', "Must be a data: URI (data:image/png;base64,...); a theme's images are never fetched"),
    ('file:///etc/passwd', "Must be a data: URI (data:image/png;base64,...); a theme's images are never fetched"),
    ('javascript:alert(1)', "Must be a data: URI (data:image/png;base64,...); a theme's images are never fetched"),
    ('DATA:image/png;base64,' + base64.b64encode(png()).decode(), "Must be a data: URI (data:image/png;base64,...); a theme's images are never fetched"),
    ('', "Must be a data: URI (data:image/png;base64,...); a theme's images are never fetched"),
    ('data:image/png;base64', 'Malformed data URI: expected data:<type>;base64,<payload>'),
    ('data:image/png,abc', 'The data URI must be base64: data:<type>;base64,<payload>'),
    ('data:image/png;charset=utf-8,abc', 'The data URI must be base64: data:<type>;base64,<payload>'),
    ('data:image/gif;base64,R0lGODlhAQABAAAAACw=', 'Type must be one of ' + ', '.join(LIMITS['types'])),
    ('data:text/html;base64,PGh0bWw+', 'Type must be one of ' + ', '.join(LIMITS['types'])),
    ('data:IMAGE/PNG;base64,' + base64.b64encode(png()).decode(), 'Type must be one of ' + ', '.join(LIMITS['types'])),
    ('data:;base64,' + base64.b64encode(png()).decode(), 'Type must be one of ' + ', '.join(LIMITS['types'])),
    ('data:image/png;base64,iVBORw0KGgo', 'The payload is not valid base64'),            # length not a multiple of 4
    ('data:image/png;base64,iVBORw0K Ggo=', 'The payload is not valid base64'),           # a space
    ('data:image/png;base64,iVBO\nRw0K', 'The payload is not valid base64'),              # a newline
    ('data:image/png;base64,iVBO-w0K', 'The payload is not valid base64'),                # url-safe alphabet
    ('data:image/png;base64,iV=O', 'The payload is not valid base64'),                    # padding in the middle
    ('data:image/png;base64,iVBO====', 'The payload is not valid base64'),                # too much padding
    ('data:image/png;base64,iVBé', 'The payload is not valid base64'),
    ('data:image/png;base64,', 'The image is empty'),
])
def test_a_src_that_is_not_a_base64_data_uri_of_an_allowed_type_is_rejected_at_src(src, message):
    assert only({'logo': {'src': src, 'alt': 'x'}}) == ('brand.logo.src', message)
    assert only({'mark': {'src': src, 'alt': 'x'}}) == ('brand.mark.src', message)


def test_a_src_that_is_not_text_is_rejected():
    for junk in (None, 3, [], {}, True):
        assert only({'logo': {'src': junk, 'alt': 'x'}}) == ('brand.logo.src', 'Must be a data: URI string')


def test_the_payload_must_match_its_declared_type_by_its_magic_bytes():
    cases = {
        'image/png': ([JPEG_MAGIC + b'\x00' * 8, b'\x89PNG\r\n\x1a' + b'\x00' * 8, b'GIF89a' + b'\x00' * 8, b'<svg/>'], 'PNG'),
        'image/jpeg': ([PNG_MAGIC + b'\x00' * 8, b'\xff\xd8' + b'\x00' * 8, b'\xd8\xff\xe0' + b'\x00' * 8], 'JPEG'),
        'image/webp': ([PNG_MAGIC + b'\x00' * 8, b'RIFF\x04\x00\x00\x00WAVE', b'RIFF\x04\x00\x00\x00WEB', b'riff\x04\x00\x00\x00webp', b'WEBP\x04\x00\x00\x00RIFF'], 'WebP'),
    }
    for mime, (payloads, label) in cases.items():
        for data in payloads:
            assert only({'logo': logo(src=uri(data, mime))}) == ('brand.logo.src', f'The data is not a {label} image (wrong file signature)'), (mime, data)
    assert only({'logo': logo(src=uri(b'RIFF', 'image/webp'))})[1] == 'The data is not a WebP image (wrong file signature)'  # shorter than the header
    assert only({'logo': logo(src=uri(b'\x89', 'image/png'))})[1] == 'The data is not a PNG image (wrong file signature)'


def test_a_non_canonical_but_well_formed_base64_payload_is_accepted():
    # The trailing bits of the last character are ignored by every decoder: 'QR==' is one byte, 0x41.
    assert only({'logo': logo(src='data:image/png;base64,QR==')}) == ('brand.logo.src', 'The data is not a PNG image (wrong file signature)')


# --- Sizes (from the vocabulary) ------------------------------------------------------------------------------------------

def test_an_image_of_exactly_the_limit_is_valid_and_one_byte_more_is_not():
    assert verdict({'logo': logo(src=uri(png(IMAGE_MAX)))}) == []
    assert only({'logo': logo(src=uri(png(IMAGE_MAX + 1)))}) == ('brand.logo.src', f'The image is {IMAGE_MAX + 1} bytes; at most {IMAGE_MAX // 1024} KiB')
    assert only({'mark': {'src': uri(png(IMAGE_MAX + 1)), 'alt': 'x'}})[0] == 'brand.mark.src'
    assert only({'logo': logo(src=svg_uri(SVG + ' ' * (IMAGE_MAX - len(SVG) + 1)))})[1].startswith(f'The image is {IMAGE_MAX + 1} bytes')


def test_the_images_of_a_brand_may_add_up_to_exactly_the_total_and_not_a_byte_more():
    assert IMAGE_MAX < TOTAL_MAX < 2 * IMAGE_MAX  # the spec's shape: two big images do not fit
    rest = TOTAL_MAX - IMAGE_MAX
    assert verdict({'logo': logo(src=uri(png(IMAGE_MAX))), 'mark': {'src': uri(png(rest)), 'alt': 'm'}}) == []
    assert only({'logo': logo(src=uri(png(IMAGE_MAX))), 'mark': {'src': uri(png(rest + 1)), 'alt': 'm'}}) == (
        'brand', f'The images of a brand add up to {TOTAL_MAX + 1} bytes; at most {TOTAL_MAX // 1024} KiB')
    assert only({'logo': logo(src=uri(png(IMAGE_MAX))), 'mark': {'src': uri(png(IMAGE_MAX)), 'alt': 'm'}})[0] == 'brand'


def test_an_oversize_image_is_not_also_counted_in_the_total_and_a_broken_one_is_not_counted_at_all():
    assert [e['path'] for e in verdict({'logo': logo(src=uri(png(IMAGE_MAX + 1))), 'mark': {'src': uri(png(IMAGE_MAX)), 'alt': 'm'}})] == ['brand.logo.src']
    broken = uri(JPEG_MAGIC + b'\x00' * (IMAGE_MAX - 4))
    assert [e['path'] for e in verdict({'logo': logo(src=broken), 'mark': {'src': uri(png(IMAGE_MAX)), 'alt': 'm'}})] == ['brand.logo.src']


def test_every_limit_comes_from_the_vocabulary():
    vocab = copy.deepcopy(VOCAB)
    limits = vocab['brand']['logo_limits']
    limits.update(max_image_bytes=100, max_total_bytes=150, alt_max=5, tagline_max=6, types=['image/png', 'image/svg+xml'])
    limits['height'].update(min=20, max=30)
    assert verdict({'logo': logo(src=uri(png(100)), alt='12345', height=30), 'tagline': '123456'}, vocab) == []
    assert only({'logo': logo(src=uri(png(101)), alt='ab')}, vocab) == ('brand.logo.src', 'The image is 101 bytes; at most 100 bytes')
    assert only({'logo': logo(src=uri(png(100)), alt='ab'), 'mark': {'src': uri(png(51)), 'alt': 'm'}}, vocab) == (
        'brand', 'The images of a brand add up to 151 bytes; at most 150 bytes')
    assert only({'logo': logo(alt='123456')}, vocab) == ('brand.logo.alt', 'Must be 1 to 5 characters')
    assert only({'tagline': '1234567'}, vocab) == ('brand.tagline', 'Must be 1 to 6 characters')
    assert only({'logo': logo(height=19, alt='ab')}, vocab) == ('brand.logo.height', 'Must be a whole number 20-30')
    assert only({'logo': logo(src=uri(JPEG_MAGIC + b'\x00' * 8, 'image/jpeg'), alt='ab')}, vocab) == ('brand.logo.src', 'Type must be one of image/png, image/svg+xml')
    # and the built-in limits are untouched
    assert verdict({'logo': logo(alt='123456')}) == []


def test_a_vocabulary_that_predates_the_brand_falls_back_to_the_built_in_limits():
    vocab = {key: value for key, value in VOCAB.items() if key != 'brand'}
    assert verdict(good(), vocab) == []
    assert normalise_brand({'logo': logo()}, vocab)['logo']['height'] == HEIGHT['default']
    assert only({'logo': logo(alt='x' * (ALT_MAX + 1))}, vocab)[0] == 'brand.logo.alt'


def test_the_limits_are_not_written_in_the_code():
    import re
    numbers = re.compile(r'(?<![0-9A-Za-z\\])(%s)(?![0-9A-Za-z])' % '|'.join(map(str, (IMAGE_MAX, TOTAL_MAX, IMAGE_MAX // 1024, TOTAL_MAX // 1024,
                                                                                        ALT_MAX, TAGLINE_MAX, HEIGHT['max']))))  # 16 and 32 are a hex radix and the ASCII case offset here
    source = (ROOT / 'fastlanelabs_sdk/themes.py').read_text()
    brand = source[source.index('# --- The brand (logo)'):source.index('def _check_layout(')]
    ts = (ROOT / 'frontend/theme-resolve.ts').read_text()
    ts_brand = ts[ts.index('// --- The brand (logo)'):ts.index('const luminance = ')]
    for text in (brand, ts_brand):
        assert numbers.findall(text) == [], numbers.findall(text)


# --- alt, height, tagline -------------------------------------------------------------------------------------------------

def test_alt_is_one_to_the_limit_characters_without_control_characters():
    assert verdict({'logo': logo(alt='x' * ALT_MAX)}) == []
    assert verdict({'logo': logo(alt='é' * ALT_MAX)}) == []
    assert verdict({'logo': logo(alt='\U0001f600' * ALT_MAX)}) == []  # characters, not UTF-16 units or bytes
    assert only({'logo': logo(alt='\U0001f600' * (ALT_MAX + 1))}) == ('brand.logo.alt', f'Must be 1 to {ALT_MAX} characters')
    assert only({'logo': logo(alt='x' * (ALT_MAX + 1))}) == ('brand.logo.alt', f'Must be 1 to {ALT_MAX} characters')
    assert only({'logo': logo(alt='')}) == ('brand.logo.alt', f'Must be 1 to {ALT_MAX} characters')
    assert only({'logo': logo(alt='   ')}) == ('brand.logo.alt', f'Must be 1 to {ALT_MAX} characters')  # trimmed first
    assert verdict({'logo': logo(alt=' ' + 'x' * ALT_MAX + ' ')}) == []  # the limit is on the trimmed text
    assert only({'mark': {'src': uri(png()), 'alt': ''}}) == ('brand.mark.alt', f'Must be 1 to {ALT_MAX} characters')
    for junk in (None, 3, [], {}):
        assert only({'logo': logo(alt=junk)}) == ('brand.logo.alt', 'Must be text')


@pytest.mark.parametrize('bad', ['a\x00b', 'a\nb', 'a\tb', 'a\rb', 'a\x1fb', 'a\x7fb', 'a' + chr(0x85) + 'b', 'a' + chr(0x9f) + 'b',
                                 'a' + chr(0x2028) + 'b', 'a' + chr(0x2029) + 'b', 'a' + chr(0x202e) + 'b', 'a' + chr(0x2066) + 'b'])
def test_control_characters_are_rejected_in_alt_and_tagline(bad):
    assert only({'logo': logo(alt=bad)}) == ('brand.logo.alt', 'Must not contain control characters')
    assert only({'tagline': bad}) == ('brand.tagline', 'Must not contain control characters')
    assert only({'mark': {'src': uri(png()), 'alt': bad}}) == ('brand.mark.alt', 'Must not contain control characters')


def test_height_is_a_whole_number_in_the_vocabulary_range():
    for good_height in (HEIGHT['min'], HEIGHT['default'], HEIGHT['max']):
        assert verdict({'logo': logo(height=good_height)}) == []
    for bad in (HEIGHT['min'] - 1, HEIGHT['max'] + 1, 0, -1, 36.5, '36', None, True, [], 1e9):
        assert only({'logo': logo(height=bad)}) == ('brand.logo.height', f"Must be a whole number {HEIGHT['min']}-{HEIGHT['max']}"), bad


def test_tagline_is_one_to_the_limit_characters():
    assert verdict({'tagline': 'x' * TAGLINE_MAX}) == []
    assert only({'tagline': 'x' * (TAGLINE_MAX + 1)}) == ('brand.tagline', f'Must be 1 to {TAGLINE_MAX} characters')
    assert only({'tagline': ' '}) == ('brand.tagline', f'Must be 1 to {TAGLINE_MAX} characters')
    for junk in (None, 3, []):
        assert only({'tagline': junk}) == ('brand.tagline', 'Must be text')


# --- The SVG safety scan --------------------------------------------------------------------------------------------------

def svg(inner='', head='<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 10 10"', tail='</svg>'):
    return f'{head}>{inner}{tail}'


@pytest.mark.parametrize('text', [
    SVG,
    '<?xml version="1.0" encoding="UTF-8"?>\n<!-- made by hand -->\n' + SVG + '\n',
    '\n  <?xml version="1.0"?><!-- a --><!-- b -->' + SVG + '<!-- trailing -->\n',
    '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">' + SVG,
    '<svg xmlns="http://www.w3.org/2000/svg"/>',
    svg('<defs><linearGradient id="a"><stop offset="0" stop-color="#fff"/></linearGradient></defs><rect fill="url(#a)" width="4" height="4"/>'),
    svg('<use href="#a"/><use xlink:href="#a"/><g id="a"><circle r="2"/></g>'),
    svg('<style>.a{fill:#336}</style><text data-icon="x" font-family="Inter, sans-serif">Hose</text>'),
    svg('<title>on and onion are text</title><rect class="one" width="1" height="1"/>'),
    svg('<rect data-ok="x" width="1"/>'),
    svg('<a xlink:href="#top"><rect width="1" height="1"/></a>'),
    svg('<rect fill="url(#g)" style="stroke:url(#g)" width="1" height="1"/>'),
    svg('<text>javascript: is only text here</text>'),
    svg('<rect title="metadata: none" width="1" height="1"/>'),                  # data: must not be the end of a longer word
    svg('<rect title="&amp;#106;avascript:alert(1)" width="1" height="1"/>'),    # decoded once, it is the text &#106;avascript:
    '<svg xmlns="http://www.w3.org/2000/svg"\n   viewBox="0 0 10 10"\n>\n<rect/>\n</svg>',
])
def test_a_safe_svg_is_accepted(text):
    assert verdict(with_svg(text)) == []


def svg_message(text):
    return [e['message'] for e in verdict(with_svg(text))]


@pytest.mark.parametrize('text,messages', [
    (svg('<script>alert(1)</script>'), ['An SVG must not contain <script>']),
    (svg('<SCRIPT>alert(1)</SCRIPT>'), ['An SVG must not contain <script>']),
    (svg('<svg:script>alert(1)</svg:script>'), ['An SVG must not contain <script>']),
    (svg('<script/>'), ['An SVG must not contain <script>']),
    (svg('<foreignObject><div>hi</div></foreignObject>'), ['An SVG must not contain <foreignObject>']),
    (svg('<FOREIGNOBJECT/>'), ['An SVG must not contain <foreignObject>']),
    (svg('<iframe src="x"/>'), ['An SVG must not contain <iframe>', ]),
    (svg('<IFrame/>'), ['An SVG must not contain <iframe>']),
    (svg('<image href="#a" width="1" height="1"/>'), ['An SVG must not contain <image>']),
    (svg('<Image/>'), ['An SVG must not contain <image>']),
    (svg('<use href="https://example.com/a.svg#b"/>'), ['An SVG <use> may only point at an element in the same file (an href starting with #)',
                                                         'An SVG must not load external or data: URLs (http:, https: or data:)']),
    (svg('<use xlink:href="a.svg#b"/>'), ['An SVG <use> may only point at an element in the same file (an href starting with #)']),
    (svg('<USE HREF="a.svg#b"/>'), ['An SVG <use> may only point at an element in the same file (an href starting with #)']),
    (svg("<use xlink:href='x.svg'/>"), ['An SVG <use> may only point at an element in the same file (an href starting with #)']),
    (svg('<use href="&#35;ok"/>'), []),   # &#35; is #: entity-decoded before the check
    (svg('<use href="&#104;ttp://x/a.svg"/>'), ['An SVG <use> may only point at an element in the same file (an href starting with #)',
                                                  'An SVG must not load external or data: URLs (http:, https: or data:)']),
    (svg('<rect onclick="alert(1)"/>'), ['An SVG must not have event attributes (on*=)']),
    (svg('<rect ONCLICK="x"/>'), ['An SVG must not have event attributes (on*=)']),
    (svg('<rect OnMouseOver = "x"/>'), ['An SVG must not have event attributes (on*=)']),
    (svg("<rect onload='x'/>"), ['An SVG must not have event attributes (on*=)']),
    (svg('<rect xlink:onclick="x"/>'), ['An SVG must not have event attributes (on*=)']),
    (svg('<rect fill="red"onclick="x"/>'), ['An SVG must not have event attributes (on*=)']),
    ('<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>', ['An SVG must not have event attributes (on*=)']),
    (svg('<a href="javascript:alert(1)"><rect/></a>'), ['An SVG must not contain javascript: URLs']),
    (svg('<a href="JavaScript:alert(1)"><rect/></a>'), ['An SVG must not contain javascript: URLs']),
    (svg('<a href="java&#115;cript:alert(1)"><rect/></a>'), ['An SVG must not contain javascript: URLs']),
    (svg('<a href="&#x6A;avascript:alert(1)"><rect/></a>'), ['An SVG must not contain javascript: URLs']),
    (svg('<a href="&#106;&#97;vascript&colon;x"><rect/></a>'), []),          # &colon; is not an XML entity: no scheme
    (svg('<a href="java&#9;script:alert(1)"><rect/></a>'), ['An SVG must not contain javascript: URLs']),
    (svg('<a href="  javascript:alert(1)"><rect/></a>'), ['An SVG must not contain javascript: URLs']),
    (svg('<a xlink:href="javascript:alert(1)"><rect/></a>'), ['An SVG must not contain javascript: URLs']),
    (svg('<rect style="fill:url(javascript:x)"/>'), ['An SVG must not contain javascript: URLs']),
    (svg('<rect fill="url(data:image/png;base64,AAAA)"/>'), ['An SVG must not load external or data: URLs (http:, https: or data:)']),
    (svg('<a href="data:text/html;base64,PGI+"><rect/></a>'), ['An SVG must not load external or data: URLs (http:, https: or data:)']),
    (svg('<a href="http://example.com"><rect/></a>'), ['An SVG must not load external or data: URLs (http:, https: or data:)']),
    (svg('<a href="HTTPS://example.com"><rect/></a>'), ['An SVG must not load external or data: URLs (http:, https: or data:)']),
    (svg('<a href="&#104;ttps://example.com"><rect/></a>'), ['An SVG must not load external or data: URLs (http:, https: or data:)']),
    (svg('<style>.a{fill:url(https://example.com/a.svg#b)}</style>'), ['An SVG must not load external or data: URLs (http:, https: or data:)']),
    (svg("<style>.a{background:URL( 'data:image/png;base64,AAAA' )}</style>"), ['An SVG must not load external or data: URLs (http:, https: or data:)']),
    (svg('<style>@import url(x.css);</style>'), ['An SVG must not use @import']),
    (svg('<style>@IMPORT "x.css";</style>'), ['An SVG must not use @import']),
    ('<!DOCTYPE svg [ <!ENTITY a "b"> ]>' + SVG, ['An SVG must not declare entities (<!ENTITY)', 'An SVG must not have a DOCTYPE with an internal subset']),
    ('<!doctype svg [ ]>' + SVG, ['An SVG must not have a DOCTYPE with an internal subset']),
    (svg('<!ENTITY a "b">'), ['An SVG must not declare entities (<!ENTITY)']),
    (svg('<!entity a "b">'), ['An SVG must not declare entities (<!ENTITY)']),
    (svg('<title>onload="x"</title>'), ['An SVG must not have event attributes (on*=)']),   # conservative: it reads text that looks like an attribute
    (svg('<script>1</script><image/><rect onload="x"/>'), ['An SVG must not contain <script>', 'An SVG must not contain <image>',
                                                        'An SVG must not have event attributes (on*=)']),
])
def test_each_forbidden_svg_construct_is_reported_once_in_a_fixed_order(text, messages):
    assert svg_message(text) == messages


def test_svg_errors_carry_the_path_of_the_src():
    assert only(with_svg(svg('<script/>'))) == ('brand.logo.src', 'An SVG must not contain <script>')
    assert only({'mark': {'src': svg_uri(svg('<script/>')), 'alt': 'm'}}) == ('brand.mark.src', 'An SVG must not contain <script>')


@pytest.mark.parametrize('text,message', [
    ('<html><body/></html>', 'An SVG must start at <svg (an XML prolog and comments may come before it)'),
    ('hello', 'An SVG must start at <svg (an XML prolog and comments may come before it)'),
    ('<SVG xmlns="http://www.w3.org/2000/svg"></SVG>', 'An SVG must start at <svg (an XML prolog and comments may come before it)'),
    ('<svgfoo></svgfoo>', 'An SVG must start at <svg (an XML prolog and comments may come before it)'),
    ('<svg', 'An SVG must start at <svg (an XML prolog and comments may come before it)'),
    ('<!-- never closed ' + SVG, 'An SVG must start at <svg (an XML prolog and comments may come before it)'),
    ('<?xml version="1.0"' + SVG, 'An SVG must start at <svg (an XML prolog and comments may come before it)'),
    (chr(0xfeff) + SVG, 'An SVG must start at <svg (an XML prolog and comments may come before it)'),
    ('<p/>' + SVG, 'An SVG must start at <svg (an XML prolog and comments may come before it)'),
])
def test_an_svg_must_start_at_svg(text, message):
    assert message in svg_message(text)


def test_an_svg_must_be_well_formed_utf8_text():
    assert 'An SVG must be well-formed: it must end with </svg>' in svg_message('<svg xmlns="http://www.w3.org/2000/svg"><rect/>')
    assert 'An SVG must be well-formed: it must end with </svg>' in svg_message(SVG + ' <p>')
    assert 'An SVG must be well-formed text, with no control characters' in svg_message(SVG.replace('<rect', '<rect\x00'))
    assert 'An SVG must be well-formed text, with no control characters' in svg_message(SVG.replace('<rect', '<rect\x08'))
    assert svg_message(SVG.replace('<rect', '<rect\t').replace('<rect\t', '<rect\n')) == []
    for data in (b'\xff\xfe<\x00s\x00v\x00g\x00>\x00', SVG.encode() + b'\xc3', b'\xc0\xaf' + SVG.encode()):
        assert only({'logo': logo(src=svg_uri(data))}) == ('brand.logo.src', 'An SVG must be UTF-8 text')
    assert verdict({'logo': logo(src=svg_uri(SVG.replace('#336', 'é中\U0001f600')))}) == []


# --- The theme ------------------------------------------------------------------------------------------------------------

def branded(brand=None, **top):
    theme = default_theme_v2('client-precision', '1.0.0', 'Precision Hose')
    theme['brand'] = good() if brand is None else brand
    theme.update(top)
    return theme


def test_a_theme_may_carry_a_brand_and_it_is_returned_as_is():
    theme = branded()
    assert theme['registry_revision'] == 4
    assert check_theme(theme)['errors'] == [] and check_theme(theme)['warnings'] == []
    assert validate_theme(theme) == theme
    without = copy.deepcopy(theme)
    del without['brand']
    assert check_theme(theme)['contrast'] == check_theme(without)['contrast']  # the contrast checker does not look at the brand


def test_theme_problems_in_the_brand_carry_their_paths():
    theme = branded({'logo': logo(src='http://x/y.png', height=3), 'tagline': ''})
    errors = check_theme(theme)['errors']
    assert [(e['path'], e['message']) for e in errors] == [
        ('brand.logo.src', "Must be a data: URI (data:image/png;base64,...); a theme's images are never fetched"),
        ('brand.logo.height', 'Must be a whole number 16-64'),
        ('brand.tagline', 'Must be 1 to 80 characters')]
    with pytest.raises(ThemeError) as caught:
        validate_theme(theme)
    assert caught.value.path == 'brand.logo.src'
    assert len(caught.value.errors) == 3


def test_the_top_level_keys_of_a_theme_gain_an_optional_brand():
    assert 'brand' not in registry.TOP_LEVEL_KEYS and registry.OPTIONAL_TOP_LEVEL_KEYS == ('modes', 'brand')
    theme = branded()
    theme['extra'] = 1
    assert check_theme(theme)['errors'][0] == {'path': '', 'message': 'Theme must contain only ' + ', '.join(registry.TOP_LEVEL_KEYS)}
    plain = default_theme_v2()
    assert 'brand' not in plain and check_theme(plain)['errors'] == []


def test_a_brand_theme_with_a_dark_palette_validates_too():
    theme = branded(color_scheme='auto', modes={'dark': themes.derive_dark(default_theme_v2())})
    assert check_theme(theme)['errors'] == []
    assert resolve_theme(theme, 'dark')['brand'] == resolve_theme(theme)['brand']  # a logo is drawn as is


def test_resolve_theme_returns_the_normalised_brand_next_to_the_shell():
    theme = branded({'logo': logo(alt=' Precision Hose '), 'tagline': ' Hose '})
    resolved = resolve_theme(theme)
    assert resolved['brand'] == {'logo': {'src': theme['brand']['logo']['src'], 'alt': 'Precision Hose', 'height': HEIGHT['default']},
                                 'logo_dark': None, 'mark': None, 'tagline': 'Hose'}
    assert resolved['brand'] == brand_of(theme) == normalise_brand(theme['brand'])
    assert list(resolved)[:5] == ['api_version', 'vars', 'attrs', 'layout', 'shell'] and 'brand' in resolved
    assert resolve_theme(branded(good()))['brand']['logo']['height'] == 36
    plain = resolve_theme(default_theme_v2())
    assert plain['brand'] is None


def test_a_brand_changes_nothing_but_the_brand_in_the_resolved_theme():
    plain = default_theme_v2('client-precision', '1.0.0', 'Precision Hose')
    for mode in (None, 'dark'):
        with_brand = resolve_theme(branded(), mode)
        assert dict(with_brand, brand=None) == resolve_theme(plain, mode)


def test_validate_theme_never_rewrites_the_brand():
    theme = branded({'logo': logo(alt='  padded  ')})
    assert validate_theme(theme)['brand']['logo'] == {'src': theme['brand']['logo']['src'], 'alt': '  padded  '}  # normalise_brand trims, validation does not


# --- The registry additions that came with the brand ----------------------------------------------------------------------

def token(name):
    return registry.INDEX[name]


def test_nav_item_variant_offers_tab_and_page_header_variant_offers_panel():
    nav, header = token('nav-item-variant'), token('page-header-variant')
    assert nav.options == ('square', 'pill', 'tab') and nav.default == 'square'
    assert header.options == ('plain', 'ruled', 'panel') and header.default == 'plain'
    data = {t['name']: t for t in registry.registry_json()['tokens']}
    assert data['nav-item-variant']['options'] == ['square', 'pill', 'tab'] and data['page-header-variant']['options'] == ['plain', 'ruled', 'panel']


def test_a_theme_may_use_the_tab_and_panel_variants():
    for name, value in (('nav-item-variant', 'tab'), ('page-header-variant', 'panel')):
        theme = default_theme_v2()
        theme['tokens']['components'][name] = value
        assert check_theme(theme)['errors'] == [], name
        assert resolve_theme(theme)['enums'][name] == value
    theme = default_theme_v2()
    theme['tokens']['components']['nav-item-variant'] = 'bar'
    assert check_theme(theme)['errors'][0]['message'] == 'Invalid value: must be one of square, pill, tab'


GATE_NEW = {'gate-shadow': ('shadow', '{shadow-sm}'), 'gate-title-fg': ('color', '{ink-900}'), 'gate-tagline-fg': ('color', '{ink-600}')}


def test_the_sign_in_card_already_had_its_page_background_card_background_border_and_radius():
    existing = {name: (token(name).type, token(name).default) for name in
                ('gate-page-bg', 'gate-bg', 'gate-border', 'gate-radius', 'gate-max-width', 'gate-title-size')}
    assert existing == {'gate-page-bg': ('color', '{surface-page}'), 'gate-bg': ('color', '{surface}'), 'gate-border': ('color', '{border}'),
                        'gate-radius': ('length', '{radius}*2'), 'gate-max-width': ('length', '416px'),
                        'gate-title-size': ('font-size', '{size-2xl}')}


def test_the_new_gate_tokens_are_components_whose_fallbacks_are_what_the_page_drew_before():
    for name, (kind, fallback) in GATE_NEW.items():
        t = token(name)
        assert (t.layer, t.type, t.default, t.component, t.optional) == ('component', kind, fallback, 'gate', False), name
    # text-ink-900 heading, text-ink-600 lede and tagline, shadow-sm card (the markup of Gate in core's Field.tsx)
    css = (ROOT / 'frontend/theme-defaults.css').read_text()
    assert '--fl-gate-shadow: var(--fl-shadow-sm);' in css
    assert '--fl-gate-title-fg: var(--fl-ink-900);' in css and '--fl-gate-tagline-fg: var(--fl-ink-600);' in css


def test_a_theme_may_set_the_new_gate_tokens_and_a_theme_without_them_stays_valid():
    values = {'gate-shadow': '0 8px 24px 0 rgba(0,0,0,0.12)', 'gate-title-fg': '#1a1b21', 'gate-tagline-fg': '{ink-500}'}
    theme = default_theme_v2()
    theme['tokens']['components'].update(values)
    assert check_theme(theme)['errors'] == []
    assert resolve_theme(theme)['vars']['--fl-gate-title-fg'] == '26 27 33'
    assert resolve_theme(theme)['vars']['--fl-gate-shadow'] == values['gate-shadow']
    assert check_theme(default_theme_v2())['errors'] == []


def test_the_new_gate_tokens_follow_the_naming_and_layer_conventions_and_reach_every_generated_file():
    for name in GATE_NEW:
        assert name.startswith('gate-') and token(name).group == 'component.gate'
    tokens_doc = (ROOT / 'docs/theme-v2-tokens.md').read_text()
    assert '| `gate-shadow` | shadow | `{shadow-sm}` |' in tokens_doc
    assert '| `gate-title-fg` | color | `{ink-900}` |' in tokens_doc
    frontend = {t['name']: t for t in json.loads((ROOT / 'frontend/theme-registry.json').read_text())['tokens']}
    assert all(name in frontend for name in GATE_NEW)
    assert json.loads((ROOT / 'frontend/theme-registry.json').read_text())['brand'] == {'vocabulary': 'layout-vocabulary.json'}
    assert json.loads((ROOT / 'frontend/theme-registry.json').read_text())['optional_top_level_keys'] == ['modes', 'brand']


# --- Cases the TypeScript twin is run over (tests/test_layout_tree_parity.py) ---------------------------------------------

def tweak(change):
    vocab = copy.deepcopy(VOCAB)
    change(vocab)
    return vocab


def named_cases():
    """(id, brand, vocabulary): every rule above, valid and invalid, and the same text-level corner cases as the SVG scan."""
    full = good()
    cases = [
        ('valid-all', full, None), ('valid-logo', {'logo': logo()}, None), ('valid-logo-height-min', {'logo': logo(height=HEIGHT['min'])}, None),
        ('valid-logo-height-max', {'logo': logo(height=HEIGHT['max'])}, None), ('valid-mark', {'mark': full['mark']}, None),
        ('valid-tagline', {'tagline': 'Hose'}, None), ('valid-logo-tagline', {'logo': logo(), 'tagline': ' padded tagline '}, None),
        ('valid-alt-padded', {'logo': logo(alt='  Precision Hose 　')}, None),
        ('valid-alt-emoji', {'logo': logo(alt='\U0001f600' * ALT_MAX)}, None), ('valid-alt-max', {'logo': logo(alt='x' * ALT_MAX)}, None),
        ('valid-tagline-max', {'tagline': 'é' * TAGLINE_MAX}, None),
        ('valid-webp', {'logo': logo(src=uri(WEBP_MAGIC + b'VP8 ', 'image/webp'))}, None),
        ('valid-jpeg', {'logo': logo(src=uri(JPEG_MAGIC + b'\x00' * 4, 'image/jpeg'))}, None),
        ('valid-svg', with_svg(SVG), None),
        ('valid-image-max', {'logo': logo(src=uri(png(IMAGE_MAX)))}, None),
        ('valid-total-max', {'logo': logo(src=uri(png(IMAGE_MAX))), 'mark': {'src': uri(png(TOTAL_MAX - IMAGE_MAX)), 'alt': 'm'}}, None),
        ('invalid-image-oversize', {'logo': logo(src=uri(png(IMAGE_MAX + 1)))}, None),
        ('invalid-total-oversize', {'logo': logo(src=uri(png(IMAGE_MAX))), 'mark': {'src': uri(png(TOTAL_MAX - IMAGE_MAX + 1)), 'alt': 'm'}}, None),
        ('invalid-total-two-big', {'logo': logo(src=uri(png(IMAGE_MAX))), 'mark': {'src': uri(png(IMAGE_MAX)), 'alt': 'm'}}, None),
        ('invalid-not-object', None, None), ('invalid-list', [], None), ('invalid-string', 'logo', None), ('invalid-empty', {}, None),
        ('invalid-unknown-keys', {'zzz': 1, 'aaa': 2, 'logo': dict(logo(), zoom=1, color=2), 'mark': dict(logo(), height=30)}, None),
        ('invalid-logo-string', {'logo': 'x'}, None), ('invalid-mark-list', {'mark': []}, None),
        ('invalid-missing-src-alt', {'logo': {}, 'mark': {}}, None),
        ('invalid-scheme-http', {'logo': logo(src='http://example.com/a.png')}, None),
        ('invalid-scheme-relative', {'logo': logo(src='/a.png')}, None), ('invalid-scheme-blob', {'logo': logo(src='blob:x')}, None),
        ('invalid-scheme-upper', {'logo': logo(src='DATA:image/png;base64,AAAA')}, None),
        ('invalid-src-types', {'logo': logo(src=None), 'mark': {'src': 3, 'alt': 'm'}}, None),
        ('invalid-no-comma', {'logo': logo(src='data:image/png;base64')}, None), ('invalid-not-base64', {'logo': logo(src='data:image/png,abc')}, None),
        ('invalid-mime-gif', {'logo': logo(src='data:image/gif;base64,AAAA')}, None),
        ('invalid-mime-upper', {'logo': logo(src='data:IMAGE/PNG;base64,AAAA')}, None),
        ('invalid-mime-html', {'logo': logo(src='data:text/html;base64,AAAA')}, None),
        ('invalid-b64-length', {'logo': logo(src='data:image/png;base64,iVBORw0KGgo')}, None),
        ('invalid-b64-space', {'logo': logo(src='data:image/png;base64,iVBO Rw0K')}, None),
        ('invalid-b64-newline', {'logo': logo(src='data:image/png;base64,iVBO\nRw0K')}, None),
        ('invalid-b64-urlsafe', {'logo': logo(src='data:image/png;base64,iVBO-w0K')}, None),
        ('invalid-b64-padding-mid', {'logo': logo(src='data:image/png;base64,iV=O')}, None),
        ('invalid-b64-padding-many', {'logo': logo(src='data:image/png;base64,iVBO====')}, None),
        ('invalid-b64-non-ascii', {'logo': logo(src='data:image/png;base64,iVBé')}, None),
        ('invalid-empty-payload', {'logo': logo(src='data:image/png;base64,')}, None),
        ('invalid-magic-png-as-jpeg', {'logo': logo(src=uri(png(), 'image/jpeg'))}, None),
        ('invalid-magic-jpeg-as-png', {'logo': logo(src=uri(JPEG_MAGIC + b'\x00' * 8))}, None),
        ('invalid-magic-webp', {'logo': logo(src=uri(b'RIFF\x04\x00\x00\x00WAVE', 'image/webp'))}, None),
        ('invalid-magic-webp-short', {'logo': logo(src=uri(b'RIFF', 'image/webp'))}, None),
        ('invalid-magic-png-short', {'logo': logo(src=uri(b'\x89PNG', 'image/png'))}, None),
        ('invalid-alt-empty', {'logo': logo(alt='')}, None), ('invalid-alt-blank', {'logo': logo(alt=' 　 ')}, None),
        ('invalid-alt-long', {'logo': logo(alt='x' * (ALT_MAX + 1))}, None), ('invalid-alt-emoji-long', {'logo': logo(alt='\U0001f600' * (ALT_MAX + 1))}, None),
        ('invalid-alt-type', {'logo': logo(alt=5), 'mark': {'src': uri(png()), 'alt': None}}, None),
        ('invalid-alt-nul', {'logo': logo(alt='a\x00b')}, None), ('invalid-alt-newline', {'logo': logo(alt='a\nb')}, None),
        ('invalid-alt-del', {'logo': logo(alt='a\x7fb')}, None), ('invalid-alt-c1', {'logo': logo(alt='a' + chr(0x85) + 'b')}, None),
        ('invalid-alt-ls', {'logo': logo(alt='a' + chr(0x2028) + 'b')}, None), ('invalid-alt-bidi', {'logo': logo(alt='a' + chr(0x202e) + 'b')}, None),
        ('invalid-height-low', {'logo': logo(height=HEIGHT['min'] - 1)}, None), ('invalid-height-high', {'logo': logo(height=HEIGHT['max'] + 1)}, None),
        ('invalid-height-float', {'logo': logo(height=36.5)}, None), ('invalid-height-string', {'logo': logo(height='36')}, None),
        ('invalid-height-bool', {'logo': logo(height=True)}, None), ('invalid-height-null', {'logo': logo(height=None)}, None),
        ('invalid-tagline-empty', {'tagline': ''}, None), ('invalid-tagline-long', {'tagline': 'x' * (TAGLINE_MAX + 1)}, None),
        ('invalid-tagline-type', {'tagline': 4}, None), ('invalid-tagline-control', {'tagline': 'a\tb'}, None),
        ('invalid-order', {'tagline': '', 'mark': {'src': 'x', 'alt': ''}, 'logo': {'src': 3, 'alt': 4, 'height': 5}}, None),
    ]
    scripts = {
        'script': svg('<script>alert(1)</script>'), 'script-upper': svg('<SCRIPT/>'), 'script-ns': svg('<svg:script/>'),
        'foreignobject': svg('<foreignObject/>'), 'foreignobject-upper': svg('<FOREIGNOBJECT/>'), 'iframe': svg('<iframe/>'), 'image': svg('<image/>'),
        'use-external': svg('<use href="https://x/a.svg#b"/>'), 'use-xlink': svg('<use xlink:href="a.svg#b"/>'),
        'use-internal': svg('<use href="#a"/>'), 'use-entity-hash': svg('<use href="&#35;a"/>'),
        'onload': '<svg xmlns="http://www.w3.org/2000/svg" onload="x"></svg>', 'onclick-upper': svg('<rect ONCLICK="x"/>'),
        'onclick-nospace': svg('<rect fill="red"onclick="x"/>'), 'onclick-ns': svg('<rect xlink:onclick="x"/>'), 'onclick-single': svg("<rect onload='x'/>"),
        'js-href': svg('<a href="javascript:x"/>'), 'js-upper': svg('<a href="JAVASCRIPT:x"/>'), 'js-entity': svg('<a href="java&#115;cript:x"/>'),
        'js-hex': svg('<a href="&#x6A;avascript:x"/>'), 'js-tab': svg('<a href="java&#9;script:x"/>'), 'js-space': svg('<a href=" javascript:x"/>'),
        'js-style': svg('<rect style="fill:url(javascript:x)"/>'), 'js-text-only': svg('<text>javascript:x</text>'),
        'js-double-encoded': svg('<rect title="&amp;#106;avascript:x"/>'), 'js-bad-entity': svg('<a href="&#xFFFFFFFF;javascript:x"/>'),
        'data-url': svg('<rect fill="url(data:image/png;base64,AAAA)"/>'), 'data-href': svg('<a href="data:text/html,x"/>'),
        'metadata-word': svg('<rect title="metadata: x"/>'), 'http-href': svg('<a href="http://x"/>'), 'https-upper': svg('<a href="HTTPS://x"/>'),
        'http-entity': svg('<a href="&#104;ttp://x"/>'), 'css-url-http': svg('<style>.a{fill:url(http://x/a)}</style>'),
        'css-url-data': svg("<style>.a{fill:URL( 'data:x' )}</style>"), 'import': svg('<style>@import url(a.css);</style>'),
        'import-upper': svg('<style>@IMPORT "a";</style>'), 'entity': '<!DOCTYPE svg [ <!ENTITY a "b"> ]>' + SVG,
        'doctype-subset': '<!doctype svg [ ]>' + SVG, 'doctype-plain': '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">' + SVG,
        'prolog': '<?xml version="1.0"?>\n<!-- c -->\n' + SVG + '\n<!-- d -->', 'prolog-unclosed': '<?xml version="1.0"' + SVG,
        'comment-unclosed': '<!-- ' + SVG, 'not-svg': '<html/>', 'svg-upper': '<SVG></SVG>', 'svgfoo': '<svgfoo/>', 'bare': '<svg',
        'no-end': '<svg xmlns="http://www.w3.org/2000/svg"><rect/>', 'trailing': SVG + '<p>', 'nul': SVG.replace('<rect', '<rect\x00'),
        'self-closed': '<svg xmlns="http://www.w3.org/2000/svg"/>', 'multi': 'x' + SVG, 'many': svg('<script/><image/><iframe/><rect onx="1" a="javascript:x" b="http://y"/>'),
        'xmlns-only': '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"></svg>',
        'xmlns-lookalike': '<svg xmlns:a="http://x" xmlnsb="http://x"></svg>',
    }
    cases += [(f'svg-{name}', with_svg(text), None) for name, text in scripts.items()]
    cases += [('svg-bom', with_svg(chr(0xfeff) + SVG), None), ('svg-bad-utf8', {'logo': logo(src=svg_uri(SVG.encode() + b'\xc3'))}, None),
              ('svg-utf16', {'logo': logo(src=svg_uri(b'\xff\xfe<\x00s\x00v\x00g\x00>\x00'))}, None),
              ('svg-unicode', with_svg(SVG.replace('#336', 'é中\U0001f600')), None),
              ('svg-mark', {'mark': {'src': svg_uri(svg('<script/>')), 'alt': 'm'}}, None),
              ('svg-oversize', {'logo': logo(src=svg_uri(SVG + ' ' * (IMAGE_MAX - len(SVG) + 1)))}, None)]
    cases += [
        ('vocab-small-limits', {'logo': logo(src=uri(png(101)), alt='123456'), 'tagline': '1234567'},
         tweak(lambda v: v['brand']['logo_limits'].update(max_image_bytes=100, alt_max=5, tagline_max=6))),
        ('vocab-small-limits-ok', {'logo': logo(src=uri(png(100)), alt='12345'), 'tagline': '123456'},
         tweak(lambda v: v['brand']['logo_limits'].update(max_image_bytes=100, alt_max=5, tagline_max=6))),
        ('vocab-total', {'logo': logo(src=uri(png(100))), 'mark': {'src': uri(png(51)), 'alt': 'm'}},
         tweak(lambda v: v['brand']['logo_limits'].update(max_image_bytes=100, max_total_bytes=150))),
        ('vocab-total-ok', {'logo': logo(src=uri(png(100))), 'mark': {'src': uri(png(50)), 'alt': 'm'}},
         tweak(lambda v: v['brand']['logo_limits'].update(max_image_bytes=100, max_total_bytes=150))),
        ('vocab-types', {'logo': logo(src=uri(JPEG_MAGIC + b'\x00' * 8, 'image/jpeg'))},
         tweak(lambda v: v['brand']['logo_limits'].update(types=['image/png', 'image/svg+xml']))),
        ('vocab-height', {'logo': logo(height=19)}, tweak(lambda v: v['brand']['logo_limits']['height'].update(min=20, max=30))),
        ('vocab-height-ok', {'logo': logo(height=30)}, tweak(lambda v: v['brand']['logo_limits']['height'].update(min=20, max=30))),
        ('vocab-default-height', {'logo': logo()}, tweak(lambda v: v['brand']['logo_limits']['height'].update(default=48))),
        ('vocab-without-brand', good(), {key: value for key, value in VOCAB.items() if key != 'brand'}),
    ]
    return cases


def logo_dark_cases():
    """(id, brand, vocabulary): the rules of `logo_dark` (the logo for dark backgrounds), valid and invalid, 40 and more."""
    base_logo = logo(height=36)
    pair = lambda **changes: {'logo': base_logo, 'logo_dark': dark(**changes)}  # noqa: E731
    bad_srcs = {
        'http': 'http://example.com/a.png', 'relative': '/a.png', 'blob': 'blob:x', 'upper': 'DATA:image/png;base64,AAAA', 'gif': 'data:image/gif;base64,AAAA',
        'no-comma': 'data:image/png;base64', 'not-base64': 'data:image/png,abc', 'b64-length': 'data:image/png;base64,iVBORw0KGgo',
        'b64-space': 'data:image/png;base64,iVBO Rw0K', 'empty-payload': 'data:image/png;base64,', 'type-int': 3, 'type-null': None,
        'magic-png-as-jpeg': uri(png(), 'image/jpeg'), 'magic-jpeg-as-png': uri(JPEG_MAGIC + b'\x00' * 8), 'magic-webp': uri(b'RIFF\x04\x00\x00\x00WAVE', 'image/webp'),
        'svg-script': svg_uri(svg('<script/>')), 'svg-onload': svg_uri('<svg xmlns="http://www.w3.org/2000/svg" onload="x"></svg>'),
        'svg-bad-utf8': svg_uri(SVG.encode() + b'\xc3'), 'svg-not-svg': svg_uri('<html/>'), 'svg-js-url': svg_uri(svg('<a href="javascript:x"/>')),
    }
    cases = [
        ('dark-valid', pair(), None), ('dark-valid-height', pair(height=24), None), ('dark-valid-height-min', pair(height=HEIGHT['min']), None),
        ('dark-valid-height-max', pair(height=HEIGHT['max']), None), ('dark-valid-svg', pair(src=svg_uri(SVG)), None),
        ('dark-valid-jpeg', pair(src=uri(JPEG_MAGIC + b'\x00' * 4, 'image/jpeg')), None),
        ('dark-valid-webp', pair(src=uri(WEBP_MAGIC + b'VP8 ', 'image/webp')), None),
        ('dark-valid-same-src-as-logo', {'logo': base_logo, 'logo_dark': dict(base_logo)}, None),
        ('dark-valid-alt-padded', pair(alt='  light on dark 　'), None), ('dark-valid-alt-max', pair(alt='x' * ALT_MAX), None),
        ('dark-valid-all-four', dict(good(), logo_dark=dark(height=20)), None),
        ('dark-valid-with-tagline', dict(pair(), tagline='Hose'), None), ('dark-valid-logo-default-height', {'logo': logo(), 'logo_dark': dark()}, None),
        ('dark-valid-total-max', {'logo': logo(src=uri(png(IMAGE_MAX))), 'logo_dark': dark(src=uri(png(TOTAL_MAX - IMAGE_MAX)))}, None),
        ('dark-no-logo', {'logo_dark': dark()}, None), ('dark-no-logo-with-mark', {'logo_dark': dark(), 'mark': {'src': uri(png()), 'alt': 'm'}}, None),
        ('dark-no-logo-with-tagline', {'logo_dark': dark(), 'tagline': 'x'}, None), ('dark-no-logo-bad-image', {'logo_dark': {'src': 3, 'alt': '', 'height': 1}}, None),
        ('dark-no-logo-not-object', {'logo_dark': 'x'}, None), ('dark-no-logo-null', {'logo_dark': None}, None),
        ('dark-not-object', {'logo': base_logo, 'logo_dark': 'x'}, None), ('dark-list', {'logo': base_logo, 'logo_dark': []}, None),
        ('dark-null', {'logo': base_logo, 'logo_dark': None}, None), ('dark-empty-object', {'logo': base_logo, 'logo_dark': {}}, None),
        ('dark-missing-src', {'logo': base_logo, 'logo_dark': {'alt': 'x'}}, None), ('dark-missing-alt', {'logo': base_logo, 'logo_dark': {'src': DARK_SRC}}, None),
        ('dark-unknown-keys', pair(zoom=2, colour='red'), None),
        ('dark-alt-empty', pair(alt=''), None), ('dark-alt-blank', pair(alt=' 　 '), None), ('dark-alt-long', pair(alt='x' * (ALT_MAX + 1)), None),
        ('dark-alt-control', pair(alt='a\x00b'), None), ('dark-alt-bidi', pair(alt='a' + chr(0x202e) + 'b'), None), ('dark-alt-type', pair(alt=5), None),
        ('dark-height-low', pair(height=HEIGHT['min'] - 1), None), ('dark-height-high', pair(height=HEIGHT['max'] + 1), None),
        ('dark-height-float', pair(height=20.5), None), ('dark-height-string', pair(height='20'), None), ('dark-height-bool', pair(height=True), None),
        ('dark-height-null', pair(height=None), None),
        ('dark-image-oversize', {'logo': base_logo, 'logo_dark': dark(src=uri(png(IMAGE_MAX + 1)))}, None),
        ('dark-total-oversize', {'logo': logo(src=uri(png(IMAGE_MAX))), 'logo_dark': dark(src=uri(png(TOTAL_MAX - IMAGE_MAX + 1)))}, None),
        ('dark-total-three-images', {'logo': logo(src=uri(png(IMAGE_MAX))), 'logo_dark': dark(src=uri(png(IMAGE_MAX // 2))),
                                     'mark': {'src': uri(png(IMAGE_MAX // 2)), 'alt': 'm'}}, None),
        ('dark-broken-not-counted', {'logo': logo(src=uri(png(IMAGE_MAX))), 'logo_dark': dark(src=uri(JPEG_MAGIC + b'\x00' * (TOTAL_MAX - IMAGE_MAX)))}, None),
        ('dark-logo-invalid-dark-valid', {'logo': {'src': 'x', 'alt': ''}, 'logo_dark': dark()}, None),
        ('dark-both-invalid-order', {'tagline': '', 'mark': {'src': 'x', 'alt': ''}, 'logo_dark': {'src': 3, 'alt': 4, 'height': 5, 'x': 1},
                                     'logo': {'src': 3, 'alt': 4, 'height': 5, 'y': 1}, 'zzz': 1}, None),
        ('dark-and-mark-invalid', {'logo': base_logo, 'logo_dark': dark(alt=''), 'mark': {'src': 'x', 'alt': 'm'}}, None),
        ('dark-with-misspelt-key', {'logo': base_logo, 'logo-dark': dark(), 'logoDark': dark()}, None),
        ('vocab-dark-small-limits', pair(src=uri(png(101)), alt='123456'), tweak(lambda v: v['brand']['logo_limits'].update(max_image_bytes=100, alt_max=5))),
        ('vocab-dark-small-limits-ok', pair(src=uri(png(100)), alt='12345'), tweak(lambda v: v['brand']['logo_limits'].update(max_image_bytes=100, alt_max=5))),
        ('vocab-dark-total', {'logo': logo(src=uri(png(100))), 'logo_dark': dark(src=uri(png(51)))},
         tweak(lambda v: v['brand']['logo_limits'].update(max_image_bytes=100, max_total_bytes=150))),
        ('vocab-dark-total-ok', {'logo': logo(src=uri(png(100))), 'logo_dark': dark(src=uri(png(50)))},
         tweak(lambda v: v['brand']['logo_limits'].update(max_image_bytes=100, max_total_bytes=150))),
        ('vocab-dark-height', pair(height=19), tweak(lambda v: v['brand']['logo_limits']['height'].update(min=20, max=30))),
        ('vocab-dark-height-ok', pair(height=30), tweak(lambda v: v['brand']['logo_limits']['height'].update(min=20, max=30))),
        ('vocab-dark-default-height', {'logo': logo(), 'logo_dark': dark()}, tweak(lambda v: v['brand']['logo_limits']['height'].update(default=48))),
        ('vocab-dark-types', pair(src=uri(JPEG_MAGIC + b'\x00' * 8, 'image/jpeg')), tweak(lambda v: v['brand']['logo_limits'].update(types=['image/png']))),
        ('vocab-dark-without-brand', dict(good(), logo_dark=dark()), {key: value for key, value in VOCAB.items() if key != 'brand'}),
    ]
    cases += [(f'dark-src-{name}', pair(src=src), None) for name, src in bad_srcs.items()]
    return cases


def mutants(count, seed=7):
    """Generated brands: the full brand with one to three random edits (a junk value for a key, a deleted key, a swapped payload)."""
    rng = random.Random(seed)
    payloads = [uri(png()), uri(JPEG_MAGIC + b'\x00' * 8, 'image/jpeg'), uri(WEBP_MAGIC + b'VP8 ', 'image/webp'), svg_uri(SVG), svg_uri(svg('<script/>')),
                uri(png(), 'image/jpeg'), uri(png(), 'image/gif'), uri(png(), 'image/svg+xml'), 'data:image/png;base64,', 'data:image/png;base64,@@@@',
                'http://x/y.png', '', 'data:', 'data:image/png;base64,QR==', uri(png(IMAGE_MAX)), uri(png(IMAGE_MAX + 1)), uri(png(TOTAL_MAX - IMAGE_MAX + 1)),
                uri(png(TOTAL_MAX - IMAGE_MAX))]
    junk = [None, True, False, 0, 1, -1, 15, 16, 17, 32, 63, 64, 65, 2.5, '', ' ', 'x', 'x' * ALT_MAX, 'x' * (ALT_MAX + 1), 'a\x00', 'a\nb', '  padded  ',
            'é' * ALT_MAX, '\U0001f600' * (ALT_MAX + 1), [], [1], {}, {'src': uri(png())}, {'src': uri(png()), 'alt': 'ok'}, {'alt': 'x'},
            {'src': uri(png()), 'alt': 'ok', 'height': 40}, {'src': uri(png()), 'alt': 'ok', 'extra': 1}]
    keys = ['logo', 'logo_dark', 'mark', 'tagline', 'extra']
    image_keys = ['src', 'alt', 'height', 'extra']
    out = []
    for index in range(count):
        brand = copy.deepcopy(good())
        if rng.random() < 0.4:
            brand['logo_dark'] = {'src': uri(png(40)), 'alt': 'dark'}
        for _ in range(rng.randint(1, 3)):
            target = rng.choice([brand] + [brand[k] for k in ('logo', 'logo_dark', 'mark') if isinstance(brand.get(k), dict)])
            action = rng.random()
            if action < 0.35:
                target[rng.choice(keys if target is brand else image_keys)] = copy.deepcopy(rng.choice(junk))
            elif action < 0.7 and target is not brand:
                target['src'] = rng.choice(payloads)
            elif action < 0.85 and target:
                del target[rng.choice(sorted(target))]
            elif target is not brand:
                target['alt'] = rng.choice(junk)
            else:
                target[rng.choice(keys)] = copy.deepcopy(rng.choice(junk))
        out.append((f'mutant-{index:03d}', brand, None))
    return out


def brand_cases():
    return named_cases() + logo_dark_cases() + mutants(220)


def test_there_are_forty_and_more_logo_dark_cases_with_unique_ids_valid_and_invalid():
    cases = logo_dark_cases()
    assert len(cases) >= 40 and len({case[0] for case in cases}) == len(cases)
    assert not {case[0] for case in cases} & {case[0] for case in named_cases()}
    outcomes = [bool(validate_brand(brand, vocabulary)['errors']) for _, brand, vocabulary in cases]
    assert outcomes.count(False) >= 12 and outcomes.count(True) >= 40, (outcomes.count(False), outcomes.count(True))
    seen = {e['message'] for _, brand, vocabulary in cases for e in validate_brand(brand, vocabulary)['errors']}
    assert 'logo_dark needs a logo' in seen
    paths = {e['path'] for _, brand, vocabulary in cases for e in validate_brand(brand, vocabulary)['errors']}
    assert {'brand.logo_dark', 'brand.logo_dark.src', 'brand.logo_dark.alt', 'brand.logo_dark.height', 'brand.logo_dark.zoom', 'brand.logo-dark', 'brand'} <= paths


def test_the_corpus_is_large_and_covers_valid_and_invalid_brands_with_unique_ids():
    cases = brand_cases()
    assert len({case[0] for case in cases}) == len(cases) >= 60
    outcomes = [bool(validate_brand(brand, vocabulary)['errors']) for _, brand, vocabulary in cases]
    assert 20 <= outcomes.count(False) and 100 <= outcomes.count(True), (outcomes.count(False), outcomes.count(True))
    # every message the validator can produce is exercised
    seen = {e['message'] for _, brand, vocabulary in cases for e in validate_brand(brand, vocabulary)['errors']}
    for wanted in ('Required', 'Unknown key zzz', 'Must be text', 'Must not contain control characters', 'Brand must set logo, mark or tagline',
                   'Must be an object with src and alt', 'The payload is not valid base64', 'The image is empty', 'An SVG must be UTF-8 text',
                   'An SVG must not use @import', 'An SVG must not declare entities (<!ENTITY)', 'An SVG must not contain javascript: URLs',
                   'An SVG must not have event attributes (on*=)', 'The data is not a WebP image (wrong file signature)',
                   'An SVG must start at <svg (an XML prolog and comments may come before it)',
                   'An SVG must be well-formed: it must end with </svg>', 'An SVG must not have a DOCTYPE with an internal subset'):
        assert wanted in seen, wanted
    assert any(message.startswith('The images of a brand add up to') for message in seen)
    assert any(message.startswith('The image is ') and 'bytes; at most' in message for message in seen)
