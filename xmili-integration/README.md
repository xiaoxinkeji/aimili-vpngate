# AimiliVPN + X-MILI 集成部署指南

X-MILI 是基于 3X-UI + Xray 内核的新一代代理管理面板。
AimiliVPN 提供更丰富的 VPN 节点源 (VPNGate + publicvpnlist.com) 和节点预检测。

## 一键自动部署 (推荐)

```bash
curl -Ls https://raw.githubusercontent.com/xiaoxinkeji/aimili-vpngate/main/xmili-integration/install.sh | bash
```

自动检测系统环境：
- 有 Docker → Docker Compose 模式 (隔离运行)
- 无 Docker → 二进制模式 (systemd 管理)

### 指定部署模式

```bash
# 强制 Docker 模式
bash xmili-integration/install.sh install --docker

# 强制二进制模式
bash xmili-integration/install.sh install --binary
```

### 自定义端口

```bash
AIMILI_PORT=9999 AIMILI_PROXY_PORT=8888 bash xmili-integration/install.sh install
```

## Docker 手动部署

```bash
# 1. 克隆仓库
git clone --recurse-submodules https://github.com/xiaoxinkeji/aimili-vpngate.git
cd aimili-vpngate

# 2. 预检宿主机
sudo bash docker-host-setup.sh

# 3. 生成令牌
export X_MILI_TOKEN=$(head -c 32 /dev/urandom | base64 | tr -d '+/=' | head -c 48)

# 4. 启动
docker compose -f docker-compose.x-mili.yml up -d

# 5. 查看面板信息
docker logs aimilivpn | grep "管理后台"
docker logs xmili | grep -E "面板|登录|密码"
```

## 二进制手动部署

```bash
# 1. 安装依赖
sudo apt-get install -y ca-certificates curl openvpn iptables iproute2

# 2. 下载 aimili-vpngate 二进制
sudo mkdir -p /opt/aimili-xmili /opt/aimili-xmili/data /opt/aimili-xmili/x-mili
sudo curl -fL -o /opt/aimili-xmili/aimili-vpngate \
  https://github.com/xiaoxinkeji/aimili-vpngate/releases/latest/download/aimilivpn-linux-amd64
sudo chmod +x /opt/aimili-xmili/aimili-vpngate

# 3. 下载 X-MILI 集成版二进制
sudo curl -fL -o /opt/aimili-xmili/x-mili/x-ui \
  https://github.com/xiaoxinkeji/aimili-vpngate/releases/latest/download/x-mili-integrated-linux-amd64
sudo chmod +x /opt/aimili-xmili/x-mili/x-ui

# 4. 生成令牌
export X_MILI_TOKEN=$(head -c 32 /dev/urandom | base64 | tr -d '+/=' | head -c 48)
echo "$X_MILI_TOKEN" | sudo tee /opt/aimili-xmili/.xmili_token
sudo chmod 600 /opt/aimili-xmili/.xmili_token

# 5. 创建 systemd 服务
sudo tee /etc/systemd/system/aimili-vpngate.service <<'EOF'
[Unit]
Description=AimiliVPN — VPN Node Manager
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/aimili-xmili/aimili-vpngate --data-dir /opt/aimili-xmili/data --host :: --port 8787 --proxy-port 7928
Environment=X_MILI_TOKEN=REPLACE_WITH_YOUR_TOKEN
Environment=VPNGATE_DATA_DIR=/opt/aimili-xmili/data
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/x-mili.service <<'EOF'
[Unit]
Description=X-MILI — Xray Proxy Panel
After=network-online.target aimili-vpngate.service
Wants=network-online.target aimili-vpngate.service

[Service]
Type=simple
WorkingDirectory=/opt/aimili-xmili/x-mili
ExecStart=/opt/aimili-xmili/x-mili/x-ui
Environment=AIMILI_NODE_API=http://127.0.0.1:8787
Environment=X_MILI_TOKEN=REPLACE_WITH_YOUR_TOKEN
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

# 6. 替换令牌
sudo sed -i "s/REPLACE_WITH_YOUR_TOKEN/$X_MILI_TOKEN/g" \
  /etc/systemd/system/aimili-vpngate.service \
  /etc/systemd/system/x-mili.service

# 7. 启动
sudo systemctl daemon-reload
sudo systemctl enable --now aimili-vpngate x-mili
```

