"""Shared test setup."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
IN_CI = bool(os.environ.get('CI') or os.environ.get('JENKINS_URL'))
NODE_MAJOR = 20  # package.json engines


def without_tree(resolved):
    """A resolve result without `shell.tree` and `brand`: the revision 1 to 3 goldens were written before the tree existed and are never
    rewritten, so what they pin is everything else (the tree of those themes is pinned by tests/golden/shell-from-layout.json)."""
    resolved = json.loads(json.dumps(resolved))
    assert resolved['shell'].pop('tree')['version'] == 1
    assert resolved.pop('brand') is None  # revisions 1 to 3 have no brand; the goldens were written before the key existed
    return resolved


@pytest.fixture
def require_node():
    """Call with the npm packages a test needs; skips locally when node or one is missing, FAILS in CI.

    The TypeScript twin of the resolver and the Tailwind preset are only exercised through node. A CI run that skipped
    them would let Python and TypeScript drift apart unseen, so with CI or JENKINS_URL set the Jenkinsfile's `npm ci`
    is required to have run and these tests fail instead of skipping.
    """
    def need(*packages):
        problem = None
        node = shutil.which('node')
        if not node:
            problem = 'node is not installed'
        else:
            version = subprocess.run([node, '--version'], capture_output=True, text=True).stdout.strip()
            match = re.match(r'v(\d+)', version)
            if not match or int(match.group(1)) < NODE_MAJOR:
                problem = f'node {version or "(unknown version)"} is older than the {NODE_MAJOR} package.json requires'
            else:
                missing = [name for name in packages if not (ROOT / 'node_modules' / name).exists()]
                if missing:
                    problem = f'node_modules lacks {", ".join(missing)} (run `npm ci`)'
        if problem:
            message = f'the TypeScript tests need node >= {NODE_MAJOR} and the dev dependencies: {problem}'
            if IN_CI:
                pytest.fail(message + '. CI must run them; the Jenkinsfile Test stage installs them with `npm ci`.')
            pytest.skip(message)
    return need
