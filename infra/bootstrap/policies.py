"""Print one of the IAM documents bootstrap.sh applies, as JSON.

    python3 -I policies.py <document> --account ... --region ... --name ... --prefix ... --project-path ... --project-id ...

Documents:
  trust-readonly, trust-staging, trust-production   who may assume each CI role
  ci-readonly, ci-staging, ci-production             what each CI role may do
  boundary                                           the most a role created by the pipeline can ever do
  state-bucket                                       Terraform state bucket policy (TLS only)

--name is the GitLab project name (state bucket, CI roles); --prefix is the Terraform var.name, the prefix of
every resource the pipeline creates (shortlinks-staging-*, shortlinks-production-*).
"""

import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument("document")
for flag in ("--account", "--region", "--name", "--prefix", "--project-path", "--project-id"):
    parser.add_argument(flag, required=True)
args = parser.parse_args()

A, R, N, P = args.account, args.region, args.name, args.prefix
BUCKET = f"arn:aws:s3:::{N}-tfstate-{A}"
REPO = f"arn:aws:ecr:{R}:{A}:repository/{P}"
BOUNDARY = f"arn:aws:iam::{A}:policy/{P}-boundary"
IN_REGION = {"StringEquals": {"aws:RequestedRegion": R}}


def allow(sid, action, resource, condition=None):
    statement = {"Sid": sid, "Effect": "Allow", "Action": action, "Resource": resource}
    if condition:
        statement["Condition"] = condition
    return statement


def trust(sid, sub, protected):
    # This project only (stable id, not just its path), GitLab-hosted runners only: the self-hosted runner next
    # to SonarQube can never assume a deploy role.
    equals = {
        "gitlab.com:aud": "https://gitlab.com",
        "gitlab.com:project_id": args.project_id,
        "gitlab.com:runner_environment": "gitlab-hosted",
    }
    if protected:
        equals["gitlab.com:ref_protected"] = "true"
    return [{
        "Sid": sid,
        "Effect": "Allow",
        "Principal": {"Federated": f"arn:aws:iam::{A}:oidc-provider/gitlab.com"},
        "Action": "sts:AssumeRoleWithWebIdentity",
        "Condition": {"StringEquals": equals, "StringLike": {"gitlab.com:sub": sub}},
    }]


SUB = f"project_path:{args.project_path}:ref_type"


def state(*keys, write):
    actions = ["s3:GetObject", "s3:PutObject"] if write else ["s3:GetObject"]
    statements = [
        allow("StateList", "s3:ListBucket", BUCKET),
        allow("StateFiles", actions, [f"{BUCKET}/{k}" for k in keys]),
    ]
    if write:
        statements.append(allow("StateLocks", ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                                [f"{BUCKET}/{k}.tflock" for k in keys]))
    return statements


def read_everything(envs):
    # What `terraform plan` reads to refresh the shared stack and the given environments.
    fns = [f"arn:aws:lambda:{R}:{A}:function:{P}-{e}" for e in envs]
    return [
        allow("ReadRepository", [
            "ecr:DescribeRepositories", "ecr:DescribeImages", "ecr:GetRepositoryPolicy", "ecr:GetLifecyclePolicy",
            "ecr:ListTagsForResource",
        ], REPO),
        allow("ReadFunctions", ["lambda:Get*", "lambda:List*"], fns + [f + ":*" for f in fns]),
        allow("ReadTables", ["dynamodb:Describe*", "dynamodb:ListTagsOfResource"],
              [f"arn:aws:dynamodb:{R}:{A}:table/{P}-{e}-*" for e in envs]),
        allow("ReadRoles", ["iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies",
                            "iam:ListAttachedRolePolicies"],
              [f"arn:aws:iam::{A}:role/{P}-{e}-*" for e in envs]),
        allow("ReadApis", "apigateway:GET", [f"arn:aws:apigateway:{R}::/apis", f"arn:aws:apigateway:{R}::/apis/*",
                                             f"arn:aws:apigateway:{R}::/tags/*"]),
        allow("ReadWithoutResourceLevel", [
            "logs:DescribeLogGroups", "logs:ListTagsForResource", "logs:ListTagsLogGroup",
            "cloudwatch:DescribeAlarms", "cloudwatch:ListTagsForResource",
        ], "*", IN_REGION),
    ]


def shared_reads():
    # The reads a deploy role needs beyond its own environment (which environment() already covers).
    keep = {"ReadRepository", "ReadWithoutResourceLevel"}
    return [s for s in read_everything([]) if s["Sid"] in keep]


