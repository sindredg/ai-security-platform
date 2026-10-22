# The tool service image. Built by the pipeline from this directory, scanned,
# and pushed to the repository's registry from main only. The orchestrator
# pulls it by digest.
#
# Both stages start from the image the tests run on, pinned by digest: Python
# 3.15.1 on Alpine 3.24. Alpine because its 30 system packages had no known
# vulnerability when 3.15.0 was first pinned, against 164 for the Debian slim
# image. 3.15.1 since 2026-10-22: its musl 1.2.6-r3 fixes CVE-2026-107891.
# Nothing here is fetched except the packages in requirements.txt, and pip
# refuses any file whose hash is not listed there.
FROM python@sha256:54448f67d7c31c39e5cdd3ea2d6382395ce142806c284425f8e897d78a0465b3 AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-deps --require-hashes -r /tmp/requirements.txt \
    && /opt/venv/bin/pip uninstall --yes pip

FROM python@sha256:54448f67d7c31c39e5cdd3ea2d6382395ce142806c284425f8e897d78a0465b3

# The base image's own pip is not needed at run time. It also carries its own
# copies of urllib3 and msgpack, which is where the base image's only known
# findings were. The package manager is removed too, because nothing is
# installed at run time.
RUN python -m pip uninstall --yes pip \
    && apk del --no-cache apk-tools

COPY --from=build /opt/venv /opt/venv
COPY aisec_tools /opt/aisec-tools/aisec_tools

# The pod runs with a read-only root file system, so nothing may expect to
# write: no byte code, no buffered output. The user is fixed so the pod's
# security context can name it.
ENV PATH=/opt/venv/bin:/usr/local/bin:/usr/bin:/bin \
    PYTHONPATH=/opt/aisec-tools \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AISEC_ROOT=/aisec

USER 65532:65532
WORKDIR /opt/aisec-tools
EXPOSE 8443 8444
LABEL org.opencontainers.image.source="https://github.com/sindredg/ai-security-platform" \
      org.opencontainers.image.description="The tool service: one MCP server that checks every tool call"
ENTRYPOINT ["python", "-m", "aisec_tools"]
