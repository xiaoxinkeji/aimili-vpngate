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

[[ $EUID -ne 0 ]] && err "请使用 root 运行 / Please run as root"

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
XMILI_PANEL_PORT="${XMILI_PANEL_PORT:-}"

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
            err "无法加载 tun 模块。请确保 VPS 支持 TUN/TAP (OpenVZ/LXC 需在面板开启)"
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
    [ -n "$XMILI_PORT" ] && ports="$ports $XMILI_PORT"
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

# ─── 二进制部署 ───
deploy_binary() {
    log "=== 二进制部署模式 ==="
    install_deps
    check_tun
    setup_sysctl

    mkdir -p "$INSTALL_DIR" "$DATA_DIR" "$XMILI_DIR" "$XMILI_DB"

    # ─── 下载 aimili-vpngate 二进制 ───
    local aimili_bin="$INSTALL_DIR/aimili-vpngate"
    if [ ! -f "$aimili_bin" ] || [ "${FORCE_UPDATE:-}" = "1" ]; then
        log "下载 aimili-vpngate 二进制 ($ARCH)..."
        local aimili_url="${RELEASE_URL}/aimili-vpngate-${ARCH}"
        curl -fL --progress-bar -o "$aimili_bin" "$aimili_url" || err "下载 aimili-vpngate 失败"
        chmod +x "$aimili_bin"
    fi

    # ─── 下载 X-MILI 集成版二进制 ───
    local xmili_bin="$XMILI_DIR/x-ui"
    if [ ! -f "$xmili_bin" ] || [ "${FORCE_UPDATE:-}" = "1" ]; then
        log "下载 X-MILI 集成版二进制 ($ARCH)..."
        local xmili_url="${RELEASE_URL}/x-mili-integrated-${ARCH}"
        curl -fL --progress-bar -o "$xmili_bin" "$xmili_url" || {
            warn "未找到预构建的 X-MILI 集成版二进制，尝试使用标准版..."
            local xmili_std_url="https://github.com/Aimilibot/X-MILI/releases/latest/download/x-ui-${ARCH}"
            curl -fL --progress-bar -o "$xmili_bin" "$xmili_std_url" || err "下载 X-MILI 失败。请使用 Docker 部署模式。"
        }
        chmod +x "$xmili_bin"
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
    echo "    ml settings"
    echo ""
    echo "  管理命令:"
    echo "    systemctl status aimili-vpngate x-mili"
    echo "    systemctl restart aimili-vpngate x-mili"
    echo "    ml          # X-MILI 管理菜单"
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
XMILI_PORT=${XMILI_PORT}
ENV

    # ─── 创建 docker-compose 文件 ───
    local compose_file="$INSTALL_DIR/docker-compose.yml"
    local compose_url="${REPO}/main/docker-compose.x-mili.yml"

    # 如果本地有源码则直接复制，否则从 GitHub 下载
    if [ -f "$(dirname "$0")/../docker-compose.x-mili.yml" ]; then
        cp "$(dirname "$0")/../docker-compose.x-mili.yml" "$compose_file"
    else
        log "下载 docker-compose 文件..."
        curl -fL --progress-bar -o "$compose_file" "$compose_url"
    fi

    # ─── 启动服务 ───
    cd "$INSTALL_DIR"
    log "拉取镜像并启动服务..."
    X_MILI_TOKEN="$X_MILI_TOKEN" $COMPOSE_CMD up -d

    # ─── 输出面板信息 ───
    show_docker_info
}

show_docker_info() {
    local compose_cmd="docker compose"
    docker compose version >/dev/null 2>&1 || compose_cmd="docker-compose"

    echo ""
    echo "================================================"
    echo "  AimiliVPN + X-MILI (Docker) 部署完成!"
    echo "================================================"
    echo ""
    echo "  AimiliVPN 面板: http://<服务器IP>:${AIMILI_PORT}/"
    echo "  AimiliVPN 代理: http://127.0.0.1:${AIMILI_PROXY_PORT}"
    echo ""
    echo "  查看面板登录信息:"
    echo "    docker logs aimilivpn | grep '管理后台'"
    echo "    docker logs xmili | grep -E '面板|登录|密码'"
    echo ""
    echo "  管理命令:"
    echo "    cd ${INSTALL_DIR}"
    echo "    ${compose_cmd} ps"
    echo "    ${compose_cmd} logs -f aimilivpn"
    echo "    ${compose_cmd} logs -f xmili"
    echo "    ${compose_cmd} restart"
    echo ""
    echo "  令牌文件: ${INSTALL_DIR}/.xmili_token"
    echo "================================================"
}

