FROM ghcr.io/astral-sh/uv:python3.13-bookworm

# Install Docker CLI (for sibling containers) and git
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker.io \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN adduser --disabled-password agent
USER agent
WORKDIR /home/agent

COPY --chown=agent pyproject.toml uv.lock README.md ./
COPY --chown=agent src src
COPY --chown=agent config config

RUN \
    --mount=type=cache,target=/home/agent/.cache/uv,uid=1000 \
    uv sync --locked

ENTRYPOINT ["uv", "run", "src/server.py"]
CMD ["--host", "0.0.0.0"]
EXPOSE 9009
