#!/usr/bin/env bash
# ─── AimiliVPN + X-MILI 联合一键部署脚本 ───
# 支持 Docker 和二进制两种部署模式
# 用法:
#   curl -Ls https://raw.githubusercontent.com/xiaoxinkeji/aimili-vpngate/main/xmili-integration/install.sh | bash
# 或:
#   bash xmili-integration/install.sh [--docker|--binary]
set -e

# ─── 颜色 ───
RD='\033[0;31m'; GR='\033[0;32m'; YW='\033[0;33m'; BL='\033[0;34m'; NC='\033[0m'
log()    { echo -e "${GR}[+]${NC} $*"; }
warn()   { echo -e "${YW}[!]${NC} $*"; }
err()    { echo -e "${RD}[-]${NC} $*" >&2; exit 1; }
info()   { echo -e "${BL}[*]${NC} $*"; }

[[ $EUID -ne 0 ]] && err "请使用 root 运行"

# ─── 变量 ───
REPO="https://github.com/xiaoxinkeji/aimili-vpngate"
RELEASE_URL="${REPO}/releases/latest/download"
INSTALL_DIR="/opt/aimili-xmili"
DATA_DIR="/opt/aimili-xmili/data"
XMILI_DIR="/opt/aimili-xmili/x-mili"
XMILI_DB="/etc/x-ui"
AIMILI_PORT="${AIMILI_PORT:-8787}"
AIMILI_PROXY_PORT="${AIMILI_PROXY_PORT:-7928}"
XMILI_PORT="${XMILI_PORT:-}"

# ─── 令牌生成 ───
generate_token() { head -c 32 /dev/urandom | base64 | tr -d '+/=' | head -c 48; }

# ─── 系统检测 ───
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VER=$VERSION_ID
    elif [ -f /etc/debian_version ]; then
        OS="debian"
    elif [ -f /etc/redhat-release ]; then
        OS="rhel"
    else
        OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    fi
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64)  ARCH="amd64" ;;
        aarch64) ARCH="arm64" ;;
        armv7l)  ARCH="armv7" ;;
    esac
    log "检测到系统: ${OS} ${OS_VER:-} / ${ARCH}"
}

# ─── 依赖安装 ───
install_deps() {
    log "安装系统依赖..."
    case "$OS" in
        debian|ubuntu)
            apt-get -o DPkg::Lock::Timeout=1800 update -qq
            apt-get -o DPkg::Lock::Timeout=1800 install -y -qq ca-certificates curl tar gzip openvpn iptables iproute2
            ;;
        rhel|centos|fedora|rocky|almalinux)
            if command -v dnf >/dev/null 2>&1; then
                dnf install -y ca-certificates curl tar gzip openvpn iptables iproute
            else
                yum install -y ca-certificates curl tar gzip openvpn iptables iproute
            fi
            ;;
        arch|manjaro)
            pacman -S --noconfirm ca-certificates curl tar gzip openvpn iptables iproute2
            ;;
        alpine)
            apk add --no-cache ca-certificates curl tar gzip openvpn iptables iproute2
            ;;
        *)
            warn "未识别的系统: $OS, 尝试 apt-get"
            apt-get update && apt-get install -y ca-certificates curl tar gzip openvpn iptables iproute2 || true
            ;;
    esac
}

# ─── TUN 检查 ───
check_tun() {
    log "检查 TUN 设备..."
    if [ ! -c /dev/net/tun ]; then
        warn "/dev/net/tun 不存在, 尝试加载 tun 模块..."
        modprobe tun 2>/dev/null || true
        if [ ! -c /dev/net/tun ]; then
            err "无法加载 tun 模块。请确保 VPS 支持 TUN/TAP"
        fi
    fi
    if [ ! -e /dev/net/tun ]; then
        mkdir -p /dev/net && mknod /dev/net/tun c 10 200 2>/dev/null || true
    fi
    log "TUN 设备: OK"
}

# ─── 内核参数 ───
setup_sysctl() {
    log "配置内核参数..."
    cat > /etc/sysctl.d/99-aimili-xmili.conf <<'SYSCTL'
net.ipv4.conf.all.rp_filter=2
net.ipv4.conf.default.rp_filter=2
net.ipv4.ip_forward=1
SYSCTL
    sysctl -p /etc/sysctl.d/99-aimili-xmili.conf >/dev/null 2>&1
}

