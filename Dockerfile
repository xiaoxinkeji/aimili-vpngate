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

COPY proxy_server.py vpngate_manager.py vpn_utils.py metrics_exporter.py docker-stats.py self_update.py publicvpnlist_scraper.py ./
# Build-time Python syntax validation
RUN python3 -m py_compile proxy_server.py vpngate_manager.py vpn_utils.py metrics_exporter.py docker-stats.py self_update.py publicvpnlist_scraper.py
COPY docker-entrypoint.sh /usr/local/bin/

# docker-stats 快捷命令
RUN printf '#!/bin/sh\nexec python3 /opt/aimilivpn/docker-stats.py\n' > /usr/local/bin/docker-stats && \
    chmod +x /usr/local/bin/docker-entrypoint.sh /usr/local/bin/docker-stats && \
    mkdir -p /opt/aimilivpn/vpngate_data

# ── 构建时版本信息 (由 CI 注入) ──
ARG IMAGE_VERSION=dev
ARG BUILD_DATE=unknown
ARG GIT_COMMIT=unknown
ENV IMAGE_VERSION=${IMAGE_VERSION}
ENV BUILD_DATE=${BUILD_DATE}
ENV GIT_COMMIT=${GIT_COMMIT}

ENV VPNGATE_DATA_DIR=/opt/aimilivpn/vpngate_data
ENV LOCAL_PROXY_HOST=127.0.0.1
ENV LOCAL_PROXY_PORT=7928
ENV UI_HOST=::
ENV UI_PORT=8787
ENV METRICS_PORT=9798
ENV METRICS_ENABLED=true

EXPOSE 8787 7928 9798

# Must run as root: required for tun device creation, iptables NAT rules, and
# binding low-numbered ports with SO_BINDTODEVICE to tun0

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD pgrep -f vpngate_manager.py > /dev/null && \
        curl -sf --max-time 5 "http://localhost:${UI_PORT:-8787}/" > /dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
