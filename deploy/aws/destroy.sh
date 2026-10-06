#!/usr/bin/env bash
# Remove what deploy.sh made: the service and its load balancer, and the images.
# The two IAM roles are left; other ECS services in the account may use them.
#
#   deploy/aws/destroy.sh
set -euo pipefail

NAME="${FAIR_REFILL_NAME:-fair-refill}"
REGION="${AWS_REGION:-$(aws configure get region || true)}"
REGION="${REGION:-us-east-1}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
SERVICE_ARN="arn:aws:ecs:${REGION}:${ACCOUNT}:service/default/${NAME}"

read -r -p "Delete the ${NAME} service and its images in ${REGION} (account ${ACCOUNT})? [y/N] " answer
[ "$answer" = "y" ] || { echo "Nothing deleted."; exit 0; }

echo "==> Service"
aws ecs delete-express-gateway-service --region "$REGION" --service-arn "$SERVICE_ARN" --monitor-resources ||
  echo "    no service deleted (already gone?)"

echo "==> ECR repository and its images"
aws ecr delete-repository --region "$REGION" --repository-name "$NAME" --force >/dev/null ||
  echo "    no repository deleted (already gone?)"

echo "Done. Check the ECS and EC2 load balancer consoles in ${REGION} to confirm nothing is left running."
