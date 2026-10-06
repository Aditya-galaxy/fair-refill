#!/usr/bin/env bash
# Run the Fair Refill add-on on Amazon Bedrock AgentCore Runtime, as an MCP server.
#
#   deploy/aws/agentcore.sh            # create or update, then call one tool to prove it answers
#   deploy/aws/agentcore.sh destroy    # remove it
#
# Needs: Node.js, the AgentCore CLI (`npm install -g @aws/agentcore`), the AWS
# CLI v2, and credentials for a region where AgentCore is available. Docker is
# not needed: AgentCore builds the image in AWS CodeBuild.
#
# Callers must sign their requests with AWS credentials (IAM). To take OAuth
# tokens instead, set both of these before the first run:
#   FAIR_REFILL_OIDC_DISCOVERY_URL   e.g. https://cognito-idp.<region>.amazonaws.com/<pool>/.well-known/openid-configuration
#   FAIR_REFILL_OIDC_CLIENT_ID
#
# The AgentCore project it generates lives in deploy/aws/.agentcore/ (not
# committed). Keep that folder: it is how later runs find what they deployed.
set -euo pipefail

PROJECT="FairRefill"          # AgentCore: letters and digits, starts with a letter, at most 23
AGENT="FairRefill"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WORK="$HERE/.agentcore"
PROJECT_DIR="$WORK/$PROJECT"
CODE_DIR="$PROJECT_DIR/app/$AGENT"

for tool in agentcore aws; do
  command -v "$tool" >/dev/null || { echo "Missing '$tool'. See the top of this script." >&2; exit 1; }
done

if [ "${1:-}" = "destroy" ]; then
  [ -d "$PROJECT_DIR" ] || { echo "Nothing to remove: $PROJECT_DIR doesn't exist."; exit 0; }
  cd "$PROJECT_DIR"
  agentcore remove all --dry-run
  read -r -p "Remove all of the above from AWS? [y/N] " answer
  [ "$answer" = "y" ] || { echo "Nothing removed."; exit 0; }
  agentcore remove all -y
  agentcore deploy -y            # removal takes effect on deploy
  echo "Removed. deploy/aws/.agentcore/ can be deleted now."
  exit 0
fi

REGION="${AWS_REGION:-$(aws configure get region || true)}"
REGION="${REGION:-us-east-1}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
echo "==> ${AGENT} to AgentCore Runtime, account ${ACCOUNT}, region ${REGION}"

if [ ! -d "$PROJECT_DIR/agentcore" ]; then
  echo "==> New AgentCore project"
  mkdir -p "$WORK"
  (cd "$WORK" && agentcore create --project-name "$PROJECT" --no-agent --skip-git --skip-install)
fi

echo "==> Copy the add-on into the project"
rm -rf "$CODE_DIR"
mkdir -p "$CODE_DIR"
cp -R "$ROOT/fair_refill" "$ROOT/skills" "$CODE_DIR/"
cp "$ROOT/pyproject.toml" "$ROOT/README.md" "$ROOT/LICENSE" "$CODE_DIR/"
cp "$HERE/agentcore/main.py" "$HERE/agentcore/Dockerfile" "$CODE_DIR/"
cp "$HERE/agentcore/dockerignore" "$CODE_DIR/.dockerignore"
find "$CODE_DIR" -name __pycache__ -type d -prune -exec rm -rf {} +

cd "$PROJECT_DIR"

# Where it deploys to.
cat > agentcore/aws-targets.json <<TARGET
[
  { "name": "default", "description": "Fair Refill (${REGION})", "account": "${ACCOUNT}", "region": "${REGION}" }
]
TARGET

if ! grep -q "\"name\": *\"${AGENT}\"" agentcore/agentcore.json; then
  echo "==> Register the add-on as an MCP runtime"
  auth=(--authorizer-type AWS_IAM)
  if [ -n "${FAIR_REFILL_OIDC_DISCOVERY_URL:-}" ] && [ -n "${FAIR_REFILL_OIDC_CLIENT_ID:-}" ]; then
    auth=(--authorizer-type CUSTOM_JWT --discovery-url "$FAIR_REFILL_OIDC_DISCOVERY_URL"
          --allowed-clients "$FAIR_REFILL_OIDC_CLIENT_ID")
  fi
  # X-Fair-Refill-List is the key a caller's list of medicines is kept under
  # (fair_refill/cabinet.py). AgentCore forwards only the headers named here.
  agentcore add agent --name "$AGENT" --type byo --build Container --language Python \
    --code-location "app/$AGENT" --entrypoint main.py --protocol MCP \
    --request-header-allowlist X-Fair-Refill-List "${auth[@]}"
fi

echo "==> Deploy (the first one builds the image and takes several minutes)"
agentcore deploy -y

echo "==> Status"
agentcore status --runtime "$AGENT"

echo "==> One tool call, to prove it answers"
agentcore invoke call-tool --runtime "$AGENT" --tool medicare_drug_cost_limits --input '{}' ||
  echo "    The call failed. If the runtime uses OAuth, add --bearer-token; see deploy/aws/README.md."

cat <<DONE

  Deployed. The runtime's ARN is in the status above. MCP clients reach it at:
    https://bedrock-agentcore.${REGION}.amazonaws.com/runtimes/<URL-encoded ARN>/invocations?qualifier=DEFAULT

  Try a price check:
    (cd "$PROJECT_DIR" && agentcore invoke call-tool --runtime "$AGENT" \\
       --tool check_prescription_price --input '{"medicine": "atorvastatin 20 mg", "you_pay_per_month": 40}')

  Take it down with: deploy/aws/agentcore.sh destroy
DONE
