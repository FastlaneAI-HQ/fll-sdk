"""Golden fixtures keep the Python and TypeScript resolvers in step (see scripts/gen_theme_golden.py)."""
import importlib.util
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'tests/golden/theme-resolve'


def generator():
    spec = importlib.util.spec_from_file_location('gen_theme_golden', ROOT / 'scripts/gen_theme_golden.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_python_results_match_the_golden_files():
    stale = [path.name for path, content in generator().outputs().items() if not path.exists() or path.read_text() != content]
    assert stale == [], 'run scripts/gen_theme_golden.py'
    assert len(list(GOLDEN.glob('*.json'))) == 7


def close(expected, actual):
    """Equal, allowing the 2-decimal contrast ratio to differ by one rounding step across languages."""
    if isinstance(expected, dict):
        return expected.keys() == actual.keys() and all(
            (abs(expected[k] - actual[k]) <= 0.011 if k == 'ratio' else close(expected[k], actual[k])) for k in expected)
    if isinstance(expected, list):
        return len(expected) == len(actual) and all(close(a, b) for a, b in zip(expected, actual))
    return expected == actual


def test_typescript_resolver_agrees_with_python(require_node):
    require_node('esbuild')
    run = subprocess.run(['node', str(ROOT / 'tests/golden/run_resolve.mjs')], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    produced = json.loads(run.stdout)
    for path in sorted(GOLDEN.glob('*.json')):
        golden = json.loads(path.read_text())
        for key in ('upgrade', 'resolve_v1', 'project', 'resolve', 'contrast'):
            if key in golden:
                assert close(golden[key], produced[path.name][key]), f'{path.name}: {key} differs between Python and TypeScript'
