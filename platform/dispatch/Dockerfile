# The dispatch image (ADR 0030), which also runs the comparison step (ADR
# 0041). Built by the pipeline from this directory, scanned, and pushed to the
# repository's registry from main only. The workflow pulls it by digest.
#
# The tool service's base image, pinned by the same digest: Python 3.15.2 on
# Alpine 3.24. It adds OpenSSH's client, which the tool service image must not
# carry, and the dispatch and comparison scripts, which use the standard
# library only.
FROM python@sha256:a0f2e268f2ce8f3709611a90054ec6a8ae31f6251f5896b8648b9bb99835e30a

# Pin zlib to Alpine's fix for CVE-2026-4738; the base still has 1.3.2-r1.
# Both Python test containers install the same fixed package.
# OpenSSH's client from Alpine's signed index, unpinned on purpose: the index
# keeps only the current version, so a pin fails the build at the next
# security fix. The scan below blocks a known finding with a fix. The package
# manager and pip are removed, because nothing is installed at run time.
#
# ssh looks its user up by ID, so the fixed user gets an entry. Its home is
# the pod's memory-backed directory, where the key copy goes.
# hadolint ignore=DL3018
RUN apk add --no-cache openssh-client-default zlib=1.4-r0 \
    && python -m pip uninstall --yes pip \
    && apk del --no-cache apk-tools \
    && echo "dispatch:x:65532:65532:dispatch:/run/dispatch:/sbin/nologin" >> /etc/passwd \
    && echo "dispatch:x:65532:" >> /etc/group

COPY dispatch.py compare.py /opt/dispatch/

# The pod runs with a read-only root file system, so nothing may expect to
# write: no byte code, no buffered output.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/run/dispatch

USER 65532:65532
LABEL org.opencontainers.image.source="https://github.com/sindredg/ai-security-platform" \
      org.opencontainers.image.description="The dispatch and comparison steps: registers a job, hands it to the worker over SSH, checks the result, and compares the model's verdict with the checks'"
ENTRYPOINT ["python", "/opt/dispatch/dispatch.py"]
