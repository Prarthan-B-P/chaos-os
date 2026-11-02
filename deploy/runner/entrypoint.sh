#!/bin/sh
# A key mounted from Windows arrives with open permissions, which ssh refuses;
# copy it inside the container with owner-only permissions.
set -e
mkdir -p /root/.ssh && chmod 700 /root/.ssh
cp /keys/id /root/.ssh/id && chmod 600 /root/.ssh/id
exec ansible-playbook --private-key /root/.ssh/id "$@"
