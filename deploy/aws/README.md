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

## Bedrock AgentCore Runtime (optional)

AgentCore Runtime hosts MCP servers and is one of the services the
hackathon's AWS Builder challenge names. The add-on already meets its
contract for MCP: Streamable HTTP at `0.0.0.0:8000/mcp`, stateless, ARM64.
Run the add-on alone, on that port:

```bash
FAIR_REFILL_HOST=0.0.0.0 FAIR_REFILL_PORT=8000 FAIR_REFILL_STATELESS=1 \
FAIR_REFILL_PUBLIC=1 python -m fair_refill.server
```

Two things to know before choosing it:

- **It isn't a public address.** AgentCore requires each caller to sign in (IAM, or OAuth through Cognito or another provider), so judges couldn't just open it. It suits "Alexa+ calls the add-on", not "try it in a browser".
- It needs its own setup (the `agentcore` CLI and an OAuth user pool), which isn't scripted here. AWS's guide: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html
