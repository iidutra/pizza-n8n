FROM n8nio/n8n:latest

# Railway usa a variavel PORT automaticamente
ENV N8N_PORT=${PORT:-5678}

USER root
RUN mkdir -p /home/node/.n8n && chown -R node:node /home/node/.n8n
USER node

EXPOSE ${PORT:-5678}
