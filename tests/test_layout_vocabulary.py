"""The layout vocabulary's two generated copies, and the generators that keep them in step with the Themes app's file."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = 'scripts/gen_theme_registry.py'
COPIES = ('fastlanelabs_sdk/registry_data/layout-vocabulary.json', 'frontend/layout-vocabulary.json')
THEMES_APP = ROOT.parent / 'apps/fll-themes'


def run(args, cwd=ROOT):
    # Whatever CI says about the outer run, these are developer-machine runs unless a test sets CI itself.
    env = {key: value for key, value in os.environ.items() if key not in ('CI', 'JENKINS_URL')}
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=cwd, timeout=120, env=env)


@pytest.fixture
def standalone(tmp_path):
    """A copy of this checkout with no apps repository beside it: the SDK's own CI."""
    target = tmp_path / 'sdk' / 'fll-sdk'
    shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns('node_modules', 'build', '.git', '*.egg-info', '__pycache__', '.pytest_cache'))
    assert not (target.parent / 'apps').exists()
    return target


def test_the_two_copies_are_identical_and_the_generator_finds_them_current():
    assert (ROOT / COPIES[0]).read_bytes() == (ROOT / COPIES[1]).read_bytes()
    done = run([GENERATOR, '--check'])
    assert done.returncode == 0, done.stdout + done.stderr


def test_standalone_check_only_compares_the_copies_with_each_other_and_requires_them_to_parse(standalone):
    assert run([GENERATOR, '--check'], standalone).returncode == 0
    # The copies differ: stale, and the generator names the one that is not the checked-in source.
    other = json.loads((standalone / COPIES[1]).read_text())
    other['vocabulary_version'] = 2
    (standalone / COPIES[1]).write_text(json.dumps(other, indent=2) + '\n')
    done = run([GENERATOR, '--check'], standalone)
    assert done.returncode == 1 and COPIES[1] in done.stdout and COPIES[0] not in done.stdout
    # Writing makes them identical again (the registry_data copy is the source when the Themes app is absent).
    assert run([GENERATOR], standalone).returncode == 0
    assert (standalone / COPIES[0]).read_bytes() == (standalone / COPIES[1]).read_bytes() == (ROOT / COPIES[0]).read_bytes()
    assert run([GENERATOR, '--check'], standalone).returncode == 0


def test_a_vocabulary_that_does_not_parse_or_is_not_understood_fails_the_generator(standalone):
    for text, message in (('{not json', 'does not parse'), ('{}', 'lacks'),
                          (json.dumps(dict(json.loads((ROOT / COPIES[0]).read_text()), shell_version=2)), 'shell version 2')):
        for copy in COPIES:
            (standalone / copy).write_text(text)
        done = run([GENERATOR, '--check'], standalone)
        assert done.returncode != 0 and message in done.stderr, (text, done.stderr)


def test_the_vocabulary_option_copies_a_given_file_byte_for_byte(standalone, tmp_path):
    source = tmp_path / 'vocabulary.json'
    data = json.loads((ROOT / COPIES[0]).read_text())
    data['vocabulary_version'] = 7
    source.write_bytes((json.dumps(data, indent=4) + '\n').encode())
    assert run([GENERATOR, '--check', '--vocabulary', str(source)], standalone).returncode == 1
    assert run([GENERATOR, '--vocabulary', str(source)], standalone).returncode == 0
    for copy in COPIES:
        assert (standalone / copy).read_bytes() == source.read_bytes()
    assert run([GENERATOR, '--check', '--vocabulary', str(source)], standalone).returncode == 0
    missing = run([GENERATOR, '--vocabulary', str(tmp_path / 'nope.json')], standalone)
    assert missing.returncode != 0 and 'No layout vocabulary' in missing.stderr


@pytest.mark.skipif(not (THEMES_APP / 'scripts/sync_layout_vocabulary.py').is_file(), reason='the Themes app is not beside the SDK')
def test_the_themes_apps_sync_script_agrees_with_this_checkout(tmp_path):
    script = THEMES_APP / 'scripts/sync_layout_vocabulary.py'
    assert (THEMES_APP / 'layout-vocabulary.json').read_bytes() == (ROOT / COPIES[0]).read_bytes()
    assert run([str(script), '--check', '--sdk', str(ROOT)]).returncode == 0
    fake = tmp_path / 'fll-sdk'
    (fake / 'fastlanelabs_sdk/registry_data').mkdir(parents=True)
    (fake / 'frontend').mkdir()
    (fake / 'fastlanelabs_sdk/theme_registry.py').write_text('')
    assert run([str(script), '--check', '--sdk', str(fake)]).returncode == 1
    assert run([str(script), '--sdk', str(fake)]).returncode == 0
    assert run([str(script), '--check', '--sdk', str(fake)]).returncode == 0
    for copy in COPIES:
        assert (fake / copy).read_bytes() == (ROOT / copy).read_bytes()
    # Without an SDK source: skipped on a developer machine, a failure in CI.
    nowhere = tmp_path / 'nowhere'
    assert run([str(script), '--check', '--sdk', str(nowhere)]).returncode == 0
    ci = subprocess.run([sys.executable, str(script), '--check', '--sdk', str(nowhere)], capture_output=True, text=True,
                        env={'CI': '1', 'PATH': '/usr/bin:/bin'}, timeout=60)
    assert ci.returncode == 1 and 'CI must supply' in ci.stderr
    assert run([str(script), '--sdk', str(nowhere)]).returncode == 1
