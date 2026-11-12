#!/bin/bash
# Install and configure SonarQube on a Docker host (here: the desk host, arm64). Re-runnable.
#   scp -r sonar desk:~/sonarqube-setup && ssh desk 'bash ~/sonarqube-setup/setup.sh'
# Leaves:
#   /mnt/data/sonarqube/secrets/admin.pw   admin password (random, mode 600)
#   /mnt/data/sonarqube/secrets/ci.token   project analysis token for GitLab CI (mode 600)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=/mnt/data/sonarqube
SECRETS=$ROOT/secrets
PROJECT_KEY=${PROJECT_KEY:-gitlab-aws-sonar-demo}
GATE="Demo Gate"
COMPOSE_VERSION=v5.6.1
COMPOSE_SHA256=42cfa75f51ad0ccf290bad37899e0038a8c10a0069e85233ecc1d53e3ff1347d   # docker-compose-linux-aarch64
API=http://127.0.0.1:9000/api

# 1. Kernel limits Elasticsearch (inside SonarQube) needs.
echo 'vm.max_map_count=524288' | sudo tee /etc/sysctl.d/99-sonarqube.conf >/dev/null
sudo sysctl -q -p /etc/sysctl.d/99-sonarqube.conf
echo "vm.max_map_count=$(sysctl -n vm.max_map_count)"

# 2. Docker Compose plugin, pinned and checksum-verified.
if ! sudo docker compose version >/dev/null 2>&1; then
  tmp=$(mktemp)
  curl -fsSL -o "$tmp" "https://github.com/docker/compose/releases/download/$COMPOSE_VERSION/docker-compose-linux-aarch64"
  echo "$COMPOSE_SHA256  $tmp" | sha256sum -c -
  sudo install -D -m 755 "$tmp" /usr/local/lib/docker/cli-plugins/docker-compose
  rm -f "$tmp"
fi
sudo docker compose version

# 3. Secrets: generated once, readable by the owner only.
sudo install -d -m 700 -o "$USER" "$ROOT" "$SECRETS" "$ROOT/backups"
if [ ! -f "$SECRETS/db.env" ]; then
  pw=$(openssl rand -hex 24)
  umask 077
  printf 'POSTGRES_USER=sonar\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=sonar\n' "$pw" > "$SECRETS/db.env"
  printf 'SONAR_JDBC_URL=jdbc:postgresql://db:5432/sonar\nSONAR_JDBC_USERNAME=sonar\nSONAR_JDBC_PASSWORD=%s\n' "$pw" > "$SECRETS/sonar.env"
fi

# 4. Start, and keep it started across reboots.
sudo install -D -m 644 "$HERE/compose.yaml" /opt/sonarqube/compose.yaml
sudo install -m 644 "$HERE/sonarqube.service" /etc/systemd/system/sonarqube.service
sudo install -m 755 "$HERE/backup.sh" /opt/sonarqube/backup.sh
sudo install -m 644 "$HERE/sonarqube-backup.service" "$HERE/sonarqube-backup.timer" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sonarqube.service sonarqube-backup.timer
echo -n "waiting for SonarQube"
for _ in $(seq 1 90); do
  status=$(curl -s "$API/system/status" | sed -n 's/.*"status":"\([A-Z_]*\)".*/\1/p' || true)  # refused until it listens
  [ "$status" = UP ] && break
  echo -n "."; sleep 5
done
echo " $status"
[ "$status" = UP ]

# 5. Replace the default admin password.
if [ ! -f "$SECRETS/admin.pw" ]; then
  new=$(openssl rand -base64 24 | tr -d '/+=')Aa1!
  first_login=admin:admin   # SonarQube's documented first-start login; replaced right here
  curl -fsS -u "$first_login" -X POST "$API/users/change_password" \
    --data-urlencode login=admin --data-urlencode previousPassword=admin --data-urlencode "password=$new"
  (umask 077; printf '%s\n' "$new" > "$SECRETS/admin.pw")
  echo "admin password changed"
fi
ADMIN="admin:$(cat "$SECRETS/admin.pw")"
api() { curl -fsS -u "$ADMIN" "$@"; }

# 6. Project, a quality gate the team can edit (a copy of the built-in "Sonar way"), and the CI token.
if ! api "$API/projects/search?projects=$PROJECT_KEY" | grep -q "\"key\":\"$PROJECT_KEY\""; then
  api -X POST "$API/projects/create" --data-urlencode "project=$PROJECT_KEY" \
    --data-urlencode "name=shortlinks" --data-urlencode "mainBranch=main" >/dev/null
  echo "project $PROJECT_KEY created"
fi
if ! api "$API/qualitygates/list" | grep -q "\"name\":\"$GATE\""; then
  api -X POST "$API/qualitygates/copy" --data-urlencode "sourceName=Sonar way" --data-urlencode "name=$GATE" >/dev/null
fi
api -X POST "$API/qualitygates/select" --data-urlencode "gateName=$GATE" --data-urlencode "projectKey=$PROJECT_KEY"
# Each main pipeline sends its commit as the project version, so "new code" is that merge's change.
api -X POST "$API/new_code_periods/set" --data-urlencode "project=$PROJECT_KEY" --data-urlencode type=PREVIOUS_VERSION
# By default a change with fewer than 20 new lines to cover skips the coverage and duplication conditions.
# Merges here are small, so every one of them must meet the gate.
api -X POST "$API/settings/set" --data-urlencode "component=$PROJECT_KEY" \
  --data-urlencode key=sonar.qualitygate.ignoreSmallChanges --data-urlencode value=false
echo "gate: $GATE"
api "$API/qualitygates/show?name=$(printf %s "$GATE" | sed 's/ /%20/g')" \
  | python3 -c 'import json,sys; [print("  ", c["metric"], c["op"], c["error"]) for c in json.load(sys.stdin)["conditions"]]'
if [ ! -f "$SECRETS/ci.token" ]; then
  api -X POST "$API/user_tokens/generate" --data-urlencode "name=gitlab-ci-$PROJECT_KEY" \
    --data-urlencode type=PROJECT_ANALYSIS_TOKEN --data-urlencode "projectKey=$PROJECT_KEY" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])' > "$SECRETS/ci.token.tmp"
  chmod 600 "$SECRETS/ci.token.tmp" && mv "$SECRETS/ci.token.tmp" "$SECRETS/ci.token"
  echo "CI token written to $SECRETS/ci.token"
fi
sudo docker compose -f /opt/sonarqube/compose.yaml ps --format '{{.Name}} {{.Status}}'
