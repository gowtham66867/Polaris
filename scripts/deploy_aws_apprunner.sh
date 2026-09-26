#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-south-1}"
SERVICE_NAME="${POLARIS_AWS_SERVICE_NAME:-polaris-guidance-aws}"
ECR_REPOSITORY="${POLARIS_ECR_REPOSITORY:-polaris-guidance}"
ACCESS_ROLE_NAME="${POLARIS_APP_RUNNER_ROLE:-PolarisAppRunnerECRAccessRole}"
IMAGE_TAG="${POLARIS_IMAGE_TAG:-$(git rev-parse --short=12 HEAD)}"

for command_name in aws docker git jq; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command is missing: ${command_name}" >&2
    exit 1
  fi
done

AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"
IMAGE_URI="${ECR_URI}:${IMAGE_TAG}"

if ! aws ecr describe-repositories \
  --region "${AWS_REGION}" \
  --repository-names "${ECR_REPOSITORY}" >/dev/null 2>&1; then
  aws ecr create-repository \
    --region "${AWS_REGION}" \
    --repository-name "${ECR_REPOSITORY}" \
    --image-scanning-configuration scanOnPush=true >/dev/null
fi

aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin \
    "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

docker build --platform linux/amd64 --tag "${IMAGE_URI}" .
docker push "${IMAGE_URI}"

if ! aws iam get-role --role-name "${ACCESS_ROLE_NAME}" >/dev/null 2>&1; then
  TRUST_POLICY="$(mktemp)"
  trap 'rm -f "${TRUST_POLICY}"' EXIT
  cat >"${TRUST_POLICY}" <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "build.apprunner.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON
  aws iam create-role \
    --role-name "${ACCESS_ROLE_NAME}" \
    --assume-role-policy-document "file://${TRUST_POLICY}" >/dev/null
  aws iam attach-role-policy \
    --role-name "${ACCESS_ROLE_NAME}" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
fi

ACCESS_ROLE_ARN="$(aws iam get-role \
  --role-name "${ACCESS_ROLE_NAME}" \
  --query 'Role.Arn' \
  --output text)"

SOURCE_CONFIGURATION="$(jq -n \
  --arg image "${IMAGE_URI}" \
  --arg role "${ACCESS_ROLE_ARN}" \
  '{
    AutoDeploymentsEnabled: false,
    AuthenticationConfiguration: {AccessRoleArn: $role},
    ImageRepository: {
      ImageIdentifier: $image,
      ImageRepositoryType: "ECR",
      ImageConfiguration: {
        Port: "8080",
        RuntimeEnvironmentVariables: {
          POLARIS_AUTH_MODE: "demo",
          POLARIS_DB_PATH: "/tmp/polaris-guidance.db",
          POLARIS_HERMES_MODEL: "anthropic/claude-opus-5"
        }
      }
    }
  }')"

SERVICE_ARN="$(aws apprunner list-services \
  --region "${AWS_REGION}" \
  --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn | [0]" \
  --output text)"

if [[ "${SERVICE_ARN}" == "None" ]]; then
  SERVICE_ARN="$(aws apprunner create-service \
    --region "${AWS_REGION}" \
    --service-name "${SERVICE_NAME}" \
    --source-configuration "${SOURCE_CONFIGURATION}" \
    --health-check-configuration 'Protocol=HTTP,Path=/api/health,Interval=10,Timeout=5,HealthyThreshold=1,UnhealthyThreshold=5' \
    --query 'Service.ServiceArn' \
    --output text)"
else
  aws apprunner update-service \
    --region "${AWS_REGION}" \
    --service-arn "${SERVICE_ARN}" \
    --source-configuration "${SOURCE_CONFIGURATION}" >/dev/null
fi

aws apprunner wait service-running \
  --region "${AWS_REGION}" \
  --service-arn "${SERVICE_ARN}"

SERVICE_URL="$(aws apprunner describe-service \
  --region "${AWS_REGION}" \
  --service-arn "${SERVICE_ARN}" \
  --query 'Service.ServiceUrl' \
  --output text)"

echo "Polaris AWS deployment: https://${SERVICE_URL}"
echo "Image: ${IMAGE_URI}"
