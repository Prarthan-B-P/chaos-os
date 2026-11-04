# Ansible control node in a container, so deploying works from Windows too.
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-client \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir ansible-core==2.21.6
# Same settings as deploy/ansible/ansible.cfg: a folder mounted from Windows looks
# world-writable, so Ansible would ignore an ansible.cfg found there.
ENV ANSIBLE_HOST_KEY_CHECKING=False \
    ANSIBLE_CALLBACK_RESULT_FORMAT=yaml \
    ANSIBLE_PYTHON_INTERPRETER=auto_silent \
    ANSIBLE_RETRY_FILES_ENABLED=False \
    ANSIBLE_PIPELINING=True
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
WORKDIR /deploy/ansible
ENTRYPOINT ["/entrypoint.sh"]