## 架构说明

```
X-MILI (Xray 面板, Go)           AimiliVPN (节点服务, Python)
┌─────────────────────┐           ┌──────────────────────┐
│  VPNGate 面板页      │──GET──>  │  /api/nodes           │
│  (选择节点/连接)      │ Bearer   │  返回 VPNGate +       │
│                      │  Token   │  publicvpnlist 节点    │
│  openvpn 进程管理     │          │  (已预检测, 含延迟)    │
│  策略路由 + Xray注入  │          │                      │
└─────────────────────┘           └──────────────────────┘
```

## 端口说明

| 服务 | 默认端口 | 用途 |
|------|----------|------|
| AimiliVPN Web | 8787 | VPN 节点管理后台 |
| AimiliVPN Proxy | 7928 | HTTP/SOCKS5 代理出口 |
| X-MILI Web | 自动分配 | Xray 代理管理面板 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `X_MILI_TOKEN` | 自动生成 | 服务间认证令牌，两个服务必须一致 |
| `AIMILI_NODE_API` | `http://127.0.0.1:8787` | AimiliVPN API 地址 (不含 /api/nodes) |
| `AIMILI_PORT` | 8787 | AimiliVPN Web 端口 |
| `AIMILI_PROXY_PORT` | 7928 | AimiliVPN 代理端口 |
| `XMILI_PORT` | (自动) | X-MILI Web 端口 (仅 Docker) |

## 管理命令

### Docker 模式

```bash
cd /opt/aimili-xmili
docker compose ps                        # 查看容器状态
docker compose logs -f aimilivpn         # AimiliVPN 日志
docker compose logs -f xmili             # X-MILI 日志
docker compose restart                   # 重启全部
docker compose pull && docker compose up -d  # 更新
```

### 二进制模式

```bash
systemctl status aimili-vpngate x-mili   # 查看状态
journalctl -u aimili-vpngate -f          # AimiliVPN 日志
journalctl -u x-mili -f                  # X-MILI 日志
systemctl restart aimili-vpngate x-mili  # 重启
ml                                        # X-MILI 管理菜单
```

## 更新

```bash
# 一键更新
curl -Ls https://raw.githubusercontent.com/xiaoxinkeji/aimili-vpngate/main/xmili-integration/install.sh | bash -s update
```

## 卸载

```bash
curl -Ls https://raw.githubusercontent.com/xiaoxinkeji/aimili-vpngate/main/xmili-integration/install.sh | bash -s uninstall
```

数据目录保留: `/opt/aimili-xmili/data`, `/etc/x-ui`

## 前置条件

- Linux VPS (Debian/Ubuntu/CentOS/RHEL/Arch/Alpine)
- 支持 TUN/TAP (OpenVZ/LXC 需在面板开启)
- root 权限
- Docker 模式: Docker + Docker Compose
- 二进制模式: systemd, openvpn, iptables, iproute2

## 手动集成到已有 X-MILI

如果已单独部署了 X-MILI，可以手动添加 AimiliVPN 支持：

1. 部署 AimiliVPN (二进制或 Docker)
2. 复制 `xmili-integration/vpngate_aimili.go` 到 X-MILI 源码的 `web/service/`
3. 在 X-MILI 源码目录执行: `patch -p1 < xmili-integration/vpngate.patch`
4. 重新编译: `go build -o x-ui main.go`
5. 配置环境变量 `AIMILI_NODE_API` 和 `X_MILI_TOKEN`
6. 重启 X-MILI 服务
