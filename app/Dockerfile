# One image for a laptop (docker run -p 8080:8080) and for Lambda: the Lambda Web Adapter extension turns
# Lambda events into HTTP requests to uvicorn on port 8080, so the app has no Lambda-specific code.
# Base images are pinned by tag and digest; bump both together.
ARG PYTHON=python:3.13.18-slim-trixie@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

FROM ghcr.io/astral-sh/uv:0.9.30 AS uv

FROM ${PYTHON} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
# Dependencies first, so this layer is cached until uv.lock changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM ${PYTHON}
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0 /lambda-adapter /opt/extensions/lambda-adapter
COPY --from=build /opt/venv /opt/venv
# Debian security fixes the base image does not have yet (rebuilds pick up new ones), and no pip at run time:
# the app installs nothing, and pip's bundled libraries carry their own CVEs.
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && python -m pip uninstall --yes --quiet pip \
 && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    AWS_LWA_PORT=8080 \
    AWS_LWA_READINESS_CHECK_PATH=/health
USER 10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"]
CMD ["uvicorn", "shortlinks.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
