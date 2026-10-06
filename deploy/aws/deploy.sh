#!/usr/bin/env bash
# Build Fair Refill and run it on AWS, at a public HTTPS address.
#
#   deploy/aws/deploy.sh            # first run creates everything; later runs ship a new build
#
# Needs: the AWS CLI v2 (a recent one, for `ecs create-express-gateway-service`),
# Docker with buildx, and credentials that can use ECR, ECS and IAM.
# Region comes from AWS_REGION, then your CLI's default, then us-east-1.
#
# What it makes: an ECR repository, two IAM roles, and one Amazon ECS Express
# Mode service (one Fargate task behind a load balancer). deploy/aws/destroy.sh
# removes them.
set -euo pipefail

NAME="${FAIR_REFILL_NAME:-fair-refill}"
REGION="${AWS_REGION:-$(aws configure get region || true)}"
REGION="${REGION:-us-east-1}"
EXECUTION_ROLE="ecsTaskExecutionRole"
INFRA_ROLE="ecsInfrastructureRoleForExpressServices"

cd "$(dirname "$0")/../.."

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
TAG="$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)"
IMAGE="${REGISTRY}/${NAME}:${TAG}"
SERVICE_ARN="arn:aws:ecs:${REGION}:${ACCOUNT}:service/default/${NAME}"

echo "==> ${NAME} to account ${ACCOUNT}, region ${REGION}, image tag ${TAG}"

echo "==> ECR repository"
aws ecr describe-repositories --region "$REGION" --repository-names "$NAME" >/dev/null 2>&1 ||
  aws ecr create-repository --region "$REGION" --repository-name "$NAME" \
    --image-scanning-configuration scanOnPush=true >/dev/null

echo "==> Build for ARM64 and push"
aws ecr get-login-password --region "$REGION" |
  docker login --username AWS --password-stdin "$REGISTRY" >/dev/null
docker buildx build --platform linux/arm64 --tag "$IMAGE" --push .

echo "==> IAM roles"
ensure_role() { # name, trusted service, managed policy ARN
  if ! aws iam get-role --role-name "$1" >/dev/null 2>&1; then
    aws iam create-role --role-name "$1" --assume-role-policy-document "{
      \"Version\": \"2012-10-17\",
      \"Statement\": [{\"Effect\": \"Allow\", \"Principal\": {\"Service\": \"$2\"}, \"Action\": \"sts:AssumeRole\"}]
    }" >/dev/null
    CREATED_A_ROLE=1
  fi
  aws iam attach-role-policy --role-name "$1" --policy-arn "$3"
}
CREATED_A_ROLE=0
ensure_role "$EXECUTION_ROLE" ecs-tasks.amazonaws.com \
  arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
ensure_role "$INFRA_ROLE" ecs.amazonaws.com \
  arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices
if [ "$CREATED_A_ROLE" = 1 ]; then
  echo "    new roles take about a minute to become usable; waiting"
  sleep 60
fi

# One task, always: the price cache and people's lists live on its disk.
CONTAINER="{\"image\":\"${IMAGE}\",\"containerPort\":8080}"
SCALING='{"minTaskCount":1,"maxTaskCount":1}'

if aws ecs describe-express-gateway-service --region "$REGION" --service-arn "$SERVICE_ARN" >/dev/null 2>&1; then
  echo "==> Update the service"
  aws ecs update-express-gateway-service --region "$REGION" --service-arn "$SERVICE_ARN" \
    --primary-container "$CONTAINER" --health-check-path /health --scaling-target "$SCALING" \
    --monitor-resources
else
  echo "==> Create the service (a few minutes: it sets up a load balancer and a certificate)"
  aws ecs create-express-gateway-service --region "$REGION" --service-name "$NAME" \
    --execution-role-arn "arn:aws:iam::${ACCOUNT}:role/${EXECUTION_ROLE}" \
    --infrastructure-role-arn "arn:aws:iam::${ACCOUNT}:role/${INFRA_ROLE}" \
    --primary-container "$CONTAINER" --cpu-architecture ARM64 \
    --health-check-path /health --scaling-target "$SCALING" \
    --monitor-resources
fi

URL="https://${NAME}.ecs.${REGION}.on.aws"
cat <<DONE

  Simulated Alexa+   ${URL}/
  The add-on (MCP)   ${URL}/mcp
  Health             ${URL}/health

  The address above is the usual form. If it doesn't answer, the real one is in:
    aws ecs describe-express-gateway-service --region ${REGION} --service-arn ${SERVICE_ARN}

  The first ten minutes are slow while it looks up common medicines.
  Take it down with deploy/aws/destroy.sh when judging ends.
DONE
