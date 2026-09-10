ARG NODE_IMAGE
FROM ${NODE_IMAGE}

ARG AGENT_VERSION
RUN npm install --prefix /opt/oracle-agent "@anthropic-ai/claude-code@${AGENT_VERSION}"