def environment(env):
    # Full control of one environment's resources, named <prefix>-<env>-*. API Gateway HTTP APIs have random ids,
    # so their statement is scoped to the region, not to one environment.
    E = f"{P}-{env}"
    fn = f"arn:aws:lambda:{R}:{A}:function:{E}"
    roles = f"arn:aws:iam::{A}:role/{E}-*"
    groups = [f"arn:aws:logs:{R}:{A}:log-group:/aws/lambda/{E}", f"arn:aws:logs:{R}:{A}:log-group:/aws/lambda/{E}:*",
              f"arn:aws:logs:{R}:{A}:log-group:/aws/apigateway/{E}",
              f"arn:aws:logs:{R}:{A}:log-group:/aws/apigateway/{E}:*"]
    return [
        allow(f"{env}WriteRolesOnlyWithBoundary", ["iam:CreateRole", "iam:PutRolePolicy", "iam:UpdateAssumeRolePolicy",
                                                  "iam:PutRolePermissionsBoundary"],
              roles, {"StringEquals": {"iam:PermissionsBoundary": BOUNDARY}}),
        allow(f"{env}ManageOwnRoles", ["iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies",
                                       "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole",
                                       "iam:DeleteRolePolicy", "iam:DeleteRole", "iam:TagRole", "iam:UntagRole"], roles),
        allow(f"{env}PassRolesToLambdaOnly", "iam:PassRole", roles,
              {"StringEquals": {"iam:PassedToService": "lambda.amazonaws.com"}}),
        allow(f"{env}Function", [
            "lambda:CreateFunction", "lambda:DeleteFunction", "lambda:Get*", "lambda:List*",
            "lambda:UpdateFunctionCode", "lambda:UpdateFunctionConfiguration", "lambda:PublishVersion",
            "lambda:CreateAlias", "lambda:UpdateAlias", "lambda:DeleteAlias", "lambda:AddPermission",
            "lambda:RemovePermission", "lambda:PutFunctionConcurrency", "lambda:DeleteFunctionConcurrency",
            "lambda:TagResource", "lambda:UntagResource",
        ], [fn, f"{fn}:*"]),
        allow(f"{env}Table", [
            "dynamodb:CreateTable", "dynamodb:DeleteTable", "dynamodb:UpdateTable", "dynamodb:Describe*",
            "dynamodb:UpdateContinuousBackups", "dynamodb:ListTagsOfResource", "dynamodb:TagResource",
            "dynamodb:UntagResource",
        ], f"arn:aws:dynamodb:{R}:{A}:table/{E}-*"),
        allow(f"{env}LogGroups", [
            "logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy", "logs:DeleteRetentionPolicy",
            "logs:TagResource", "logs:UntagResource", "logs:TagLogGroup", "logs:UntagLogGroup",
        ], groups),
        allow(f"{env}Alarms", ["cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms", "cloudwatch:TagResource",
                               "cloudwatch:UntagResource"], f"arn:aws:cloudwatch:{R}:{A}:alarm:{E}-*"),
        # Lambda checks that the caller can read the image it points the function at.
        allow(f"{env}PullImage", ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"], REPO),
    ]


def api_gateway():
    return [
        # Creating a tagged stage also needs apigateway:TagResource, an action IAM enforces but Access Analyzer
        # does not list (bootstrap.sh accepts exactly those two findings).
        allow("HttpApis", ["apigateway:GET", "apigateway:POST", "apigateway:PUT", "apigateway:PATCH",
                           "apigateway:DELETE", "apigateway:TagResource", "apigateway:UntagResource"],
              [f"arn:aws:apigateway:{R}::/apis", f"arn:aws:apigateway:{R}::/apis/*", f"arn:aws:apigateway:{R}::/tags/*"]),
        # Access logging of HTTP APIs is set up through CloudWatch Logs log deliveries (no resource-level control).
        allow("AccessLogDelivery", [
            "logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery", "logs:DeleteLogDelivery",
            "logs:ListLogDeliveries", "logs:PutResourcePolicy", "logs:DescribeResourcePolicies",
        ], "*", IN_REGION),
    ]


def ci_readonly():
    return (state("shared.tfstate", "service/staging.tfstate", "service/production.tfstate", write=False)
            + read_everything(["staging", "production"]))


def ci_staging():
    return (state("shared.tfstate", "service/staging.tfstate", write=True)
            + shared_reads()
            + [
                allow("ManageRepository", [
                    "ecr:CreateRepository", "ecr:DeleteRepository", "ecr:PutLifecyclePolicy",
                    "ecr:DeleteLifecyclePolicy", "ecr:SetRepositoryPolicy", "ecr:DeleteRepositoryPolicy",
                    "ecr:PutImageScanningConfiguration", "ecr:PutImageTagMutability", "ecr:TagResource",
                    "ecr:UntagResource", "ecr:BatchDeleteImage", "ecr:ListImages",
                ], REPO),
                allow("PushImages", ["ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload",
                                     "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage"], REPO),
                allow("RegistryLogin", "ecr:GetAuthorizationToken", "*"),
            ]
            + environment("staging") + api_gateway())


def ci_production():
    # No push and no repository changes: production only runs images main already pushed.
    return (state("service/production.tfstate", write=True)
            + shared_reads()
            + environment("production") + api_gateway())


def boundary():
    return [
        allow("Links", ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"],
              f"arn:aws:dynamodb:{R}:{A}:table/{P}-*"),
        allow("Logs", ["logs:CreateLogStream", "logs:PutLogEvents"],
              f"arn:aws:logs:{R}:{A}:log-group:/aws/lambda/{P}-*"),
    ]


def state_bucket():
    return [{
        "Sid": "TlsOnly",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [BUCKET, f"{BUCKET}/*"],
        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
    }]


documents = {
    "trust-readonly": lambda: trust("AnyBranchOfThisProject", f"{SUB}:branch:ref:*", protected=False),
    "trust-staging": lambda: trust("ProtectedMainOfThisProject", f"{SUB}:branch:ref:main", protected=True),
    "trust-production": lambda: trust("ProtectedReleaseTagsOfThisProject", f"{SUB}:tag:ref:v*", protected=True),
    "ci-readonly": ci_readonly,
    "ci-staging": ci_staging,
    "ci-production": ci_production,
    "boundary": boundary,
    "state-bucket": state_bucket,
}
print(json.dumps({"Version": "2012-10-17", "Statement": documents[args.document]()}, indent=2))
