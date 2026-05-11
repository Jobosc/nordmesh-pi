FROM debian:bookworm-slim

# System dependencies (NordVPN needs iptables/iproute2 at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    iptables \
    iproute2 \
    procps \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install NordVPN via official apt repository (avoids systemd issues in Docker)
RUN curl -fsSL https://repo.nordvpn.com/gpg/nordvpn_public.asc \
        | gpg --dearmor -o /etc/apt/keyrings/nordvpn.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nordvpn.gpg] https://repo.nordvpn.com/deb/nordvpn/debian stable main" \
        > /etc/apt/sources.list.d/nordvpn.list \
    && apt-get update \
    && apt-get install -y nordvpn \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Install Python deps as a cached layer before copying app code
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# Copy application
COPY app.py nordvpn.py ./
COPY templates/ templates/

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["docker-entrypoint.sh"]
