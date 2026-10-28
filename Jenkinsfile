// CHAOS OS pipeline: build -> deploy lab -> smoke test -> resilience gate -> teardown.
pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()  // experiments share one Docker host
    }

    environment {
        COMPOSE_PROJECT_NAME = 'chaosos'
        LAB_NETWORK = 'chaosos_default'
    }

    stages {
        stage('Build images') {
            steps {
                sh 'docker compose build'
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
                // Phase 3+: run chaos experiments and fail the build when recovery misses the SLO.
                echo 'No resilience experiments yet - added in Phase 3.'
            }
        }
    }

    post {
        always {
            sh 'docker compose logs --no-color > lab-logs.txt || true'
            archiveArtifacts artifacts: 'lab-logs.txt', allowEmptyArchive: true
            sh 'docker compose down -v --remove-orphans || true'
        }
    }
}
