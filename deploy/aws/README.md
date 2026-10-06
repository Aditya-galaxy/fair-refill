# Fair Refill on AWS

Puts the add-on and the simulated Alexa+ at a public HTTPS address, so it can
be tried without installing anything.

```bash
deploy/aws/deploy.sh       # build, push, create or update
deploy/aws/destroy.sh      # take it all down
```

When it finishes it prints three addresses: the simulated Alexa+ at `/`, the
add-on's MCP endpoint at `/mcp`, and `/health`.

## What it uses

| AWS service | For |
|---|---|
| Amazon ECR | The container image, built for ARM64 |
| Amazon ECS Express Mode, on Fargate | One task running the image, behind a load balancer with HTTPS |
| IAM | Two roles ECS needs: one to pull the image and write logs, one to manage the load balancer |
| CloudWatch Logs | The server's output |

ECS Express Mode is the service AWS points to now that App Runner is closed
to new customers (since 30 April 2026).

## Before you run it

1. An AWS account, with the default VPC still in place in the region you use.
2. The AWS CLI v2, recent enough to have `aws ecs create-express-gateway-service`, and signed in (`aws sts get-caller-identity` should print your account).
3. Docker with buildx. The image is built for ARM64; on an Intel machine Docker emulates it, which is slower but works.
4. Permission to use ECR, ECS and IAM. The script creates two IAM roles the first time.

Region: `AWS_REGION`, else your CLI's default, else `us-east-1`.

## What the container does differently from a laptop

The image sets four things (see `Dockerfile`):

- `FAIR_REFILL_HOST=0.0.0.0`: reachable from outside the container.
- `FAIR_REFILL_PUBLIC=1`: **each browser gets its own list of medicines.** On a laptop there is one list. On a shared server that would hand one visitor another's medicines, so the page makes up a long random key, keeps it in the browser, and sends it with each request; the server keeps that visitor's list under it. A request with no key gets no list, and is told so. The key is a secret, not an identity: on Alexa+ the account would take its place.
- `FAIR_REFILL_STATELESS=1`: nothing is kept between requests, so a new copy can take over during a deploy.
- `/data` for the price cache and the lists. It is the task's own disk: both start empty after every deploy or restart.

The service is held at exactly one task, so there is one cache and one set of
lists. For about ten minutes after a start it is looking up common medicines;
it answers during that, just more slowly.

## Cost

One Fargate task (1 vCPU, 2 GB, ARM64) and one load balancer, running all
day. From AWS's list prices that is roughly $1.50 to $2 a day in `us-east-1`.
That is an estimate, not a quote: check the AWS Pricing Calculator, and set a
budget alert. Run `destroy.sh` when judging ends (20 November 2026).

## What has and hasn't been checked

- Checked: the server run with exactly the container's settings, installed from only the files the image copies; `/health`; MCP requests carrying a public `Host` header; lists kept apart between two visitors; no list without a key.
- **Not checked: the Docker build and the AWS commands.** They were written from AWS's documentation on a machine with neither Docker nor the AWS CLI. Expect to fix something small on the first run. In particular the address printed at the end is the documented form (`https://<name>.ecs.<region>.on.aws`); the script also prints the command that shows the real one.

## It's public: what that means

Anyone with the address can use it. It holds no secrets and calls only public
price sources, but each uncached question makes a few requests to them. If it
is misused, `destroy.sh` is the off switch. People's lists are kept only under
their random keys, with no names, and vanish on restart.

## Bedrock AgentCore Runtime

AgentCore Runtime hosts MCP servers, and is one of the services the
hackathon's AWS Builder challenge names. The add-on runs on it unchanged.

```bash
npm install -g @aws/agentcore      # once
deploy/aws/agentcore.sh            # create or update, then call one tool
deploy/aws/agentcore.sh destroy    # remove it
```

The script creates an AgentCore project in `deploy/aws/.agentcore/` (not
committed), copies the add-on into it with the entrypoint and Dockerfile from
`deploy/aws/agentcore/`, registers it as an MCP runtime, and deploys.
AgentCore builds the image in AWS CodeBuild, so Docker isn't needed. Keep the
`.agentcore/` folder: later runs and `destroy` find the deployment through it.

### How it differs from the ECS deployment

| | ECS Express Mode (`deploy.sh`) | AgentCore Runtime (`agentcore.sh`) |
|---|---|---|
| What runs | The add-on and the simulated Alexa+ | The add-on only |
| Who can call it | Anyone with the address | Only signed-in callers: AWS credentials by default, or OAuth tokens |
| Good for | "Try it in a browser" | "An agent calls the add-on", which is how Alexa+ would use it |
| Price cache | One, kept warm | One per runtime session, starting empty, so the first check of a medicine takes 6 to 14 seconds |
| Saved lists | Per browser, until a restart | Per `X-Fair-Refill-List` key, for the life of the runtime session |

### What makes it fit

AgentCore's contract for an MCP server is Streamable HTTP at
`0.0.0.0:8000/mcp`, on ARM64, keeping nothing between requests, and accepting
the `Mcp-Session-Id` AgentCore adds. `deploy/aws/agentcore/main.py` sets
exactly that. `X-Fair-Refill-List`, the key a caller's list is kept under, is
put on the runtime's header allowlist so AgentCore passes it through.

### Signing in

By default callers sign requests with AWS credentials (IAM), which is what
`agentcore invoke` does for you. To accept OAuth tokens instead, set
`FAIR_REFILL_OIDC_DISCOVERY_URL` and `FAIR_REFILL_OIDC_CLIENT_ID` before the
first run; AWS's guide shows how to make a Cognito user pool for that:
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html

### What has and hasn't been checked

- Checked: the entrypoint run locally from only the files the script copies, on port 8000, with requests shaped as AgentCore sends them: a session ID the server never issued, tool calls with no handshake first, a list saved and read back under a key, and no list without one.
- **Not checked: the `agentcore` commands and the build.** They follow the CLI's reference (version 0.31.1) but have not been run. The parts most likely to need a fix on first run are `agentcore create` in a script, and whether `add agent --type byo --build Container` accepts the Dockerfile as placed.
- `agentcore deploy --dry-run` and `--diff`, run inside `deploy/aws/.agentcore/FairRefill`, show what would be made before anything is.
