FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# 安装系统依赖: openvpn, python3, 网络工具
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

# 数据目录
RUN mkdir -p /opt/aimilivpn/vpngate_data

# 环境变量默认值
ENV VPNGATE_DATA_DIR=/opt/aimilivpn/vpngate_data
ENV LOCAL_PROXY_HOST=127.0.0.1
ENV LOCAL_PROXY_PORT=7928
ENV UI_HOST=::
ENV UI_PORT=8787

EXPOSE 8787 7928

COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
