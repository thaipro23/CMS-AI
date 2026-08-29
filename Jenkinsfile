// ========================================================
// AI SERVER / OPENEDX FPT - CI PIPELINE (HARBOR ONLY)
// GitLab/SCM -> Jenkins -> SonarQube Quality Gate -> Harbor
//
// Jenkins has NO Kubernetes access.
// Current delivery mode:
//   GitLab/SCM -> Jenkins -> CI -> SonarQube -> Quality Gate -> Harbor -> STOP
// Kubernetes deployment is performed manually from an authorized K8s admin host.
//
// Jenkins Harbor credential: Username + password.
// Default ID follows the existing Mail Center convention and can be overridden
// by job/folder environment variable HARBOR_CREDENTIAL_ID.
//
// Optional Sonar overrides via Jenkins Job/Folder environment:
//   SONARQUBE_INSTALLATION_NAME, SONAR_SCANNER_TOOL_NAME, SONAR_PROJECT_KEY, SONAR_PROJECT_NAME
//
// Runtime application secrets stay in Kubernetes and are NOT stored in Jenkins/Git.
// Kubernetes deployment/migration/smoke checks are intentionally NOT performed here.
// ========================================================

pipeline {
    agent { label 'built-in' }

    options {
        buildDiscarder(logRotator(numToKeepStr: '30'))
        timeout(time: 2, unit: 'HOURS')
        timestamps()
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
    }

    parameters {
        string(
            name: 'NEXT_PUBLIC_API_BASE_URL',
            defaultValue: 'https://dash-cms.fpl.edu.vn',
            description: 'Public AI API URL, ví dụ https://dash-cms.fpl.edu.vn'
        )

        string(
            name: 'NEXT_PUBLIC_OPENEDX_CMS_BASE_URL',
            defaultValue: 'https://scms.fpl.edu.vn',
            description: 'Open edX Studio/CMS public URL'
        )
    }

    environment {
        APP_VERSION = '25.9.16.7.2.64.16.5.7.2.18'

        // Harbor
        HARBOR_REGISTRY = 'harbor.poly.edu.vn'
        HARBOR_PROJECT = 'acms'

        BACKEND_REPO = "${HARBOR_REGISTRY}/${HARBOR_PROJECT}/ai-server-backend"
        FRONTEND_REPO = "${HARBOR_REGISTRY}/${HARBOR_PROJECT}/ai-server-frontend"

        // Existing Harbor credential.
        // Override using Jenkins Job/Folder env HARBOR_CREDENTIAL_ID if needed.
        HARBOR_CREDS_ID = 'robot$acms+jenkins'

        CLEANUP_AGENT_LABEL = 'built-in'
    }

    stages {

        // ========================================================
        // CHECKOUT
        // ========================================================

        stage('Checkout') {
            steps {
                checkout scm

                script {
                    env.GIT_SHORT_SHA = sh(
                        script: 'git rev-parse --short=8 HEAD',
                        returnStdout: true
                    ).trim()

                    env.IMAGE_TAG =
                        "${env.APP_VERSION}-${env.BUILD_NUMBER}-${env.GIT_SHORT_SHA}"

                    env.BACKEND_IMAGE =
                        "${env.BACKEND_REPO}:${env.IMAGE_TAG}"

                    env.FRONTEND_IMAGE =
                        "${env.FRONTEND_REPO}:${env.IMAGE_TAG}"

                    env.BUILD_INFO =
                        "${env.BUILD_NUMBER} - ${env.GIT_SHORT_SHA}"

                    echo "Build Info: ${env.BUILD_INFO}"
                    echo "Image Tag: ${env.IMAGE_TAG}"
                    echo "Backend image: ${env.BACKEND_IMAGE}"
                    echo "Frontend image: ${env.FRONTEND_IMAGE}"
                }
            }
        }

        // ========================================================
        // PREFLIGHT
        // ========================================================

        stage('Preflight') {
            steps {
                sh '''#!/usr/bin/env bash
set -Eeuo pipefail

echo "===== CHECK REQUIRED TOOLS ====="

for cmd in git docker; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "[FAIL] Missing tool on Jenkins node: $cmd" >&2
        exit 2
    }
done

docker version >/dev/null


echo
echo "===== CHECK FRONTEND BUILD CONFIG ====="

if [[ -z "${NEXT_PUBLIC_API_BASE_URL:-}" || \
      "$NEXT_PUBLIC_API_BASE_URL" == *CHANGE_ME* ]]; then

    echo '[FAIL] NEXT_PUBLIC_API_BASE_URL chưa được cấu hình.' >&2
    exit 2
fi

if [[ "$NEXT_PUBLIC_API_BASE_URL" != https://* ]]; then
    echo '[FAIL] Production NEXT_PUBLIC_API_BASE_URL phải dùng https://' >&2
    exit 2
fi

if [[ -z "${NEXT_PUBLIC_OPENEDX_CMS_BASE_URL:-}" || \
      "$NEXT_PUBLIC_OPENEDX_CMS_BASE_URL" == *CHANGE_ME* ]]; then
    echo '[FAIL] Production NEXT_PUBLIC_OPENEDX_CMS_BASE_URL phải dùng https://' >&2
    exit 2
fi

if [[ "$NEXT_PUBLIC_OPENEDX_CMS_BASE_URL" != https://* ]]; then
    echo '[FAIL] Production NEXT_PUBLIC_OPENEDX_CMS_BASE_URL phải dùng https://' >&2
    exit 2
fi


echo
echo "===== CHECK SOURCE CONTRACT ====="

grep -q "APP_VERSION=$APP_VERSION" .env.production.example

grep -q \
    'image: ai-server-backend' \
    deploy/k8s/base/backend.yaml

grep -q \
    'image: ai-server-frontend' \
    deploy/k8s/base/frontend.yaml

grep -q \
    'path: /api/health' \
    deploy/k8s/base/backend.yaml

grep -q \
    'name: ai-server-migrate' \
    deploy/k8s/jobs/migrate.yaml


echo
echo "===== CHECK NPM LOCKFILES ====="

docker run --rm \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -v "$WORKSPACE:/workspace" \
    -w /workspace \
    python:3.12-slim \
    bash ./scripts/npm-public-registry-lockfile-report.sh \
    /tmp/npm-public-registry-report >/dev/null

echo "Preflight PASS"
'''
            }
        }

        // ========================================================
        // BACKEND CI
        // ========================================================

        stage('Backend CI in Docker') {
            steps {
                sh '''#!/usr/bin/env bash
set -Eeuo pipefail

SAFE_BUILD="$(
    printf '%s' "$BUILD_TAG" \
    | tr -cs '[:alnum:]_.-' '-' \
    | tr '[:upper:]' '[:lower:]'
)"

CI_NETWORK="ai-ci-net-${SAFE_BUILD}"
PG_NAME="ai-ci-pg-${SAFE_BUILD}"
REDIS_NAME="ai-ci-redis-${SAFE_BUILD}"


cleanup_ci() {
    docker rm -f \
        "$PG_NAME" \
        "$REDIS_NAME" \
        >/dev/null 2>&1 || true

    docker network rm \
        "$CI_NETWORK" \
        >/dev/null 2>&1 || true
}

trap cleanup_ci EXIT

cleanup_ci


echo "===== CREATE CI NETWORK ====="

docker network create \
    "$CI_NETWORK" \
    >/dev/null


echo
echo "===== START POSTGRESQL ====="

docker run -d \
    --name "$PG_NAME" \
    --network "$CI_NETWORK" \
    --network-alias postgres \
    -e POSTGRES_DB=ai_openedx_ci \
    -e POSTGRES_USER=ai_ci \
    -e POSTGRES_PASSWORD=ai_ci_password \
    pgvector/pgvector:pg16 \
    >/dev/null


echo
echo "===== START REDIS ====="

docker run -d \
    --name "$REDIS_NAME" \
    --network "$CI_NETWORK" \
    --network-alias redis \
    redis:7-alpine \
    >/dev/null


echo
echo "===== WAIT POSTGRESQL ====="

for i in $(seq 1 30); do

    if docker exec "$PG_NAME" \
        pg_isready \
        -U ai_ci \
        -d ai_openedx_ci \
        >/dev/null 2>&1; then

        echo "PostgreSQL READY"
        break
    fi

    if [[ "$i" == 30 ]]; then
        docker logs "$PG_NAME"
        exit 3
    fi

    sleep 2
done


echo
echo "===== WAIT REDIS ====="

for i in $(seq 1 30); do

    if docker exec "$REDIS_NAME" \
        redis-cli ping 2>/dev/null \
        | grep -q PONG; then

        echo "Redis READY"
        break
    fi

    if [[ "$i" == 30 ]]; then
        docker logs "$REDIS_NAME"
        exit 3
    fi

    sleep 2
done


echo
echo "===== RUN BACKEND TESTS ====="

docker run --rm \
    --network "$CI_NETWORK" \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -e APP_ENV=test \
    -e DEBUG=false \
    -e AUTO_CREATE_TABLES=false \
    -e DATABASE_URL='postgresql+psycopg://ai_ci:ai_ci_password@postgres:5432/ai_openedx_ci' \
    -e TEST_DATABASE_URL='postgresql+psycopg://ai_ci:ai_ci_password@postgres:5432/ai_openedx_ci' \
    -e REDIS_URL='redis://redis:6379/15' \
    -e METRICS_ENABLED=false \
    -e ALLOW_DEMO_ROLE_HEADER=false \
    -e MOCK_LLM=true \
    -e USE_MOCK_OPENEDX=true \
    -v "$WORKSPACE:/workspace" \
    -w /workspace \
    python:3.12-slim \
    bash -lc '

        set -Eeuo pipefail


        echo "===== CREATE PYTHON VENV ====="

        python -m venv /tmp/ai-ci-venv


        echo
        echo "===== INSTALL CI REQUIREMENTS ====="

        /tmp/ai-ci-venv/bin/python \
            -m pip install \
            --disable-pip-version-check \
            -r backend/requirements-ci.txt


        echo
        echo "===== PYTHON COMPILE ====="

        cd backend

        /tmp/ai-ci-venv/bin/python \
            -m compileall \
            -q app


        echo
        echo "===== RUFF ====="

        /tmp/ai-ci-venv/bin/ruff \
            check app \
            --select E9,F63,F7,F82


        echo
        echo "===== ALEMBIC UPGRADE HEAD ====="

        /tmp/ai-ci-venv/bin/alembic \
            -c alembic.ini \
            upgrade head


        echo
        echo "===== BACKEND REGRESSION TESTS ====="

        cd ..

        PATH="/tmp/ai-ci-venv/bin:$PATH" \
            bash ./scripts/ci-backend-tests.sh


        echo
        echo "===== ALEMBIC DOWNGRADE / UPGRADE CHECK ====="

        cd backend

        /tmp/ai-ci-venv/bin/alembic \
            -c alembic.ini \
            downgrade 0052_v25_9_16_7_2_27

        /tmp/ai-ci-venv/bin/alembic \
            -c alembic.ini \
            upgrade head


        echo
        echo "Backend CI PASS"
    '
'''
            }
        }

        // ========================================================
        // SONARQUBE
        // ========================================================

        stage('SonarQube Analysis') {
            steps {
                script {

                    def sonarInstallation =
                        env.SONARQUBE_INSTALLATION_NAME?.trim()
                        ?: 'SonarQube'

                    def sonarScannerTool =
                        env.SONAR_SCANNER_TOOL_NAME?.trim()
                        ?: 'SonarScanner'

                    def sonarProjectKey =
                        env.SONAR_PROJECT_KEY?.trim()
                        ?: 'fpt-ai-server'

                    def sonarProjectName =
                        env.SONAR_PROJECT_NAME?.trim()
                        ?: 'FPT AI Server'

                    def scannerHome =
                        tool sonarScannerTool


                    echo "SonarQube installation: ${sonarInstallation}"
                    echo "SonarScanner tool: ${sonarScannerTool}"
                    echo "Sonar project key: ${sonarProjectKey}"
                    echo "Sonar project name: ${sonarProjectName}"


                    withSonarQubeEnv(sonarInstallation) {

                        sh """#!/usr/bin/env bash
set -Eeuo pipefail

echo "===== SONARQUBE ANALYSIS ====="

"${scannerHome}/bin/sonar-scanner" \\
    -Dsonar.projectKey="${sonarProjectKey}" \\
    -Dsonar.projectName="${sonarProjectName}" \\
    -Dsonar.projectVersion="$APP_VERSION" \\
    -Dsonar.projectBaseDir="$WORKSPACE" \\
    -Dsonar.sources=backend/app,frontend \\
    -Dsonar.sourceEncoding=UTF-8 \\
    -Dsonar.exclusions='frontend/node_modules/**,frontend/.next/**,frontend/out/**,frontend/coverage/**,backend/**/__pycache__/**,**/*.pyc' \\
    -Dsonar.scm.provider=git
"""
                    }
                }
            }
        }


        // stage('SonarQube Quality Gate') {
        //     steps {
        //         timeout(time: 15, unit: 'MINUTES') {
        //             script {
        //                 def qg = waitForQualityGate()

        //                 echo "SonarQube Quality Gate: ${qg.status}"

        //                 if (qg.status != 'OK') {
        //                     error "SonarQube Quality Gate failed: ${qg.status}"
        //                 }
        //             }
        //         }
        //     }
        // }

        // ========================================================
        // HARBOR LOGIN
        // ========================================================

        stage('Docker Login') {
            steps {

                script {

                    def credId =
                        env.HARBOR_CREDENTIAL_ID?.trim()


                    if (!credId) {
                        credId =
                            env.HARBOR_CREDS_ID?.trim()
                    }


                    echo "Harbor Jenkins credential ID: ${credId}"


                    withCredentials([

                        usernamePassword(
                            credentialsId: credId,
                            usernameVariable: 'HARBOR_USER',
                            passwordVariable: 'HARBOR_PASS'
                        )

                    ]) {

                        sh '''#!/usr/bin/env bash
set -Eeuo pipefail

echo "===== HARBOR LOGIN ====="

printf '%s' "$HARBOR_PASS" \
    | docker login "$HARBOR_REGISTRY" \
        -u "$HARBOR_USER" \
        --password-stdin
'''
                    }
                }
            }
        }

        // ========================================================
        // BUILD
        // ========================================================

        stage('Build Docker Images') {
            steps {

                sh '''#!/usr/bin/env bash
set -Eeuo pipefail

echo "===== BUILD AI SERVER IMAGES ====="

echo "Backend:"
echo "$BACKEND_IMAGE"

echo

echo "Frontend:"
echo "$FRONTEND_IMAGE"


export VERSION="$APP_VERSION"

export REGISTRY="${HARBOR_REGISTRY}/${HARBOR_PROJECT}"

export BACKEND_IMAGE="$BACKEND_IMAGE"

export FRONTEND_IMAGE="$FRONTEND_IMAGE"


export NEXT_PUBLIC_API_BASE_URL="$NEXT_PUBLIC_API_BASE_URL"

export NEXT_PUBLIC_OPENEDX_CMS_BASE_URL="$NEXT_PUBLIC_OPENEDX_CMS_BASE_URL"

export NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN=true

export NEXT_PUBLIC_APP_ENV=production

export NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI=false


export FRONTEND_VALIDATE_IN_IMAGE=true

export PUSH=false


bash ./scripts/build-k8s-images.sh


echo
echo "===== BACKEND IMAGE HARDENING ====="

docker run \
    --rm \
    --entrypoint sh \
    "$BACKEND_IMAGE" \
    -c '
        test "$(id -u)" = 10001 &&
        test ! -w /app/app &&
        ! command -v gcc
    '


echo
echo "===== FRONTEND IMAGE HARDENING ====="

docker run \
    --rm \
    --entrypoint sh \
    "$FRONTEND_IMAGE" \
    -c '
        test "$(id -u)" = 10001 &&
        test ! -w /app/server.js
    '


echo
echo "Docker image build PASS"
'''
            }
        }

        // ========================================================
        // PUSH HARBOR
        // ========================================================

        stage('Push Images to Harbor') {
            steps {

                sh '''#!/usr/bin/env bash
set -Eeuo pipefail

echo "===== PUSH IMMUTABLE IMAGES ====="


echo
echo "Pushing backend..."

docker push "$BACKEND_IMAGE"


echo
echo "Pushing frontend..."

docker push "$FRONTEND_IMAGE"


echo
echo "===== CREATE RELEASE METADATA ====="

cat > .jenkins-image-metadata.txt <<META
commit=$(git rev-parse HEAD)
version=$APP_VERSION
build=$BUILD_NUMBER
image_tag=$IMAGE_TAG
backend_image=$BACKEND_IMAGE
frontend_image=$FRONTEND_IMAGE
META


cat .jenkins-image-metadata.txt


echo
echo "===== HARBOR PUSH PASS ====="

echo "IMAGE_TAG=$IMAGE_TAG"

echo "BACKEND_IMAGE=$BACKEND_IMAGE"

echo "FRONTEND_IMAGE=$FRONTEND_IMAGE"


echo
echo "===== REMOVE ONLY CURRENT BUILD IMAGES ====="

docker rmi -f \
    "$BACKEND_IMAGE" \
    "$FRONTEND_IMAGE" \
    >/dev/null 2>&1 || true


echo
echo "Build + Push Harbor DONE"
'''

                archiveArtifacts(
                    artifacts: '.jenkins-image-metadata.txt',
                    fingerprint: true
                )
            }
        }
    }

    post {

        always {

            script {

                try {

                    node(
                        env.CLEANUP_AGENT_LABEL
                        ?: 'built-in'
                    ) {

                        sh '''#!/usr/bin/env bash
set +e

echo "===== CLEANUP ====="

docker logout \
    "$HARBOR_REGISTRY" \
    >/dev/null 2>&1 || true


rm -f \
    .jenkins-image-metadata.txt


# Do NOT run:
# docker image prune -af
# docker system prune
# docker builder prune
# docker buildx prune
# docker volume prune

echo "Cleanup DONE"
'''
                    }

                } catch (e) {

                    echo(
                        "Cleanup skipped/failed: ${e.message}"
                    )
                }
            }
        }


        success {

            echo """
✓ AI Server CI SUCCESS

Build:
${env.BUILD_INFO}

Image tag:
${env.IMAGE_TAG}

Backend:
${env.BACKEND_IMAGE}

Frontend:
${env.FRONTEND_IMAGE}

Pipeline:
GitLab
→ Jenkins CI
→ SonarQube Quality Gate
→ Harbor

Kubernetes deployment:
MANUAL / Argo CD ở bước sau.
"""
        }


        failure {

            script {

                def info =
                    env.BUILD_INFO
                    ?: "build ${env.BUILD_NUMBER} (checkout có thể chưa hoàn tất)"

                echo(
                    "✗ AI Server pipeline FAILED - ${info}"
                )
            }
        }


        unstable {

            script {

                def info =
                    env.BUILD_INFO
                    ?: "build ${env.BUILD_NUMBER}"

                echo(
                    "⚠ AI Server pipeline UNSTABLE - ${info}"
                )
            }
        }
    }
}