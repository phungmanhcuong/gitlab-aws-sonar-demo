#!/bin/bash
# Remove what bootstrap.sh created, after the pipeline's destroy jobs. The OIDC provider stays: other projects
# in the account use it.
set -euo pipefail
cd "$(dirname "$0")"
set -a; source ./bootstrap.env; set +a
export AWS_PAGER=""
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

delete_policy() {
  local arn=arn:aws:iam::$ACCOUNT:policy/$1
  for v in $(aws iam list-policy-versions --policy-arn "$arn" --query 'Versions[?!IsDefaultVersion].VersionId' --output text 2>/dev/null); do
    aws iam delete-policy-version --policy-arn "$arn" --version-id "$v"
  done
  aws iam delete-policy --policy-arn "$arn" || true
}

for role in readonly staging production; do
  name=$NAME-ci-$role
  aws iam detach-role-policy --role-name "$name" --policy-arn "arn:aws:iam::$ACCOUNT:policy/$name" || true
  aws iam delete-role --role-name "$name" || true
  delete_policy "$name"
done
delete_policy "$PREFIX-boundary"
echo "State bucket $NAME-tfstate-<account> is kept (versioned). Empty and delete it when you are sure."
