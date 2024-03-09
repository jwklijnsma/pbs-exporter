FROM ubuntu:22.04
LABEL maintainer="janwiebe@janwiebe.eu"

# Install necessary packages
RUN apt-get update
RUN apt-get install -y nodejs npm wget

COPY --from=build_node_modules /app /app
WORKDIR /app

# Install necessary packages
RUN apt-get update && \
    apt-get install -y \
    python3 \
    jw && \
    rm -rf /var/lib/apt/lists/*

# Enable this to run `npm run serve`
RUN npm i -g nodemon

# Expose Ports
EXPOSE 51820/udp
EXPOSE 51821/tcp

# Set Environment
ENV DEBUG=Server,WireGuard

# Run Web UI
WORKDIR /app
CMD ["/usr/bin/dumb-init", "node", "server.js"]