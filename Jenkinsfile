// Tests this SDK on every v* tag. Nothing is published: apps and core depend
// on the SDK straight from this repository by tag (`fll-sdk.git@vX.Y.Z`), so
// the tag *is* the release, and every app's CI installs whatever it points
// at. A failing test here marks the tag's build FAILED in Jenkins -- the
// signal not to re-pin anything to it.
pipeline {
    agent any
    triggers {
        pollSCM('H/5 * * * *')
    }
    stages {
        stage('Checkout') {
            steps { checkout scm }
        }
        stage('Only run on a tag') {
            steps {
                script {
                    env.VERSION = sh(
                        script: "git describe --tags --exact-match 2>/dev/null | sed 's/^v//' || true",
                        returnStdout: true
                    ).trim()
                    if (!env.VERSION) {
                        echo "HEAD is not exactly a v* tag -- nothing to test."
                        currentBuild.result = 'NOT_BUILT'
                        error('skip')
                    }
                }
            }
        }
        stage('Test') {
            // The SDK's suite on python3.12 -- the version the production
            // image runs -- from a copy outside the workspace, the same way
            // the app pipelines test. Nothing is published: the tag itself is
            // the release, so a FAILED build here means "do not pin this".
            //
            // The TypeScript twin of the resolver and the shared Tailwind
            // preset are only exercised through node, so the dev dependencies
            // are installed from package-lock.json (`npm ci`) and CI is set:
            // with it, those tests FAIL when node (>= 20) or a dependency is
            // missing instead of skipping, so a tag build always covers the
            // TS twin. The build host needs node 20+ on its PATH (its npm
            // already runs for `npm pack` in the app jobs).
            steps {
                sh '''
                    T=$(mktemp -d)
                    trap 'rm -rf "$T"' EXIT
                    export CI=1
                    cp -r . "$T/src"
                    # A node_modules copied from the workspace must not stand in for the install.
                    rm -rf "$T/src/node_modules"
                    python3.12 -m venv "$T/venv"
                    "$T/venv/bin/pip" install -q --upgrade pip
                    "$T/venv/bin/pip" install -q "$T/src" pytest
                    cd "$T/src"
                    node --version
                    npm ci --no-audit --no-fund
                    "$T/venv/bin/python" -m pytest -q -p no:cacheprovider -rs tests
                '''
            }
        }
    }
}
