#!/bin/bash

# AimiliVPN Docker Entrypoint
# 功能: 环境预检 -> 网络参数优化 -> 启停信号处理 -> 启动主进程

set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
PLAIN="\033[0m"

PID_FILE="/tmp/aimilivpn.pid"
CHILD_PID=""

# ── 优雅关闭 ──────────────────────────────────────────
cleanup() {
    echo ""
    echo -e "${YELLOW}[aimilivpn] 收到停止信号，正在优雅关闭...${PLAIN}"
    if [ -n "$CHILD_PID" ] && kill -0 "$CHILD_PID" 2>/dev/null; then
        kill -TERM "$CHILD_PID" 2>/dev/null || true
        # 等待最多 15 秒让子进程自行清理 (停止 OpenVPN、清除路由等)
        for i in $(seq 1 15); do
            if ! kill -0 "$CHILD_PID" 2>/dev/null; then
                break
            fi
            sleep 1
        done
        # 如果还没退出，强制杀死
        if kill -0 "$CHILD_PID" 2>/dev/null; then
            echo -e "${RED}[aimilivpn] 子进程未响应，强制终止${PLAIN}"
            kill -KILL "$CHILD_PID" 2>/dev/null || true
        fi
    fi
    # 清理可能残留的 OpenVPN 进程
    pkill -f "openvpn.*vpngate_data" 2>/dev/null || true
    echo -e "${GREEN}[aimilivpn] 已关闭${PLAIN}"
    exit 0
}

trap cleanup SIGTERM SIGINT SIGHUP

# ── 环境预检 ──────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${PLAIN}"
echo -e "${CYAN}║${BOLD}           AimiliVPN Docker Container              ${CYAN}║${PLAIN}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${PLAIN}"
echo ""

# 1. TUN 设备检查
echo -e "${BOLD}[1/5]${PLAIN} 检查 TUN 设备..."
if [ ! -c /dev/net/tun ]; then
    echo -e "  ${RED}✗ /dev/net/tun 不存在${PLAIN}"
    echo -e "  ${YELLOW}→ 请使用: --device=/dev/net/tun${PLAIN}"
    exit 1
fi
if [ ! -r /dev/net/tun ] || [ ! -w /dev/net/tun ]; then
    echo -e "  ${YELLOW}⚠ /dev/net/tun 权限不足，尝试修复...${PLAIN}"
    chmod 666 /dev/net/tun 2>/dev/null || echo -e "  ${RED}  修复失败，请使用 --privileged 或调整宿主机权限${PLAIN}"
fi
echo -e "  ${GREEN}✓ /dev/net/tun 就绪${PLAIN}"

# 2. 网络参数
echo -e "${BOLD}[2/5]${PLAIN} 配置内核网络参数..."
echo 1 > /proc/sys/net/ipv4/ip_forward 2>/dev/null && echo -e "  ${GREEN}✓ ip_forward 已启用${PLAIN}" || echo -e "  ${YELLOW}⚠ 无法设置 ip_forward (非特权模式)${PLAIN}"
for iface in all default; do
    echo 2 > "/proc/sys/net/ipv4/conf/${iface}/rp_filter" 2>/dev/null || true
done
echo -e "  ${GREEN}✓ rp_filter 已设为宽松模式${PLAIN}"

# 3. 依赖检查
echo -e "${BOLD}[3/5]${PLAIN} 检查系统依赖..."
OVPN_VER=$(openvpn --version 2>&1 | head -1 || echo "unknown")
echo -e "  ${GREEN}✓ openvpn: ${OVPN_VER}${PLAIN}"
PY_VER=$(python3 --version 2>&1)
echo -e "  ${GREEN}✓ ${PY_VER}${PLAIN}"

# 4. iptables 权限
echo -e "${BOLD}[4/5]${PLAIN} 检查网络管理权限..."
if iptables -L -n > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓ iptables 可用${PLAIN}"
else
    echo -e "  ${YELLOW}⚠ iptables 不可用，策略路由功能可能受限${PLAIN}"
fi

# 5. 目录准备
echo -e "${BOLD}[5/5]${PLAIN} 准备数据目录..."
mkdir -p "$VPNGATE_DATA_DIR" "$VPNGATE_DATA_DIR/logs" "$VPNGATE_DATA_DIR/configs"
echo -e "  ${GREEN}✓ 数据目录: ${VPNGATE_DATA_DIR}${PLAIN}"

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${PLAIN}"
echo -e "  ${BOLD}环境检查通过，启动 AimiliVPN...${PLAIN}"
echo ""
echo -e "  Web 管理后台:  ${CYAN}http://宿主机IP:${UI_PORT:-8787}/${PLAIN}"
echo -e "  代理地址:      ${CYAN}http://127.0.0.1:${LOCAL_PROXY_PORT:-7928}${PLAIN}"
echo -e "  容器状态:      ${CYAN}docker exec -it aimilivpn docker-stats${PLAIN}"
echo -e "${GREEN}══════════════════════════════════════════════════${PLAIN}"
echo ""

# ── 启动主进程 ────────────────────────────────────────
python3 /opt/aimilivpn/vpngate_manager.py &
CHILD_PID=$!
echo "$CHILD_PID" > "$PID_FILE"

# 等待子进程退出
wait "$CHILD_PID"
EXIT_CODE=$?
echo -e "${YELLOW}[aimilivpn] 主进程退出 (code: $EXIT_CODE)${PLAIN}"
exit $EXIT_CODE
