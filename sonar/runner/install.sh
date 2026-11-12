#!/bin/bash
# Start the desk-sonar GitLab Runner as a container on the SonarQube host. Re-runnable.
# The runner authentication token (glrt-...) comes on stdin, so it never appears in a command line or log:
#   create the runner in GitLab (Settings > CI/CD > Runners > New project runner: tag desk-sonar,
#   "Protected", untagged jobs off), then
#   ssh desk 'bash ~/sonarqube-setup/runner/install.sh' < token-file
# RUNTIME=runsc runs jobs in gVisor (needs a network without Docker's embedded DNS; see config.toml.tmpl).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
DIR=/mnt/data/sonarqube/runner
IMAGE=gitlab/gitlab-runner:alpine-v19.5.3@sha256:25adb59339aebbee89050b2d3fd0d193a30c1860c70fd4d98d1c8b1e154914a3
RUNTIME=${RUNTIME:-runc}

token=$(cat)
case "$token" in glrt-*) ;; *) echo "expected a glrt- runner token on stdin" >&2; exit 1;; esac

sudo install -d -m 700 "$DIR"
sed -e "s|__RUNNER_TOKEN__|$token|" -e "s|__RUNTIME__|$RUNTIME|" "$HERE/config.toml.tmpl" \
  | sudo tee "$DIR/config.toml" >/dev/null
sudo chmod 600 "$DIR/config.toml"

sudo docker rm -f desk-sonar-runner >/dev/null 2>&1 || true
# --userns=host: the runner talks to the Docker socket, which the daemon's user-namespace remapping would block.
# The jobs it starts still run in the remapped user namespace.
sudo docker run -d --name desk-sonar-runner --restart unless-stopped --userns=host \
  --memory 256m \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$DIR:/etc/gitlab-runner" \
  "$IMAGE" >/dev/null
sleep 5
sudo docker logs --tail 5 desk-sonar-runner 2>&1 | sed -E 's/glrt-[A-Za-z0-9_-]+/glrt-***/g'
sudo docker ps --filter name=desk-sonar-runner --format '{{.Names}} {{.Status}}'