# ─── 更新 ───
do_update() {
    log "更新部署..."
    if [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
        cd "$INSTALL_DIR"
        local compose_cmd="docker compose"
        docker compose version >/dev/null 2>&1 || compose_cmd="docker-compose"
        $compose_cmd pull
        $compose_cmd up -d
        log "Docker 更新完成"
    elif [ -f /etc/systemd/system/aimili-vpngate.service ]; then
        FORCE_UPDATE=1 deploy_binary
        log "二进制更新完成"
    else
        err "未找到已有部署，请使用 install 命令。"
    fi
}

# ─── 卸载 ───
do_uninstall() {
    warn "即将卸载 AimiliVPN + X-MILI，数据将保留在:"
    warn "  ${DATA_DIR}"
    warn "  ${XMILI_DB}"
    read -rp "确认卸载? [y/N]: " confirm
    [[ "$confirm" != "y" && "$confirm" != "Y" ]] && exit 0

    if [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
        cd "$INSTALL_DIR"
        local compose_cmd="docker compose"
        docker compose version >/dev/null 2>&1 || compose_cmd="docker-compose"
        $compose_cmd down -v 2>/dev/null || true
    fi

    systemctl stop aimili-vpngate x-mili 2>/dev/null || true
    systemctl disable aimili-vpngate x-mili 2>/dev/null || true
    rm -f /etc/systemd/system/aimili-vpngate.service /etc/systemd/system/x-mili.service
    systemctl daemon-reload 2>/dev/null || true

    rm -f /etc/sysctl.d/99-aimili-xmili.conf
    sysctl -p >/dev/null 2>&1 || true

    log "卸载完成。数据目录保留: ${DATA_DIR}, ${XMILI_DB}"
    log "如需彻底清理: rm -rf ${DATA_DIR} ${XMILI_DB} ${INSTALL_DIR}"
}

# ─── 显示状态 ───
do_status() {
    echo "=== AimiliVPN + X-MILI 部署状态 ==="
    echo ""
    if [ -f /etc/systemd/system/aimili-vpngate.service ]; then
        echo "--- aimili-vpngate (systemd) ---"
        systemctl status aimili-vpngate --no-pager -l 2>/dev/null || echo "  未运行"
    fi
    if [ -f /etc/systemd/system/x-mili.service ]; then
        echo "--- x-mili (systemd) ---"
        systemctl status x-mili --no-pager -l 2>/dev/null || echo "  未运行"
    fi
    if [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
        cd "$INSTALL_DIR"
        local compose_cmd="docker compose"
        docker compose version >/dev/null 2>&1 || compose_cmd="docker-compose"
        echo "--- Docker 容器 ---"
        $compose_cmd ps 2>/dev/null
    fi
    if [ -f "$INSTALL_DIR/.xmili_token" ]; then
        echo "X_MILI_TOKEN: $(cat "$INSTALL_DIR/.xmili_token")"
    fi
}

# ─── 帮助 ───
do_help() {
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  install      安装 (自动检测 Docker, 无 Docker 则二进制)"
    echo "  install --docker   强制 Docker 模式"
    echo "  install --binary   强制二进制模式"
    echo "  update       更新到最新版本"
    echo "  uninstall    卸载 (保留数据)"
    echo "  status       查看部署状态"
    echo "  help         显示此帮助"
    echo ""
    echo "环境变量:"
    echo "  AIMILI_PORT         AimiliVPN Web 端口 (默认 8787)"
    echo "  AIMILI_PROXY_PORT   AimiliVPN 代理端口 (默认 7928)"
    echo "  XMILI_PORT          X-MILI Web 端口 (仅 Docker 模式)"
}

# ─── 主入口 ───
detect_os

MODE="auto"
ACTION="install"

for arg in "$@"; do
    case "$arg" in
        --docker) MODE="docker" ;;
        --binary) MODE="binary" ;;
        install)   ACTION="install" ;;
        update)    ACTION="update" ;;
        uninstall) ACTION="uninstall" ;;
        status)    ACTION="status" ;;
        help|--help|-h) ACTION="help" ;;
    esac
done

case "$ACTION" in
    install)
        if [ "$MODE" = "docker" ]; then
            deploy_docker
        elif [ "$MODE" = "binary" ]; then
            deploy_binary
        else
            # 自动模式: 检测 Docker
            if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
                log "检测到 Docker, 使用 Docker 部署模式"
                deploy_docker
            else
                log "未检测到 Docker, 使用二进制部署模式"
                deploy_binary
            fi
        fi
        ;;
    update)    do_update ;;
    uninstall) do_uninstall ;;
    status)    do_status ;;
    help)      do_help ;;
    *)         do_help ;;
esac
