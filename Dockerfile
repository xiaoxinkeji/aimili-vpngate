FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -q && \
    apt-get install -y --no-install-recommends \
        python3 \
        openvpn \
        iptables \
        iproute2 \
        ca-certificates \
        curl \
        procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/aimilivpn

COPY proxy_server.py vpngate_manager.py vpn_utils.py ./
COPY docker-entrypoint.sh /usr/local/bin/
COPY docker-stats.sh /usr/local/bin/

RUN chmod +x /usr/local/bin/docker-entrypoint.sh /usr/local/bin/docker-stats.sh && \
    mkdir -p /opt/aimilivpn/vpngate_data

ENV VPNGATE_DATA_DIR=/opt/aimilivpn/vpngate_data
ENV LOCAL_PROXY_HOST=127.0.0.1
ENV LOCAL_PROXY_PORT=7928
ENV UI_HOST=::
ENV UI_PORT=8787

EXPOSE 8787 7928

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD pgrep -f vpngate_manager.py > /dev/null && \
        curl -sf --max-time 5 http://localhost:8787/ > /dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
