#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-south-1}"
INSTANCE_NAME="${POLARIS_AWS_INSTANCE_NAME:-polaris-guidance-aws}"
INSTANCE_TYPE="${POLARIS_AWS_INSTANCE_TYPE:-t3.micro}"
REPOSITORY_URL="${POLARIS_REPOSITORY_URL:-https://github.com/gowtham66867/Polaris.git}"
REVISION="${POLARIS_REVISION:-$(git rev-parse HEAD)}"

for command_name in aws git; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command is missing: ${command_name}" >&2
    exit 1
  fi
done

existing_instance_id="$(aws ec2 describe-instances \
  --region "${AWS_REGION}" \
  --filters \
    "Name=tag:Name,Values=${INSTANCE_NAME}" \
    'Name=instance-state-name,Values=pending,running,stopping,stopped' \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text)"

if [[ "${existing_instance_id}" != "None" ]]; then
  instance_id="${existing_instance_id}"
  state="$(aws ec2 describe-instances \
    --region "${AWS_REGION}" \
    --instance-ids "${instance_id}" \
    --query 'Reservations[0].Instances[0].State.Name' \
    --output text)"
  if [[ "${state}" == "stopped" ]]; then
    aws ec2 start-instances --region "${AWS_REGION}" --instance-ids "${instance_id}" >/dev/null
  fi
else
  vpc_id="$(aws ec2 describe-vpcs \
    --region "${AWS_REGION}" \
    --filters Name=is-default,Values=true \
    --query 'Vpcs[0].VpcId' \
    --output text)"
  if [[ "${vpc_id}" == "None" ]]; then
    echo "A default VPC is required in ${AWS_REGION}." >&2
    exit 1
  fi

  security_group_id="$(aws ec2 describe-security-groups \
    --region "${AWS_REGION}" \
    --filters "Name=vpc-id,Values=${vpc_id}" "Name=group-name,Values=${INSTANCE_NAME}" \
    --query 'SecurityGroups[0].GroupId' \
    --output text)"
  if [[ "${security_group_id}" == "None" ]]; then
    security_group_id="$(aws ec2 create-security-group \
      --region "${AWS_REGION}" \
      --vpc-id "${vpc_id}" \
      --group-name "${INSTANCE_NAME}" \
      --description 'Polaris synthetic demo HTTP access' \
      --query 'GroupId' \
      --output text)"
    aws ec2 authorize-security-group-ingress \
      --region "${AWS_REGION}" \
      --group-id "${security_group_id}" \
      --ip-permissions \
        'IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0,Description="Polaris public demo"}]' \
      >/dev/null
  fi

  ami_id="$(aws ssm get-parameter \
    --region "${AWS_REGION}" \
    --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
    --query 'Parameter.Value' \
    --output text)"

  user_data_file="$(mktemp)"
  trap 'rm -f "${user_data_file}"' EXIT
  cat >"${user_data_file}" <<USER_DATA
#!/bin/bash
set -euxo pipefail
dnf install -y docker git
systemctl enable --now docker
git clone "${REPOSITORY_URL}" /opt/polaris
cd /opt/polaris
git checkout "${REVISION}"
docker build --tag polaris-guidance:"${REVISION}" .
docker run --detach \
  --name polaris-guidance \
  --restart unless-stopped \
  --publish 80:8080 \
  --env POLARIS_AUTH_MODE=demo \
  --env POLARIS_DB_PATH=/tmp/polaris-guidance.db \
  --env POLARIS_HERMES_MODEL=anthropic/claude-opus-5 \
  polaris-guidance:"${REVISION}"
USER_DATA

  instance_id="$(aws ec2 run-instances \
    --region "${AWS_REGION}" \
    --image-id "${ami_id}" \
    --instance-type "${INSTANCE_TYPE}" \
    --security-group-ids "${security_group_id}" \
    --user-data "file://${user_data_file}" \
    --credit-specification CpuCredits=standard \
    --metadata-options 'HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1' \
    --block-device-mappings \
      'DeviceName=/dev/xvda,Ebs={VolumeSize=8,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
    --tag-specifications \
      "ResourceType=instance,Tags=[{Key=Name,Value=${INSTANCE_NAME}},{Key=Project,Value=Polaris},{Key=Environment,Value=hackathon-demo}]" \
      "ResourceType=volume,Tags=[{Key=Name,Value=${INSTANCE_NAME}},{Key=Project,Value=Polaris}]" \
    --query 'Instances[0].InstanceId' \
    --output text)"
fi

aws ec2 wait instance-running --region "${AWS_REGION}" --instance-ids "${instance_id}"
aws ec2 wait instance-status-ok --region "${AWS_REGION}" --instance-ids "${instance_id}"

public_dns="$(aws ec2 describe-instances \
  --region "${AWS_REGION}" \
  --instance-ids "${instance_id}" \
  --query 'Reservations[0].Instances[0].PublicDnsName' \
  --output text)"

echo "Polaris AWS deployment: http://${public_dns}"
echo "Instance: ${instance_id} (${INSTANCE_TYPE}, standard CPU credits)"
