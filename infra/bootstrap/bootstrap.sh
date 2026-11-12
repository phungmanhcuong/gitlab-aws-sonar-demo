#!/bin/bash
# One-time setup an AWS admin runs before the first pipeline: the Terraform state bucket, the permissions
# boundary for roles the pipeline creates, and three roles GitLab CI assumes through OIDC (no stored AWS keys):
#   <NAME>-ci-readonly    any branch: terraform plan
#   <NAME>-ci-staging     protected main: push images, deploy staging
#   <NAME>-ci-production  protected tags v*: deploy production
# Re-runnable: each step updates what exists. Every policy document passes IAM Access Analyzer first.
#   cp infra/bootstrap/bootstrap.env.example infra/bootstrap/bootstrap.env   # fill in
#   bash infra/bootstrap/bootstrap.sh
set -euo pipefail
cd "$(dirname "$0")"
set -a; source ./bootstrap.env; set +a
export AWS_PAGER=""

read -r ACCOUNT CALLER <<< "$(aws sts get-caller-identity --query '[Account,Arn]' --output text)"
echo "account $ACCOUNT as $CALLER, region $AWS_REGION"
BUCKET=$NAME-tfstate-$ACCOUNT
OIDC_ARN=arn:aws:iam::$ACCOUNT:oidc-provider/gitlab.com

mkdir -p build
render() { python3 -I policies.py "$1" --account "$ACCOUNT" --region "$AWS_REGION" --name "$NAME" --prefix "$PREFIX" \
  --project-path "$PROJECT_PATH" --project-id "$PROJECT_ID" > "build/$1.json"; }
# Access Analyzer's catalog lacks apigateway:TagResource/UntagResource, yet IAM denies a tagged API Gateway stage
# without them. Those two INVALID_ACTION findings are expected; any other ERROR stops the run.
KNOWN='INVALID_ACTION.*apigateway:(Tag|Untag)Resource does not exist'
check() { # <document> <policy type> [resource type]
  local findings
  render "$1"
  findings=$(aws accessanalyzer validate-policy --policy-type "$2" ${3:+--validate-policy-resource-type "$3"} \
    --policy-document "file://build/$1.json" --query 'findings[].[findingType,issueCode,findingDetails]' \
    --output text | grep -Ev "$KNOWN" || true)
  echo "$1: ${findings:-no findings}"
  case "$findings" in *ERROR*|*SECURITY_WARNING*) exit 1;; esac
}
for role in readonly staging production; do
  check "trust-$role" RESOURCE_POLICY AWS::IAM::AssumeRolePolicyDocument
  check "ci-$role" IDENTITY_POLICY
done
check boundary IDENTITY_POLICY
check state-bucket RESOURCE_POLICY AWS::S3::Bucket

# GitLab's OIDC provider exists once per account. Create it if missing.
if ! aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_ARN" >/dev/null 2>&1; then
  aws iam create-open-id-connect-provider --url https://gitlab.com --client-id-list https://gitlab.com >/dev/null
  echo "created OIDC provider $OIDC_ARN"
fi
aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_ARN" \
  --query 'ClientIDList' --output text | grep -qw 'https://gitlab.com'

# State bucket: private, versioned, encrypted, TLS only.
if ! aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
  if [ "$AWS_REGION" = us-east-1 ]; then aws s3api create-bucket --bucket "$BUCKET" >/dev/null
  else aws s3api create-bucket --bucket "$BUCKET" --create-bucket-configuration "LocationConstraint=$AWS_REGION" >/dev/null; fi
fi
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'
aws s3api put-bucket-policy --bucket "$BUCKET" --policy file://build/state-bucket.json
aws s3api put-bucket-tagging --bucket "$BUCKET" --tagging "TagSet=[{Key=Project,Value=$NAME}]"
echo "state bucket: $NAME-tfstate-<account>"

# Managed policy, created or updated; a policy keeps at most 5 versions, so older ones go first.
managed() { # <policy name> <document> <description>
  local arn=arn:aws:iam::$ACCOUNT:policy/$1
  if aws iam get-policy --policy-arn "$arn" >/dev/null 2>&1; then
    for v in $(aws iam list-policy-versions --policy-arn "$arn" --query 'Versions[?!IsDefaultVersion].VersionId' --output text); do
      aws iam delete-policy-version --policy-arn "$arn" --version-id "$v"
    done
    aws iam create-policy-version --policy-arn "$arn" --policy-document "file://build/$2.json" --set-as-default >/dev/null
  else
    aws iam create-policy --policy-name "$1" --policy-document "file://build/$2.json" --description "$3" \
      --tags "Key=Project,Value=$NAME" >/dev/null
  fi
  echo "policy: $1"
}
managed "$PREFIX-boundary" boundary "Most that function roles created by the $NAME pipeline can ever do"

for role in readonly staging production; do
  name=$NAME-ci-$role
  managed "$name" "ci-$role" "GitLab CI of $NAME, $role"
  if aws iam get-role --role-name "$name" >/dev/null 2>&1; then
    aws iam update-assume-role-policy --role-name "$name" --policy-document "file://build/trust-$role.json"
  else
    aws iam create-role --role-name "$name" --assume-role-policy-document "file://build/trust-$role.json" \
      --description "GitLab CI of $PROJECT_PATH ($role), GitLab-hosted runners only" \
      --max-session-duration 3600 --tags "Key=Project,Value=$NAME" >/dev/null
  fi
  aws iam attach-role-policy --role-name "$name" --policy-arn "arn:aws:iam::$ACCOUNT:policy/$name"
  echo "role: $name"
done

echo
echo "Set these GitLab CI/CD variables (not secret; protect STAGING and PRODUCTION):"
echo "  AWS_ACCOUNT_ID       = <account>"
echo "  TF_STATE_BUCKET      = $NAME-tfstate-<account>"
echo "  ROLE_ARN_READONLY    = arn:aws:iam::<account>:role/$NAME-ci-readonly"
echo "  ROLE_ARN_STAGING     = arn:aws:iam::<account>:role/$NAME-ci-staging"
echo "  ROLE_ARN_PRODUCTION  = arn:aws:iam::<account>:role/$NAME-ci-production"