# ─── 防火墙 ───
setup_firewall() {
    local ports="$AIMILI_PORT"
    log "配置防火墙端口: $ports"
    if command -v ufw >/dev/null 2>&1; then
        for p in $ports; do ufw allow "$p/tcp" 2>/dev/null || true; done
    elif command -v firewall-cmd >/dev/null 2>&1; then
        for p in $ports; do firewall-cmd --permanent --add-port="$p/tcp" 2>/dev/null || true; done
        firewall-cmd --reload 2>/dev/null || true
    elif command -v iptables >/dev/null 2>&1; then
        for p in $ports; do
            iptables -I INPUT -p tcp --dport "$p" -j ACCEPT 2>/dev/null || true
        done
        if command -v iptables-save >/dev/null 2>&1; then
            iptables-save > /etc/iptables/rules.v4 2>/dev/null || true
        fi
    fi
}

# ─── 二进制下载辅助 ───
download_and_extract() {
    local url="$1" local_bin="$2" local_name="$3" local_archive="$4"
    log "下载 ${local_name} (${ARCH})..."
    curl -fL --progress-bar -o "$local_archive" "$url" || return 1
    tar xzf "$local_archive" -C "$INSTALL_DIR"
    rm -f "$local_archive"
    chmod +x "$local_bin"
    log "${local_name} 安装完成"
}

# ─── 二进制部署 ───
deploy_binary() {
    log "=== 二进制部署模式 ==="
    install_deps
    check_tun
    setup_sysctl

    mkdir -p "$INSTALL_DIR" "$DATA_DIR" "$XMILI_DIR" "$XMILI_DB"

    local tmp_dir=$(mktemp -d)
    trap "rm -rf $tmp_dir" EXIT

    # ─── 下载 aimili-vpngate 二进制 ───
    # Release asset: aimilivpn-linux-${ARCH}.tar.gz → aimilivpn binary
    local aimili_bin="$INSTALL_DIR/aimili-vpngate"
    if [ ! -f "$aimili_bin" ] || [ "${FORCE_UPDATE:-}" = "1" ]; then
        local aimili_archive="${tmp_dir}/aimilivpn-linux-${ARCH}.tar.gz"
        local aimili_url="${RELEASE_URL}/aimilivpn-linux-${ARCH}.tar.gz"
        if ! curl -fL --progress-bar -o "$aimili_archive" "$aimili_url"; then
            err "下载 aimili-vpngate 失败 (${aimili_url})"
        fi
        tar xzf "$aimili_archive" -C "$tmp_dir"
        local extracted_bin=$(find "$tmp_dir" -name "aimilivpn" -type f 2>/dev/null | head -1)
        if [ -z "$extracted_bin" ]; then
            extracted_bin="$tmp_dir/aimilivpn"
        fi
        mv "$extracted_bin" "$aimili_bin" 2>/dev/null || cp "$tmp_dir/aimilivpn" "$aimili_bin"
        chmod +x "$aimili_bin"
        rm -f "$aimili_archive" "$tmp_dir/aimilivpn" "$tmp_dir/version.txt" 2>/dev/null
        log "aimili-vpngate 安装完成"
    fi

    # ─── 下载 X-MILI 集成版二进制 ───
    # Release asset: x-mili-integrated-linux-${ARCH}.tar.gz → x-mili-integrated binary
    local xmili_bin="$XMILI_DIR/x-ui"
    if [ ! -f "$xmili_bin" ] || [ "${FORCE_UPDATE:-}" = "1" ]; then
        local xmili_archive="${tmp_dir}/x-mili-integrated-linux-${ARCH}.tar.gz"
        local xmili_url="${RELEASE_URL}/x-mili-integrated-linux-${ARCH}.tar.gz"
        if curl -fL --progress-bar -o "$xmili_archive" "$xmili_url"; then
            tar xzf "$xmili_archive" -C "$tmp_dir"
            local extracted_bin=$(find "$tmp_dir" -name "x-mili-integrated" -type f 2>/dev/null | head -1)
            if [ -z "$extracted_bin" ]; then
                extracted_bin="$tmp_dir/x-mili-integrated"
            fi
            mv "$extracted_bin" "$xmili_bin" 2>/dev/null || cp "$tmp_dir/x-mili-integrated" "$xmili_bin"
            chmod +x "$xmili_bin"
            rm -f "$xmili_archive" "$tmp_dir/x-mili-integrated" 2>/dev/null
            log "X-MILI 集成版安装完成"
        else
            warn "未找到预构建的 X-MILI 集成版二进制，尝试使用标准版..."
            local xmili_std_url="https://github.com/Aimilibot/X-MILI/releases/latest/download/x-ui-${ARCH}"
            curl -fL --progress-bar -o "$xmili_bin" "$xmili_std_url" || err "下载 X-MILI 失败。请使用 Docker 部署模式。"
            chmod +x "$xmili_bin"
        fi
    fi

    # ─── 生成配置 ───
    local token_file="$INSTALL_DIR/.xmili_token"
    if [ -f "$token_file" ]; then
        X_MILI_TOKEN=$(cat "$token_file")
    else
        X_MILI_TOKEN=$(generate_token)
        echo "$X_MILI_TOKEN" > "$token_file"
        chmod 600 "$token_file"
    fi

    # ─── 创建 aimili-vpngate systemd 服务 ───
    cat > /etc/systemd/system/aimili-vpngate.service <<SVC
[Unit]
Description=AimiliVPN — VPN Node Manager
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${aimili_bin} \\
    --data-dir ${DATA_DIR} \\
    --host :: \\
    --port ${AIMILI_PORT} \\
    --proxy-port ${AIMILI_PROXY_PORT}
Environment=X_MILI_TOKEN=${X_MILI_TOKEN}
Environment=VPNGATE_DATA_DIR=${DATA_DIR}
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SVC

    # ─── 创建 X-MILI systemd 服务 ───
    cat > /etc/systemd/system/x-mili.service <<SVC
[Unit]
Description=X-MILI — Xray Proxy Panel
After=network-online.target aimili-vpngate.service
Wants=network-online.target aimili-vpngate.service

[Service]
Type=simple
WorkingDirectory=${XMILI_DIR}
ExecStart=${xmili_bin}
Environment=AIMILI_NODE_API=http://127.0.0.1:${AIMILI_PORT}
Environment=X_MILI_TOKEN=${X_MILI_TOKEN}
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SVC

    # ─── 重载并启动服务 ───
    systemctl daemon-reload
    systemctl enable aimili-vpngate x-mili
    systemctl restart aimili-vpngate
    sleep 3
    systemctl restart x-mili

    # ─── 输出面板信息 ───
    show_binary_info
}

