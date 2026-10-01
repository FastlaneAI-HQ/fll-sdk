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
            // A copy outside the workspace, same as the app pipelines, so
            // nothing the test run writes is ever mistaken for source.
            steps {
                sh '''
                    T=$(mktemp -d)
                    trap 'rm -rf "$T"' EXIT
                    cp -r . "$T/src"
                    python3.9 -m venv "$T/venv"
                    "$T/venv/bin/pip" install -q --upgrade pip
                    "$T/venv/bin/pip" install -q "$T/src" pytest
                    cd "$T/src" && "$T/venv/bin/python" -m pytest -q -p no:cacheprovider tests
                '''
            }
        }
    }
}
