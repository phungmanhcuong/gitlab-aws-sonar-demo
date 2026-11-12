#!/bin/bash
# Nightly pg_dump of the SonarQube database; keeps 7 days. Restore:
#   gunzip -c sonar-<date>.sql.gz | docker compose -f /opt/sonarqube/compose.yaml exec -T db psql -U sonar sonar
set -euo pipefail
DIR=/mnt/data/sonarqube/backups
out=$DIR/sonar-$(date -u +%Y-%m-%d).sql.gz
docker compose -f /opt/sonarqube/compose.yaml exec -T db pg_dump -U sonar sonar | gzip > "$out.tmp"
mv "$out.tmp" "$out"
find "$DIR" -name 'sonar-*.sql.gz' -mtime +7 -delete
ls -lh "$out"