show_binary_info() {
    echo ""
    echo "================================================"
    echo "  AimiliVPN + X-MILI 部署完成!"
    echo "================================================"
    echo ""
    echo "  AimiliVPN 面板: http://<服务器IP>:${AIMILI_PORT}/"
    echo "  AimiliVPN 代理: http://127.0.0.1:${AIMILI_PROXY_PORT}"
    echo ""
    echo "  查看 X-MILI 面板信息:"
    echo "    journalctl -u x-mili --no-pager | grep -E '面板|登录|密码|端口'"
    echo "    x-ui settings"
    echo ""
    echo "  管理命令:"
    echo "    systemctl status aimili-vpngate x-mili"
    echo "    systemctl restart aimili-vpngate x-mili"
    echo "    x-ui        # X-MILI 管理菜单"
    echo ""
    echo "  令牌文件: ${INSTALL_DIR}/.xmili_token"
    echo "================================================"
}

# ─── Docker 部署 ───
deploy_docker() {
    log "=== Docker 部署模式 ==="

    if ! command -v docker >/dev/null 2>&1; then
        err "Docker 未安装。请先安装 Docker 后重试，或使用 '--binary' 二进制模式。"
    fi
    if ! docker compose version >/dev/null 2>&1 && ! docker-compose version >/dev/null 2>&1; then
        err "Docker Compose 未安装。请先安装 Docker Compose。"
    fi

    COMPOSE_CMD="docker compose"
    if ! docker compose version >/dev/null 2>&1; then
        COMPOSE_CMD="docker-compose"
    fi

    check_tun
    setup_sysctl

    # ─── 生成令牌 ───
    local env_file="$INSTALL_DIR/.env"
    mkdir -p "$INSTALL_DIR"
    local token_file="$INSTALL_DIR/.xmili_token"
    if [ -f "$token_file" ]; then
        X_MILI_TOKEN=$(cat "$token_file")
    else
        X_MILI_TOKEN=$(generate_token)
        echo "$X_MILI_TOKEN" > "$token_file"
        chmod 600 "$token_file"
    fi

    # ─── 创建 .env 文件 ───
    cat > "$env_file" <<ENV
X_MILI_TOKEN=${X_MILI_TOKEN}
AIMILI_PORT=${AIMILI_PORT}
AIMILI_PROXY_PORT=${AIMILI_PROXY_PORT}
ENV

    # ─── 创建 docker-compose 文件 ───
    local compose_file="$INSTALL_DIR/docker-compose.yml"

    # 如果有 Docker 则用镜像模式，否则下载 docker-compose 文件用 build 模式
    cat > "$compose_file" <<'COMPOSE'
services:
  aimilivpn:
    image: ghcr.io/xiaoxinkeji/aimili-vpngate:latest
    container_name: aimilivpn
    restart: unless-stopped
    network_mode: host
    cap_add:
      - NET_ADMIN
      - NET_RAW
    devices:
      - /dev/net/tun:/dev/net/tun
    environment:
      - VPNGATE_DATA_DIR=/opt/aimilivpn/vpngate_data
      - LOCAL_PROXY_HOST=127.0.0.1
      - LOCAL_PROXY_PORT=${AIMILI_PROXY_PORT:-7928}
      - UI_HOST=::
      - UI_PORT=${AIMILI_PORT:-8787}
      - X_MILI_TOKEN=${X_MILI_TOKEN}
    volumes:
      - aimili_data:/opt/aimilivpn/vpngate_data
    tmpfs:
      - /tmp:exec
    sysctls:
      - net.ipv4.conf.all.rp_filter=2
      - net.ipv4.conf.default.rp_filter=2
      - net.ipv4.ip_forward=1
    security_opt:
      - no-new-privileges:true
    logging:
      driver: json-file
      options:
        max-size: "20m"
        max-file: "3"
    healthcheck:
      test:
        - CMD-SHELL
        - pgrep -f vpngate_manager.py > /dev/null && curl -sf --max-time 5 http://localhost:${AIMILI_PORT:-8787}/ > /dev/null || exit 1
      interval: 30s
      timeout: 10s
      start_period: 90s
      retries: 3

  xmili:
    image: ghcr.io/xiaoxinkeji/x-mili-integrated:latest
    container_name: xmili
    restart: unless-stopped
    network_mode: host
    cap_add:
      - NET_ADMIN
    devices:
      - /dev/net/tun:/dev/net/tun
    environment:
      - XRAY_VMESS_AEAD_FORCED=false
      - XUI_ENABLE_FAIL2BAN=false
      - AIMILI_NODE_API=http://127.0.0.1:${AIMILI_PORT:-8787}
      - X_MILI_TOKEN=${X_MILI_TOKEN}
    volumes:
      - xmili_db:/etc/x-ui/
      - xmili_cert:/root/cert/
    tty: true
    logging:
      driver: json-file
      options:
        max-size: "20m"
        max-file: "3"
    depends_on:
      aimilivpn:
        condition: service_healthy

volumes:
  aimili_data:
  xmili_db:
  xmili_cert:
COMPOSE

    # ─── 确保 env 变量传递给 docker compose ───
    export AIMILI_PORT AIMILI_PROXY_PORT X_MILI_TOKEN

    # ─── 启动服务 ───
    cd "$INSTALL_DIR"
    log "拉取镜像并启动服务..."
    $COMPOSE_CMD up -d

    # ─── 输出面板信息 ───
    show_docker_info
}

