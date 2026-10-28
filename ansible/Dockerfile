# Ansible runner: executes recovery playbooks against the lab.
# Runs on the lab network with the host Docker socket, so it behaves the same
# on Windows, Linux, and inside Jenkins - no WSL install needed.
FROM python:3.12-slim

COPY --from=docker:27.3-cli /usr/local/bin/docker /usr/local/bin/docker
RUN pip install --no-cache-dir ansible-core==2.17.5

WORKDIR /ansible
COPY . .
ENTRYPOINT ["ansible-playbook"]
