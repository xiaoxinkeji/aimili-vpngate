#!/usr/bin/env bash
# AimiliVPN Docker 宿主机一键预检与配置脚本
# 功能: 检查并加载 TUN 模块、配置内核参数、确保宿主机满足 Docker 运行要求
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;36m'
BOLD='\033[1m'
PLAIN='\033[0m'

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════╗${PLAIN}"
echo -e "${BLUE}║${BOLD}     AimiliVPN Docker 宿主机环境预检脚本         ${BLUE}║${PLAIN}"
echo -e "${BLUE}╚══════════════════════════════════════════════════╝${PLAIN}"
echo ""

# ── 1. 权限检查 ──────────────────────────────────────
if [ "$(id -u)" != "0" ]; then
    echo -e "${RED}[错误] 必须以 root 权限运行此脚本。${PLAIN}"
    echo -e "  请使用: ${YELLOW}sudo bash $0${PLAIN}"
    exit 1
fi

ALL_OK=true

# ── 2. TUN 模块检查与加载 ─────────────────────────────
echo -e "${BOLD}[1/4]${PLAIN} 检查 TUN 内核模块..."
if [ -c /dev/net/tun ]; then
    echo -e "  ${GREEN}[通过] /dev/net/tun 设备已存在${PLAIN}"
else
    echo -e "  ${YELLOW}[操作] /dev/net/tun 不存在，尝试加载 tun 模块...${PLAIN}"
    if modprobe tun 2>/dev/null; then
        echo -e "  ${GREEN}[通过] tun 模块加载成功${PLAIN}"
    elif insmod /lib/modules/tun.ko 2>/dev/null; then
        echo -e "  ${GREEN}[通过] tun 模块加载成功 (insmod)${PLAIN}"
    else
        echo -e "  ${RED}[失败] 无法加载 tun 内核模块${PLAIN}"
        echo -e "  ${YELLOW}  可能原因:${PLAIN}"
        echo -e "    1. 宿主机内核未编译 TUN 支持 (CONFIG_TUN=m 或 y)"
        echo -e "    2. LXC/OpenVZ 虚拟化需在宿主机层面开启 TUN 权限"
        echo -e "    3. 某些云服务器默认禁用内核模块加载"
        echo ""
        echo -e "  ${YELLOW}  解决方案:${PLAIN}"
        echo -e "    - KVM/Xen/VMware: 联系 VPS 提供商确认 TUN/TAP 支持"
        echo -e "    - LXC/OpenVZ: 在宿主机控制面板中为容器开启 TUN 设备权限"
        echo -e "    - 自建服务器: apt-get install linux-modules-extra-\\$(uname -r) 后重试"
        ALL_OK=false
    fi
fi

# 检查 TUN 设备读写权限
if [ -c /dev/net/tun ]; then
    if [ -r /dev/net/tun ] && [ -w /dev/net/tun ]; then
        echo -e "  ${GREEN}[通过] /dev/net/tun 读写权限正常${PLAIN}"
    else
        echo -e "  ${YELLOW}[修复] /dev/net/tun 权限不足，尝试 chmod 666...${PLAIN}"
        chmod 666 /dev/net/tun 2>/dev/null && echo -e "  ${GREEN}[通过] 权限已修复${PLAIN}" || echo -e "  ${RED}[失败] 无法修改权限${PLAIN}"
    fi
fi

# ── 3. 内核网络参数配置 ──────────────────────────────
echo ""
echo -e "${BOLD}[2/4]${PLAIN} 配置内核网络参数..."

# IP 转发
CUR_FWD=$(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null || echo "0")
if [ "$CUR_FWD" = "1" ]; then
    echo -e "  ${GREEN}[通过] ip_forward 已启用${PLAIN}"
else
    echo -e "  ${YELLOW}[修复] 启用 ip_forward...${PLAIN}"
    echo 1 > /proc/sys/net/ipv4/ip_forward 2>/dev/null && echo -e "  ${GREEN}[通过] 已启用${PLAIN}" || echo -e "  ${YELLOW}[跳过] 无权限${PLAIN}"
fi

# rp_filter 宽松模式
RP_ALL=$(cat /proc/sys/net/ipv4/conf/all/rp_filter 2>/dev/null || echo "0")
if [ "$RP_ALL" = "2" ]; then
    echo -e "  ${GREEN}[通过] rp_filter=2 (宽松模式)${PLAIN}"
else
    echo -e "  ${YELLOW}[修复] 设置 rp_filter=2...${PLAIN}"
    for iface in all default; do
        echo 2 > "/proc/sys/net/ipv4/conf/${iface}/rp_filter" 2>/dev/null || true
    done
    echo -e "  ${GREEN}[通过] 已设置为宽松模式${PLAIN}"
fi

# 持久化内核参数
if [ -d "/etc/sysctl.d" ]; then
    cat > /etc/sysctl.d/99-aimilivpn-docker.conf <<'SYSCTL'
# AimiliVPN Docker 宿主机内核参数
net.ipv4.ip_forward = 1
net.ipv4.conf.all.rp_filter = 2
net.ipv4.conf.default.rp_filter = 2
SYSCTL
    sysctl -p /etc/sysctl.d/99-aimilivpn-docker.conf >/dev/null 2>&1 || true
    echo -e "  ${GREEN}[通过] 内核参数已持久化到 /etc/sysctl.d/99-aimilivpn-docker.conf${PLAIN}"
