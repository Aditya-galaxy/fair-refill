# Fair Refill for Amazon Bedrock AgentCore Runtime: the add-on alone, on the
# port and path AgentCore expects of an MCP server (0.0.0.0:8000/mcp).
#
# deploy/aws/agentcore.sh copies this beside the package and `agentcore deploy`
# builds it for ARM64 in AWS CodeBuild. No local Docker is needed.
FROM public.ecr.aws/docker/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Installed in place: the add-on reads its Agent Skill from skills/ beside it.
COPY pyproject.toml README.md LICENSE ./
COPY fair_refill ./fair_refill
COPY skills ./skills
RUN pip install -e .
COPY main.py ./

RUN useradd --create-home --uid 1000 bedrock_agentcore && mkdir -p /data && chown bedrock_agentcore /data
USER bedrock_agentcore

ENV FAIR_REFILL_HOST=0.0.0.0 \
    FAIR_REFILL_PORT=8000 \
    FAIR_REFILL_STATELESS=1 \
    FAIR_REFILL_PUBLIC=1 \
    FAIR_REFILL_PREWARM=0 \
    FAIR_REFILL_CACHE=/data/cache \
    FAIR_REFILL_STATE=/data/state

EXPOSE 8000
CMD ["python", "main.py"]
