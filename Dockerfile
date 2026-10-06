# Fair Refill: the add-on (MCP at /mcp) and the simulated Alexa+ (at /), one process.
#
#   docker build -t fair-refill .
#   docker run --rm -p 8080:8080 fair-refill        # http://localhost:8080
#
# deploy/aws/ builds this for ARM64 and runs it on AWS.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# The package is installed in place: it reads the Agent Skill from skills/
# beside it, as it does in a checkout.
COPY pyproject.toml README.md LICENSE ./
COPY fair_refill ./fair_refill
COPY skills ./skills
RUN pip install -e .

# Runs as an ordinary user. /data holds the price cache and people's lists;
# both are rebuilt or empty after a restart, which is fine for a demo.
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app /data
USER app

# Reachable from outside the container, one list of medicines per browser,
# and nothing kept between requests so any copy can answer any of them.
ENV FAIR_REFILL_HOST=0.0.0.0 \
    FAIR_REFILL_PORT=8080 \
    FAIR_REFILL_PUBLIC=1 \
    FAIR_REFILL_STATELESS=1 \
    FAIR_REFILL_CACHE=/data/cache \
    FAIR_REFILL_STATE=/data/state

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"FAIR_REFILL_PORT\"]}/health', timeout=4)"

CMD ["python", "-m", "fair_refill.simulator"]
