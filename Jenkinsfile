// CHAOS OS pipeline: build -> unit tests -> deploy lab -> smoke test -> resilience gate -> teardown.
pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
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
                // Checks and limits live in resilience-gate.yml (policy as code).
                sh 'docker compose run --rm controller gate'
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
