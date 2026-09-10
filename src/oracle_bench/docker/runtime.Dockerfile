ARG AGENT_IMAGE
ARG PROJECT_IMAGE

FROM ${AGENT_IMAGE} AS agent
FROM ${PROJECT_IMAGE}

USER root
ARG PROJECT_PYTHON
ARG PROJECT_PYTHON_DIR
ARG PYTEST_VERSION
ARG COVERAGE_VERSION

COPY --from=agent /usr/local/bin/node /opt/oracle-node/node
COPY --from=agent /opt/oracle-agent /opt/oracle-agent
COPY container_helpers/ /opt/oracle-bench/container-helpers/

ENV PATH="${PROJECT_PYTHON_DIR}:/opt/oracle-node:/opt/oracle-agent/node_modules/.bin:${PATH}"

RUN "${PROJECT_PYTHON}" -m pip install \
    "pytest==${PYTEST_VERSION}" \
    "coverage==${COVERAGE_VERSION}"
RUN useradd --create-home --uid 10001 oracle
