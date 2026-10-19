# The dispatch image (ADR 0030). Built by the pipeline from this directory,
# scanned, and pushed to the repository's registry from main only. The
# workflow pulls it by digest.
#
# The tool service's base image, pinned by the same digest: Python 3.15.0 on
# Alpine 3.24. It adds OpenSSH's client, which the tool service image must not
# carry, and the dispatch script, which uses the standard library only.
FROM python@sha256:ff4d3c9b1a48f646eedd93182aaea385c7a5452f4c8a8cd7cef686babacf4928

# OpenSSH's client from Alpine's signed index, unpinned on purpose: the index
# keeps only the current version, so a pin fails the build at the next
# security fix. The scan below blocks a known finding with a fix. The package
# manager and pip are removed, because nothing is installed at run time.
#
# ssh looks its user up by ID, so the fixed user gets an entry. Its home is
# the pod's memory-backed directory, where the key copy goes.
# hadolint ignore=DL3018
RUN apk add --no-cache openssh-client-default \
    && python -m pip uninstall --yes pip \
    && apk del --no-cache apk-tools \
    && echo "dispatch:x:65532:65532:dispatch:/run/dispatch:/sbin/nologin" >> /etc/passwd \
    && echo "dispatch:x:65532:" >> /etc/group

COPY dispatch.py /opt/dispatch/dispatch.py

# The pod runs with a read-only root file system, so nothing may expect to
# write: no byte code, no buffered output.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/run/dispatch

USER 65532:65532
LABEL org.opencontainers.image.source="https://github.com/sindredg/ai-security-platform" \
      org.opencontainers.image.description="The dispatch step: registers a job, hands it to the worker over SSH, and checks the result"
ENTRYPOINT ["python", "/opt/dispatch/dispatch.py"]
