// CHAOS OS pipeline:
//   build -> unit tests -> alert-rule tests -> security scan -> deploy lab -> smoke test
//   -> resilience gate -> on-call drill -> reports -> teardown
pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 45, unit: 'MINUTES')
        disableConcurrentBuilds()  // one build per branch at a time
    }

    environment {
        // One lab per executor, no host ports (override file skipped): builds of
        // different branches run side by side without touching each other or a
        // lab running locally on the same Docker host.
        COMPOSE_PROJECT_NAME = "chaosos-ci-${env.EXECUTOR_NUMBER}"
        COMPOSE_FILE = 'docker-compose.yml'
        LAB_NETWORK = "chaosos-ci-${env.EXECUTOR_NUMBER}_default"
    }

    stages {
        stage('Build images') {
            steps {
                sh 'docker compose --profile tools build'
            }
        }

        stage('Unit tests') {
            steps {
                sh 'docker compose run --rm --entrypoint python controller -m unittest discover -s tests -v'
            }
        }

        stage('Alert rules') {
            steps {
                // Alerts are code too: validate the configs and unit-test the SLO
                // burn-rate rules (observability/prometheus/tests/slo_test.yml).
                sh 'docker compose run --rm --no-deps --entrypoint promtool prometheus check config /etc/prometheus/prometheus.yml'
                sh 'docker compose run --rm --no-deps --entrypoint promtool prometheus test rules /etc/prometheus/tests/slo_test.yml'
                sh 'docker compose run --rm --no-deps --entrypoint amtool alertmanager check-config /etc/alertmanager/alertmanager.yml'
            }
        }

        stage('Security scan') {
            steps {
                // Secrets in code and git history (gitleaks), vulnerable dependencies and
                // Dockerfile misconfigurations (trivy fs), image CVEs and SBOMs (trivy image).
                sh 'sh scripts/security-scan.sh'
            }
            post {
                always {
                    archiveArtifacts artifacts: 'security-reports/**', allowEmptyArchive: true
                }
            }
        }

        stage('Deploy lab') {
            steps {
                sh 'docker compose up -d --wait'
                sh 'docker compose ps'
            }
        }

        stage('Smoke test') {
            steps {
                // Piped via stdin so no bind mount is needed (Docker-outside-of-Docker).
                sh 'docker run --rm -i --network "$LAB_NETWORK" python:3.12-slim python - http://frontend:8080 < scripts/smoke_test.py'
            }
        }

        stage('Resilience gate') {
            steps {
                // Checks and limits live in resilience-gate.yml (policy as code).
                sh 'docker compose run --rm controller gate'
            }
            post {
                always {
                    sh 'docker compose run --rm -T controller report > resilience-report.txt || true'
                    sh 'cat resilience-report.txt || true'
                    archiveArtifacts artifacts: 'resilience-report.txt', allowEmptyArchive: true
                }
            }
        }

        stage('On-call drill') {
            steps {
                // Break the lab without telling anyone: the SLO alert must page the
                // on-call agent, and the agent must heal it on its own in time.
                // (no pipe to tee: dash has no pipefail, so a failed drill would look green)
                sh '''
                    rc=0
                    docker compose run --rm -T controller drill --scenario redis_down --within 120 > oncall-drill.txt 2>&1 || rc=$?
                    cat oncall-drill.txt
                    exit $rc
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'oncall-drill.txt', allowEmptyArchive: true
                }
            }
        }
    }

    post {
        always {
            sh 'docker compose logs --no-color > lab-logs.txt || true'
            archiveArtifacts artifacts: 'lab-logs.txt', allowEmptyArchive: true
            sh 'docker compose --profile tools down -v --remove-orphans || true'
        }
    }
}
