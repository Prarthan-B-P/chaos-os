// CHAOS OS pipeline: build -> unit tests -> deploy lab -> smoke test -> resilience gate -> teardown.
pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()  // experiments share one Docker host
    }

    environment {
        // Separate project + no host ports (override file skipped), so CI never
        // touches or clashes with a lab running locally on the same Docker host.
        COMPOSE_PROJECT_NAME = 'chaosos-ci'
        COMPOSE_FILE = 'docker-compose.yml'
        LAB_NETWORK = 'chaosos-ci_default'
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

        stage('Deploy lab') {
            steps {
                sh 'docker compose up -d --wait'
                sh 'docker compose ps'
            }
        }

        stage('Smoke test') {
            steps {
                // Piped via stdin so no bind mount is needed (Docker-outside-of-Docker).
                sh 'docker run --rm -i --network "$LAB_NETWORK" python:3.12-slim python - http://frontend < scripts/smoke_test.py'
            }
        }

        stage('Resilience gate') {
            steps {
                // The release must recover from each failure with its known-good playbook.
                sh 'docker compose run --rm controller gate --scenario redis_down --action restart_redis --max-recovery 10'
                sh 'docker compose run --rm controller gate --scenario all --action cache_bypass --max-recovery 10'
            }
            post {
                always {
                    sh 'docker compose run --rm controller report || true'
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