show_docker_info() {
    echo ""
    echo "================================================"
    echo "  AimiliVPN + X-MILI 部署完成!"
    echo "================================================"
    echo ""
    echo "  AimiliVPN 面板: http://<服务器IP>:${AIMILI_PORT}/"
    echo ""
    echo "  查看 X-MILI 面板信息:"
    echo "    docker compose -f ${INSTALL_DIR}/docker-compose.yml logs xmili | grep -E '面板|登录|密码|端口'"
    echo "    docker compose -f ${INSTALL_DIR}/docker-compose.yml exec xmili x-ui settings"
    echo ""
    echo "  管理命令:"
    echo "    docker compose -f ${INSTALL_DIR}/docker-compose.yml ps"
    echo "    docker compose -f ${INSTALL_DIR}/docker-compose.yml logs -f"
    echo "    docker compose -f ${INSTALL_DIR}/docker-compose.yml restart"
    echo ""
    echo "  令牌文件: ${INSTALL_DIR}/.xmili_token"
    echo "================================================"
}

# ─── 更新 ───
do_update() {
    log "更新 AimiliVPN + X-MILI..."
    if [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
        log "Docker 模式更新..."
        cd "$INSTALL_DIR"
        if [ -f "$INSTALL_DIR/.xmili_token" ]; then
            export X_MILI_TOKEN=$(cat "$INSTALL_DIR/.xmili_token")
        fi
        export AIMILI_PORT AIMILI_PROXY_PORT
        local COMPOSE_CMD="docker compose"
        if ! docker compose version >/dev/null 2>&1; then
            COMPOSE_CMD="docker-compose"
        fi
        $COMPOSE_CMD pull
        $COMPOSE_CMD up -d --force-recreate
        log "更新完成!"
    elif systemctl is-active --quiet aimili-vpngate 2>/dev/null; then
        log "二进制模式更新..."
        FORCE_UPDATE=1 deploy_binary
    else
        warn "未检测到已安装的服务。请先运行安装脚本。"
    fi
}

# ─── 卸载 ───
do_uninstall() {
    warn "即将卸载 AimiliVPN + X-MILI 并删除所有数据!"
    echo -n "确认卸载? [y/N] "; read -r confirm
    [ "$confirm" != "y" ] && [ "$confirm" != "Y" ] && exit 0

    systemctl stop aimili-vpngate x-mili 2>/dev/null || true
    systemctl disable aimili-vpngate x-mili 2>/dev/null || true
    rm -f /etc/systemd/system/aimili-vpngate.service /etc/systemd/system/x-mili.service
    systemctl daemon-reload

    if command -v docker >/dev/null 2>&1; then
        local COMPOSE_CMD="docker compose"
        if ! docker compose version >/dev/null 2>&1; then COMPOSE_CMD="docker-compose"; fi
        if [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
            cd "$INSTALL_DIR" && $COMPOSE_CMD down -v 2>/dev/null || true
        fi
    fi

    rm -rf "$INSTALL_DIR"
    rm -f /etc/sysctl.d/99-aimili-xmili.conf
    log "卸载完成。"
}

# ─── 状态 ───
show_status() {
    echo ""
    echo "=== AimiliVPN + X-MILI 状态 ==="
    echo ""
    if systemctl is-active --quiet aimili-vpngate 2>/dev/null; then
        echo -e "  aimili-vpngate service: ${GR}active${NC}"
        echo "  API: http://127.0.0.1:${AIMILI_PORT}/api/nodes"
    elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q aimilivpn; then
        echo -e "  aimili-vpngate container: ${GR}running${NC}"
        echo "  API: http://127.0.0.1:${AIMILI_PORT}/api/nodes"
    else
        echo -e "  aimili-vpngate: ${RD}not running${NC}"
    fi
    echo ""
    if systemctl is-active --quiet x-mili 2>/dev/null; then
        echo -e "  x-mili service: ${GR}active${NC}"
    elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q xmili; then
        echo -e "  x-mili container: ${GR}running${NC}"
    else
        echo -e "  x-mili: ${RD}not running${NC}"
    fi
    echo ""
    if [ -f "$INSTALL_DIR/.xmili_token" ]; then
        echo "  Token: $(cat "$INSTALL_DIR/.xmili_token")"
    fi
    echo ""
}

# ─── 主流程 ───
MODE="auto"
case "${1:-}" in
    --docker|-d)  MODE="docker" ;;
    --binary|-b)  MODE="binary" ;;
    --update|-u)  do_update; exit 0 ;;
    --uninstall)  do_uninstall; exit 0 ;;
    --status|-s)  show_status; exit 0 ;;
    --help|-h)    echo "用法: $0 [--docker|--binary|--update|--uninstall|--status]"; exit 0 ;;
esac

detect_os

if [ "$MODE" = "auto" ]; then
    if command -v docker >/dev/null 2>&1 && (docker compose version >/dev/null 2>&1 || docker-compose version >/dev/null 2>&1); then
        MODE="docker"
        log "自动检测到 Docker, 使用 Docker 部署模式"
    else
        MODE="binary"
        log "未检测到 Docker, 使用二进制部署模式"
    fi
fi

case "$MODE" in
    docker) deploy_docker ;;
    binary) deploy_binary ;;
esac