fi

# ── 4. Docker 环境检查 ──────────────────────────────
echo ""
echo -e "${BOLD}[3/4]${PLAIN} 检查 Docker 环境..."

if command -v docker >/dev/null 2>&1; then
    DOCKER_VER=$(docker --version 2>/dev/null | head -1)
    echo -e "  ${GREEN}[通过] Docker 已安装: ${DOCKER_VER}${PLAIN}"
    
    if docker info >/dev/null 2>&1; then
        echo -e "  ${GREEN}[通过] Docker 守护进程运行正常${PLAIN}"
    else
        echo -e "  ${RED}[失败] Docker 守护进程未运行或无权限${PLAIN}"
        ALL_OK=false
    fi
else
    echo -e "  ${RED}[失败] Docker 未安装${PLAIN}"
    echo -e "  ${YELLOW}  安装命令:${PLAIN}"
    echo -e "    curl -fsSL https://get.docker.com | bash"
    ALL_OK=false
fi

if command -v docker compose >/dev/null 2>&1 || docker compose version >/dev/null 2>&1; then
    echo -e "  ${GREEN}[通过] Docker Compose 可用${PLAIN}"
elif command -v docker-compose >/dev/null 2>&1; then
    echo -e "  ${GREEN}[通过] docker-compose (v1) 可用${PLAIN}"
else
    echo -e "  ${YELLOW}[提示] Docker Compose 未安装，将使用 docker run 方式${PLAIN}"
fi

# ── 5. 防火墙提示 ────────────────────────────────────
echo ""
echo -e "${BOLD}[4/4]${PLAIN} 防火墙检查..."

UI_PORT="${AIMILI_UI_PORT:-8787}"
PROXY_PORT="${AIMILI_PROXY_PORT:-7928}"
METRICS_PORT="${AIMILI_METRICS_PORT:-9798}"

echo -e "  ${BLUE}[提示]${PLAIN} 如果使用了 host 网络模式，请确保以下端口未被占用:"
echo -e "    - 管理面板: ${YELLOW}${UI_PORT}/tcp${PLAIN}"
echo -e "    - HTTP/SOCKS5 代理: ${YELLOW}${PROXY_PORT}/tcp${PLAIN}"
echo -e "    - Prometheus 指标: ${YELLOW}${METRICS_PORT}/tcp${PLAIN}"

# 检测端口占用
for port in $UI_PORT $PROXY_PORT $METRICS_PORT; do
    if ss -tlnp 2>/dev/null | grep -q ":${port} " || netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
        echo -e "  ${YELLOW}[警告] 端口 ${port} 已被占用${PLAIN}"
    else
        echo -e "  ${GREEN}[通过] 端口 ${port} 空闲${PLAIN}"
    fi
done

# 防火墙提示 (UFW / firewalld / iptables)
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "active"; then
    echo ""
    echo -e "  ${YELLOW}[提示] 检测到 UFW 防火墙已启用，如需从外网访问管理面板，请放行端口:${PLAIN}"
    echo -e "    ufw allow ${UI_PORT}/tcp"
fi

if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
    echo ""
    echo -e "  ${YELLOW}[提示] 检测到 firewalld 已启用，如需从外网访问管理面板，请放行端口:${PLAIN}"
    echo -e "    firewall-cmd --permanent --add-port=${UI_PORT}/tcp && firewall-cmd --reload"
fi

# ── 汇总 ────────────────────────────────────────────
echo ""
echo -e "${BLUE}==========================================================${PLAIN}"
if [ "$ALL_OK" = true ]; then
    echo -e "  ${GREEN}${BOLD}宿主机环境检查全部通过！${PLAIN}"
    echo -e "  ${GREEN}可以开始部署 AimiliVPN Docker 容器。${PLAIN}"
    echo ""
    echo -e "  ${BOLD}快速启动命令:${PLAIN}"
    echo ""
    echo -e "  ${BLUE}# 方式一: docker compose (推荐)${PLAIN}"
    echo -e "  ${YELLOW}docker compose up -d${PLAIN}"
    echo ""
    echo -e "  ${BLUE}# 方式二: docker run${PLAIN}"
    echo -e "  ${YELLOW}docker run -d \\"
    echo -e "    --name aimilivpn \\"
    echo -e "    --network host \\"
    echo -e "    --cap-add NET_ADMIN \\"
    echo -e "    --cap-add NET_RAW \\"
    echo -e "    --device /dev/net/tun:/dev/net/tun \\"
    echo -e "    --restart unless-stopped \\"
    echo -e "    ghcr.io/xiaoxinkeji/aimili-vpngate:latest${PLAIN}"
    echo ""
    echo -e "  ${BLUE}# 查看启动日志 (含管理地址和账号密码)${PLAIN}"
    echo -e "  ${YELLOW}docker logs -f aimilivpn${PLAIN}"
else
    echo -e "  ${RED}${BOLD}部分检查未通过，请根据上述提示修复后再部署。${PLAIN}"
fi
echo -e "${BLUE}==========================================================${PLAIN}"
echo ""

if [ "$ALL_OK" = true ]; then
    exit 0
else
    exit 1
fi
