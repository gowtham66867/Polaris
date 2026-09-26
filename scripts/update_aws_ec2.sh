#!/usr/bin/env bash
# Redeploys the running Polaris EC2 instance in place (same public URL) using
# SSM Run Command. Reads the model key from SSM Parameter Store at runtime, so the
# key never appears in git, user data, or this script. All services used here
# (IAM, SSM Run Command, standard SecureString parameters) are no-cost.
set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-south-1}"
INSTANCE_NAME="${POLARIS_AWS_INSTANCE_NAME:-polaris-guidance-aws}"
REVISION="${POLARIS_REVISION:-main}"
KEY_PARAMETER="${POLARIS_OPENAI_KEY_PARAMETER:-/polaris/openai_api_key}"
GEMINI_KEY_PARAMETER="${POLARIS_GEMINI_KEY_PARAMETER:-/polaris/gemini_api_key}"
GEMINI_MODEL="${POLARIS_GEMINI_MODEL:-gemini-2.5-flash}"
OPENAI_MODEL="${POLARIS_OPENAI_MODEL:-gpt-4.1-mini}"
ROLE_NAME="polaris-ec2-ssm"

account_id="$(aws sts get-caller-identity --query Account --output text)"

instance_id="$(aws ec2 describe-instances --region "${AWS_REGION}" \
  --filters "Name=tag:Name,Values=${INSTANCE_NAME}" 'Name=instance-state-name,Values=running' \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)"
if [[ "${instance_id}" == "None" ]]; then
  echo "No running instance named ${INSTANCE_NAME}; run deploy_aws_ec2.sh first." >&2
  exit 1
fi

if ! aws iam get-role --role-name "${ROLE_NAME}" >/dev/null 2>&1; then
  aws iam create-role --role-name "${ROLE_NAME}" --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "${ROLE_NAME}" \
    --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  aws iam create-instance-profile --instance-profile-name "${ROLE_NAME}" >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "${ROLE_NAME}" --role-name "${ROLE_NAME}"
fi
aws iam put-role-policy --role-name "${ROLE_NAME}" --policy-name polaris-read-model-key \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"ssm:GetParameter\",\"Resource\":[\"arn:aws:ssm:${AWS_REGION}:${account_id}:parameter${KEY_PARAMETER}\",\"arn:aws:ssm:${AWS_REGION}:${account_id}:parameter${GEMINI_KEY_PARAMETER}\"]}]}"

associated="$(aws ec2 describe-iam-instance-profile-associations --region "${AWS_REGION}" \
  --filters "Name=instance-id,Values=${instance_id}" 'Name=state,Values=associated,associating' \
  --query 'IamInstanceProfileAssociations[0].AssociationId' --output text)"
if [[ "${associated}" == "None" ]]; then
  sleep 10  # new instance profiles take a few seconds to propagate
  aws ec2 associate-iam-instance-profile --region "${AWS_REGION}" \
    --instance-id "${instance_id}" --iam-instance-profile "Name=${ROLE_NAME}" >/dev/null
fi

echo "Waiting for the instance to register with SSM…"
for _ in $(seq 1 60); do
  ping="$(aws ssm describe-instance-information --region "${AWS_REGION}" \
    --filters "Key=InstanceIds,Values=${instance_id}" \
    --query 'InstanceInformationList[0].PingStatus' --output text 2>/dev/null || true)"
  [[ "${ping}" == "Online" ]] && break
  sleep 10
done
if [[ "${ping}" != "Online" ]]; then
  echo "Instance did not register with SSM. If the agent was idle, reboot it once (URL is kept on reboot)." >&2
  exit 1
fi

remote_script="$(cat <<REMOTE
set -euo pipefail
cd /opt/polaris
git fetch --quiet origin
git checkout --quiet --force "origin/${REVISION}" 2>/dev/null || git checkout --quiet --force "${REVISION}"
rev=\$(git rev-parse --short HEAD)
docker build --quiet --tag polaris-guidance:\$rev . >/dev/null
key=\$(aws ssm get-parameter --region ${AWS_REGION} --name ${KEY_PARAMETER} --with-decryption --query Parameter.Value --output text 2>/dev/null || true)
gkey=\$(aws ssm get-parameter --region ${AWS_REGION} --name ${GEMINI_KEY_PARAMETER} --with-decryption --query Parameter.Value --output text 2>/dev/null || true)
docker rm -f polaris-guidance >/dev/null 2>&1 || true
docker run --detach --name polaris-guidance --restart unless-stopped --publish 80:8080 \
  --env POLARIS_AUTH_MODE=demo --env POLARIS_DB_PATH=/tmp/polaris-guidance.db \
  --env POLARIS_OPENAI_MODEL=${OPENAI_MODEL} --env OPENAI_API_KEY="\$key" \
  --env POLARIS_GEMINI_MODEL=${GEMINI_MODEL} --env GEMINI_API_KEY="\$gkey" \
  polaris-guidance:\$rev >/dev/null
docker image prune --force >/dev/null
echo "deployed \$rev; gemini key: \$([[ -n "\$gkey" ]] && echo yes || echo no); openai key: \$([[ -n "\$key" ]] && echo yes || echo no)"
REMOTE
)"

params="$(jq -nc --arg s "${remote_script}" '{commands:[$s],executionTimeout:["900"]}')"
command_id="$(aws ssm send-command --region "${AWS_REGION}" --instance-ids "${instance_id}" \
  --document-name AWS-RunShellScript --comment 'Polaris in-place redeploy' \
  --parameters "${params}" --query 'Command.CommandId' --output text)"
echo "Rebuilding on the instance (a few minutes on t3.micro)…"
aws ssm wait command-executed --region "${AWS_REGION}" --command-id "${command_id}" \
  --instance-id "${instance_id}" 2>/dev/null || true
for _ in $(seq 1 60); do
  status="$(aws ssm get-command-invocation --region "${AWS_REGION}" --command-id "${command_id}" \
    --instance-id "${instance_id}" --query Status --output text)"
  [[ "${status}" == "InProgress" || "${status}" == "Pending" ]] || break
  sleep 10
done
aws ssm get-command-invocation --region "${AWS_REGION}" --command-id "${command_id}" \
  --instance-id "${instance_id}" --query '{Status:Status,Output:StandardOutputContent,Error:StandardErrorContent}' --output json
