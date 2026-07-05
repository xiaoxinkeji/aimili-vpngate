# AimiliVPN 🌐

[![Docker Image](https://img.shields.io/badge/ghcr.io-xiaoxinkeji%2Faimili--vpngate-blue?logo=docker)](https://github.com/xiaoxinkeji/aimili-vpngate/pkgs/container/aimili-vpngate)
[![GitHub Actions](https://img.shields.io/github/actions/workflow/status/xiaoxinkeji/aimili-vpngate/docker-publish.yml?branch=main&label=build)](https://github.com/xiaoxinkeji/aimili-vpngate/actions)

Bilingual: [中文](#中文) | [English](#english)

---

<a name="中文"></a>
## 中文 (Chinese)

AimiliVPN 是一款基于官方 VPNGate 开放协议的高性能、零依赖 VPN 代理网关。它以纯 Python 标准库编写，内置美观响应式的管理网页，提供智能并发测速、多路由模式、出站代理网关、实时日志等强大功能。

---

### 🌟 VPS 优选推荐：跑 AimiliVPN 更稳更省心
[![BandwagonHost 顶级三网优化](https://img.shields.io/badge/BandwagonHost-%E9%A1%B6%E7%BA%A7%E4%B8%89%E7%BD%91%E4%BC%98%E5%8C%96-red?style=for-the-badge)](https://bandwagonhost.com/aff.php?aff=81790)
[![RackNerd 6000GB 流量](https://img.shields.io/badge/RackNerd-6000GB%2F%E6%9C%88%20%E5%A4%A7%E6%B5%81%E9%87%8F-blue?style=for-the-badge)](https://my.racknerd.com/aff.php?aff=18708)

| 推荐 | 适合谁 | 亮点 | 入口 |
| --- | --- | --- | --- |
| **BandwagonHost 搬瓦工** | 更看重国内访问质量、延迟和线路上限的用户 | **顶级三网优化线路**，适合对网络体验、跨境访问质量和长期稳定性要求更高的场景 | [立即查看](https://bandwagonhost.com/aff.php?aff=81790) |
| **RackNerd** | 想低成本部署、测试、长期挂机的用户 | **每月 6000GB 流量**，价格实惠、配置给得足，适合入门部署和性价比优先的 VPS 需求 | [立即查看](https://my.racknerd.com/aff.php?aff=18708) |

---

### 📢 官方交流与反馈
[![Telegram](https://img.shields.io/badge/TG交流群-arestemple-2CA5E0?style=flat-square&logo=telegram&logoColor=white)](https://t.me/arestemple)
[![Forum](https://img.shields.io/badge/交流论坛-339936.xyz-orange?style=flat-square&logo=discourse&logoColor=white)](https://339936.xyz)
[![YouTube](https://img.shields.io/badge/视频教程-YouTube-red?style=flat-square&logo=youtube&logoColor=white)](https://www.youtube.com/watch?v=s-ATfXR8BpI)
[![Email](https://img.shields.io/badge/Bug反馈-yaohunse7@gmail.com-red?style=flat-square&logo=gmail&logoColor=white)](mailto:yaohunse7@gmail.com)

---

### 🚀 一键极速部署 (支持 Debian/Ubuntu/CentOS/Alpine 等 Linux 系统)

在您的 Linux VPS 上以 root 用户执行以下对应命令：

#### 🌟 正式稳定版本 (main 分支)
```bash
bash <(curl -Ls https://raw.githubusercontent.com/baoweise-bot/aimili-vpngate/main/install.sh)
```
> 💡 **小贴士**：部署完成后，终端会输出管理网页的专属链接（含随机安全后缀，如 `http://your_vps_ip:8787/u71e9IXp4TPx`）。在终端中输入 `ml` 命令可以随时调出交互式命令行管理菜单。

#### 🐳 Docker 部署

支持通过 Docker / Docker Compose 一键部署，无需手动安装系统依赖 (openvpn / iptables 等已内置在镜像中)。镜像自动构建多架构 (`amd64` / `arm64`)，内置健康检查和优雅关闭。

**前置条件：** 宿主机需加载 tun 内核模块。运行一键预检脚本自动完成环境配置：

```bash
# 下载并运行宿主机预检脚本 (自动加载 TUN / 配置内核参数 / 检查环境)
wget https://raw.githubusercontent.com/xiaoxinkeji/aimili-vpngate/main/docker-host-setup.sh
sudo bash docker-host-setup.sh
```

或手动执行：

```bash
# 检查 TUN 是否已就绪
[ -c /dev/net/tun ] && echo "TUN 已就绪" || echo "需要加载 tun 模块"

# 加载 tun 模块 (任选一种方式)
modprobe tun                # 标准方式
insmod /lib/modules/tun.ko  # modprobe 不可用时
# 如果是 LXC/OpenVZ 虚拟化，需在宿主机开启 TUN 设备权限
```

**docker-compose 部署（推荐）：**

```bash
# 下载 docker-compose.yml
wget https://raw.githubusercontent.com/xiaoxinkeji/aimili-vpngate/main/docker-compose.yml

# 启动 (自动拉起 OpenVPN + Web UI + SOCKS5/HTTP 代理)
docker compose up -d
```

**手动 docker run：**

```bash
docker run -d \
  --name aimilivpn \
  --network host \
  --cap-add=NET_ADMIN \
  --cap-add=NET_RAW \
  --device=/dev/net/tun:/dev/net/tun \
  -v $(pwd)/vpngate_data:/opt/aimilivpn/vpngate_data \
  -e VPNGATE_DATA_DIR=/opt/aimilivpn/vpngate_data \
  ghcr.io/xiaoxinkeji/aimili-vpngate:latest
```

> **参数说明：**
> - `--network host` — 必须使用 host 网络模式 (VPN 策略路由依赖)
> - `--cap-add=NET_ADMIN` — 允许容器内 iptables 修改路由规则
> - `--device=/dev/net/tun` — 将宿主机 TUN 设备透传给容器 (OpenVPN 必需)
> - `-v ./vpngate_data:...` — 持久化节点数据、配置文件、凭证，重启不丢失

**容器内管理命令：**

```bash
# 查看容器实时状态 (进程、端口、节点、路由、最近日志)
docker exec -it aimilivpn docker-stats

# 查看启动日志
docker logs -f aimilivpn

# 健康检查状态
docker inspect --format='{{.State.Health.Status}}' aimilivpn
```

**Docker 容器特性：**
- **启动预检**：自动检查 TUN 设备、openvpn、iptables、内核参数
- **健康检查**：每 30s 检测进程存活和 Web UI 可达性
- **优雅关闭**：收到 SIGTERM 后自动停止 OpenVPN、清理路由表再退出
- **多架构**：同时支持 `linux/amd64` 和 `linux/arm64` (树莓派等 ARM 设备)
- **持久化**：节点缓存、配置、日志均通过 volume 持久化

**环境变量说明：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `UI_HOST` | `::` | Web 管理后台绑定地址 |
| `UI_PORT` | `8787` | Web 管理后台端口 |
| `LOCAL_PROXY_HOST` | `127.0.0.1` | 代理监听地址 |
| `LOCAL_PROXY_PORT` | `7928` | HTTP/SOCKS5 代理端口 |
| `LOCAL_PROXY_USER` | (无) | 代理认证用户名 |
| `LOCAL_PROXY_PASS` | (无) | 代理认证密码 |
| `LOCAL_PROXY_MAX_CONNECTIONS` | `256` | 代理最大并发连接数 |
| `http_proxy` | (无) | 上游 HTTP 代理（用于拉取节点） |
| `OPENVPN_UPSTREAM_SOCKS` | (无) | 上游 SOCKS5 代理 |

> ⚠️ **注意**：Docker 容器必须使用 `--network host` 和 `--cap-add=NET_ADMIN` 参数，因为需要操作 TUN 虚拟网卡和系统路由表。

#### 📦 二进制部署 (无需 Python / Docker)

提供预编译的单一二进制文件，内置 Python 解释器，**无需安装 Python、Docker 或任何依赖**。`releases/latest` 始终指向最新版本。

**前置条件：** 需要安装系统级依赖 `openvpn` 和 `iptables`，并加载 tun 模块。

```bash
# Debian/Ubuntu
apt-get install -y openvpn iptables iproute2 curl

# CentOS/RHEL
yum install -y openvpn iptables iproute curl

# 加载 tun 内核模块 (任选一种)
modprobe tun                              # 标准方式
[ -c /dev/net/tun ] || echo "TUN 未加载"   # 检查是否已就绪
# 如果 modprobe 不可用，检查宿主机内核配置或联系 VPS 提供商
```

**下载并运行：**

```bash
# 下载对应架构的二进制 (amd64 或 arm64)
# 从 GitHub Releases 获取: https://github.com/xiaoxinkeji/aimili-vpngate/releases
wget https://github.com/xiaoxinkeji/aimili-vpngate/releases/latest/download/aimilivpn-linux-amd64.tar.gz
tar xzf aimilivpn-linux-amd64.tar.gz
chmod +x aimilivpn

# 直接运行 (需要 root 权限)
sudo ./aimilivpn

# 后台运行
sudo nohup ./aimilivpn > vpngate.log 2>&1 &

# 查看状态
curl http://localhost:8787/
```

**环境变量 (与 Docker 相同)：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VPNGATE_DATA_DIR` | `./vpngate_data` | 数据目录 |
| `UI_HOST` | `::` | Web 管理后台绑定地址 |
| `UI_PORT` | `8787` | Web 管理后台端口 |
| `LOCAL_PROXY_HOST` | `127.0.0.1` | 代理监听地址 |
| `LOCAL_PROXY_PORT` | `7928` | HTTP/SOCKS5 代理端口 |
| `METRICS_ENABLED` | `true` | 是否启用 Prometheus 指标 |
| `METRICS_PORT` | `9798` | 指标导出端口 |

```bash
# 自定义端口运行
sudo UI_PORT=8080 LOCAL_PROXY_PORT=1080 ./aimilivpn

# 指定数据目录
sudo VPNGATE_DATA_DIR=/var/lib/aimilivpn ./aimilivpn
```

> 💡 **提示**：二进制文件 (`aimilivpn`) 已内置 `docker-stats` 功能，运行后在同一目录或 PATH 下创建名为 `docker-stats` 的符号链接即可使用状态查看命令，或直接执行 `python3 docker-stats.py`。

**CLI 命令：**

```bash
./aimilivpn --version       # 查看版本信息
./aimilivpn --show-auth     # 查看管理凭证
./aimilivpn --check-update  # 检查是否有新版本
./aimilivpn --update        # 自动下载并更新到最新版
```

#### 📊 Prometheus 监控

容器内置 Prometheus 指标导出器，暴露进程、节点、连接、代理健康等指标。

**接入方式：**
```bash
# 指标端点 (默认端口 9798)
curl http://宿主机IP:9798/metrics
```

**暴露的指标：**

| 指标名 | 类型 | 说明 |
|--------|------|------|
| `aimilivpn_up` | gauge | 各组件存活状态 (manager/openvpn/ui/proxy/tun0) |
| `aimilivpn_connection_status` | gauge | 连接状态 (0=空闲, 1=切换中, 2=已连接) |
| `aimilivpn_proxy_healthy` | gauge | 出站代理健康检查是否通过 |
| `aimilivpn_proxy_latency_ms` | gauge | 出站代理延迟 (毫秒) |
| `aimilivpn_active_node_info` | gauge | 活动节点元数据 (node_id, country) |
| `aimilivpn_active_node_latency_ms` | gauge | 活动节点延迟 (毫秒) |
| `aimilivpn_active_node_score` | gauge | 活动节点评分 |
| `aimilivpn_nodes_total` | gauge | 节点总数 |
| `aimilivpn_nodes_by_status` | gauge | 按探测状态分组的节点数 |
| `aimilivpn_nodes_by_type` | gauge | 按 IP 类型分组的节点数 (residential/hosting) |
| `aimilivpn_blacklisted_nodes` | gauge | 黑名单节点数 |
| `aimilivpn_process_cpu_seconds_total` | counter | 进程 CPU 使用时间 |
| `aimilivpn_process_resident_memory_bytes` | gauge | 进程物理内存占用 |
| `aimilivpn_uptime_seconds` | gauge | 服务运行时长 (秒) |
| `aimilivpn_build_info` | gauge | 构建版本信息 |

**Prometheus 配置示例：**
```yaml
scrape_configs:
  - job_name: aimilivpn
    static_configs:
      - targets: ["your_vps_ip:9798"]
```

**关闭指标导出：**
```yaml
environment:
  - METRICS_ENABLED=false
```

#### 📈 Grafana 监控面板

预配置的 Grafana Dashboard，开箱即用。包含服务健康、延迟、CPU/内存、节点池统计等面板。

**一键启动监控栈 (Prometheus + Grafana)：**
```bash
docker compose -f docker-compose.yml -f contrib/docker-compose.monitor.yml up -d
```

访问 `http://宿主机IP:3000` (admin/admin)，Dashboard 已自动导入。

#### 🔄 自动更新

通过 Watchtower 自动拉取最新镜像并重启容器，无需手动更新：

```bash
# 启用自动更新 (每 6 小时检查一次)
docker compose --profile auto-update up -d
```

#### 🛡️ 安全加固

容器默认启用以下安全措施：
- `cap_drop: ALL` -- 移除所有非必要 Capability，仅保留 NET_ADMIN/NET_RAW
- `no-new-privileges: true` -- 禁止进程提权
- `tmpfs: /tmp, /run` -- 临时文件系统隔离
- 资源限制 CPU 2 核 / 内存 512MB

---

### 💡 快速使用指南 (小白必看)

部署成功后，如何使用它进行科学上网？

#### 如何查看管理凭证

**Docker:**
```bash
# 查看启动日志（包含 Web 地址、账号、密码）
docker logs aimilivpn 2>&1 | grep -A5 "启动成功"

# 或直接读取容器内凭证文件
docker exec aimilivpn cat /opt/aimilivpn/vpngate_data/CREDENTIALS.txt
```

**二进制:**
```bash
# 启动时控制台已打印凭证，也可随时查看
./aimilivpn --show-auth

# 或直接读取凭证文件
cat vpngate_data/CREDENTIALS.txt
```

**云端 VPS（无法直接看控制台时）：**
```bash
# 首次 SSH 连接 VPS 后运行 docker logs 查看凭证
ssh root@<VPS公网IP>
docker logs aimilivpn 2>&1 | grep -A5 "启动成功"
```

#### 第一步：登录 Web 管理后台
打开浏览器，访问部署完成时提示的专属后台地址（含安全后缀），即可进入精美的暗黑玻璃拟物风管理界面。

#### 第二步：获取并连接节点
1. 首次进入后台，节点列表可能正在进行首次自动测速与拉取。
2. 点击 **“更新节点”** 按钮（或通过网页下方的网关/日志进行状态检查），程序会在后台通过多线程并发测速，自动筛选出延迟最低、可连接的 VPNGate 节点。
3. 选择您喜欢的出站路由模式：
   - **智能自动配置**（推荐）：如果当前连接的节点失效，系统会在数秒内自动漂移连接至其他备用健康节点，无需手动干预。
   - **固定国家地区**：只选择指定国家（如日本 JP、韩国 KR、美国 US）的最佳节点。
   - **固定 IP 节点**：始终锁定连接到这一个特定节点。

#### 第三步：使用本机代理 (核心步骤)
为了防止代理端口暴露至公网被恶意扫描和滥用，AimiliVPN 的双效代理服务（默认端口 **`7928`**，自适应支持 SOCKS5 和 HTTP 协议）**默认仅绑定在本地回环地址（`127.0.0.1`）**，只接收 VPS 本机上的流量，不对外机提供代理。

* **🐍 Python 脚本中使用代理**:
  ```python
  import requests
  proxies = {
      "http": "http://127.0.0.1:7928",
      "https": "http://127.0.0.1:7928",
  }
  response = requests.get("https://www.google.com", proxies=proxies)
  ```
* **🐚 Shell 终端环境中使用代理**:
  在命令行执行以下命令，可以让当前终端的后续命令（如 `curl`、`wget` 等）走代理出口：
  ```bash
  export http_proxy="http://127.0.0.1:7928"
  export https_proxy="http://127.0.0.1:7928"
  ```
* **⚙️ 本地其他服务配置**:
  将本机的其他代理工具、爬虫框架或服务的出战代理设置为 `127.0.0.1:7928`。

> 💡 **小贴士**：如果您确实需要对公网其他设备开放此代理端口，可以通过设置环境变量 `export LOCAL_PROXY_HOST="::"` 重新启动服务以允许公网接入。

---

### 🛠️ 核心功能与操作说明

* **合并操作面板**：将“更新节点”与“立即检测补齐”合并，一键触发多线程拉取与测速。
* **网关状态面板**：
  - **系统诊断**：检测网关心跳及后台各个子守护线程（网页服务、VPN连接管理、出站网关服务）是否正常运行。若有脚本未运行，会提示具体的异常原因。
  - **本地代理出口检测**：在网页端直接一键检测 VPS 后台对海外的实际连通状况，并回显真实的代理出站 IP 和所在地理位置。
* **日志追踪面板**：
  - **分类过滤**：可精准筛选查看特定功能的日志（如 VPN 连接日志、API 请求日志、系统异常等）。
  - **实时滚动与管理**：日志实时滚动加载，支持一键复制代码、一键导出 `.log` 日志文件到本地。

---

### ⚠️ 小白安装与运行常见问题 (FAQ)

#### 1. 提示 `Cannot allocate tun` 或 `Cannot open tun/tap dev`
* **原因**：VPS 宿主机未启用虚拟网卡（TUN/TAP 设备）。这种情况常见于 LXC 或 OpenVZ 架构的轻量 VPS。
* **解决办法**：请登录您的 VPS 服务商控制面板（如 SolusVM/Proxmox），找到 **Enable TUN/TAP** / **开启 TUN** 选项并启用，然后重启 VPS。如无此选项，请工单联系客服开启。

#### 2. 网页管理后台无法打开（链接超时或拒绝连接）
* **原因 1**：VPS 本身自带防火墙（如 UFW、firewalld 或 iptables）阻断了管理端口（默认 `8787`）或代理端口（默认 `7928`）。
* **解决办法 1**：请在终端放行对应端口：
  * **UFW (Ubuntu/Debian)**: `ufw allow 8787/tcp && ufw allow 7928/tcp`
  * **Firewalld (CentOS/RHEL)**: `firewall-cmd --zone=public --add-port=8787/tcp --permanent && firewall-cmd --zone=public --add-port=7928/tcp --permanent && firewall-cmd --reload`
* **原因 2**：云服务商的“安全组”或“网络访问控制列表 (ACL)”未放行端口。
* **解决办法 2**：**非常重要！** 登录云服务商控制台（如阿里云、腾讯云、AWS、Oracle Cloud等），找到您 VPS 实例的 **安全组规则 (Security Group)**，在入站规则中添加：
  - **协议类型**: `TCP`
  - **端口范围**: `8787` (管理网页) 和 `7928` (代理端口)
  - **授权对象/源IP**: `0.0.0.0/0` (允许所有人，或指定您自己的家庭公网 IP 提高安全性)

#### 3. 页面提示 `API Domain Blocked` 且备选节点显示为 0
* **原因**：您的 VPS DNS 解析异常，或者官方 VPNGate 域名遭防火墙拦截污染，导致无法下载节点列表。
* **解决办法**：
  * **设置上游代理**：如果您有其他可用的代理服务，可在网页管理面板中打开“管理员 -> 代理及网络设置”，配置有效的 HTTP/SOCKS5 上游代理，后台会自动通过该代理拉取更新。
  * **修改 DNS 解析器**：在终端修改 `/etc/resolv.conf`，将域名服务器替换为公共 DNS（如 `nameserver 8.8.8.8` 和 `nameserver 1.1.1.1`）。

#### 4. VPN 已成功连接，但客户端设置代理后无法上网 (无流量)
* **原因**：部分系统启用了严格的反向路径过滤（`rp_filter`），导致策略路由的入站/出站数据包被系统误判丢弃。
* **解决办法**：在终端输入 `ml` 命令打开交互菜单，工具会自动检测并提示您将 `rp_filter` 修复为宽松模式（值为 `2`）。

---

### 🎁 捐赠支持项目开发

如果您觉得这个项目对您有所帮助，欢迎捐赠支持我们的后续开发与维护：

* **BNB (BSC / BEP20)**: `0xB6d78c42CEB0687A31B8cfEBE4b51b6eB8953C17`
* **TRX (TRC20)**: `TSdzCW6JvsrqcppodYjhSrku4mYmDJ9pxf`

感谢您的慷慨与支持！❤️

---

<a name="english"></a>
## English

AimiliVPN is a high-performance, zero-dependency VPN proxy gateway built entirely using Python's standard library. It parses official VPNGate servers, benchmarks latency, and routes traffic through a built-in dual-protocol (HTTP/SOCKS5) proxy server.

### 🌟 Recommended VPS Deals
[![BandwagonHost Premium Optimized Routes](https://img.shields.io/badge/BandwagonHost-Premium%20Optimized%20Routes-red?style=for-the-badge)](https://bandwagonhost.com/aff.php?aff=81790)
[![RackNerd 6000GB Bandwidth](https://img.shields.io/badge/RackNerd-6000GB%2Fmonth%20Bandwidth-blue?style=for-the-badge)](https://my.racknerd.com/aff.php?aff=18708)

| Pick | Best for | Highlights | Link |
| --- | --- | --- | --- |
| **BandwagonHost** | Users who care most about China connectivity, latency, and route quality | **Premium China Telecom/Unicom/Mobile optimized routes**, ideal for demanding cross-border networking and long-term use | [View deals](https://bandwagonhost.com/aff.php?aff=81790) |
| **RackNerd** | Budget deployments, testing, and long-running lightweight services | **6000GB monthly bandwidth**, affordable pricing, and generous specs for value-focused VPS use | [View deals](https://my.racknerd.com/aff.php?aff=18708) |


### 📢 Community & Feedback
- **Telegram Group**: [arestemple](https://t.me/arestemple)
- **Discussion Forum**: [339936.xyz](https://339936.xyz)
- **Video Tutorial**: [YouTube Guide](https://www.youtube.com/watch?v=s-ATfXR8BpI)
- **Email Contact**: yaohunse7@gmail.com

---

### 🚀 One-Click Installation

Run the corresponding command on your Linux VPS as root:

#### 🌟 Stable Release (main branch)
```bash
bash <(curl -Ls https://raw.githubusercontent.com/baoweise-bot/aimili-vpngate/main/install.sh)
```

> 💡 **Quick Note**: Once installed, copy the printed URL from the terminal to access the Web UI. Type the `ml` command in the terminal to summon the interactive CLI management console.

#### 🐳 Docker Deployment

Deploy with Docker / Docker Compose without installing system dependencies. Image is auto-built for multi-arch (`amd64` / `arm64`) with built-in health checks and graceful shutdown.

**Prerequisites:** Host must have tun kernel module loaded:
```bash
# Check and load tun module
lsmod | grep tun || modprobe tun
```

**docker-compose (Recommended):**
```bash
# Download docker-compose.yml
wget https://raw.githubusercontent.com/xiaoxinkeji/aimili-vpngate/main/docker-compose.yml
# Start (auto-launches OpenVPN + Web UI + SOCKS5/HTTP proxy)
docker compose up -d
```

**Manual docker run:**
```bash
docker run -d \
  --name aimilivpn \
  --network host \
  --cap-add=NET_ADMIN \
  --cap-add=NET_RAW \
  --device=/dev/net/tun:/dev/net/tun \
  -v $(pwd)/vpngate_data:/opt/aimilivpn/vpngate_data \
  -e VPNGATE_DATA_DIR=/opt/aimilivpn/vpngate_data \
  ghcr.io/xiaoxinkeji/aimili-vpngate:latest
```

**Container management commands:**
```bash
# View real-time container status (process, ports, node, routes, recent logs)
docker exec -it aimilivpn docker-stats

# View startup logs
docker logs -f aimilivpn

# Health check status
docker inspect --format='{{.State.Health.Status}}' aimilivpn
```

**Docker container features:**
- **Startup pre-check**: Auto-verify TUN device, openvpn, iptables, kernel parameters
- **Health check**: Check process liveness and Web UI reachability every 30s
- **Graceful shutdown**: Auto-stop OpenVPN, clean up routes on SIGTERM before exit
- **Multi-arch**: Supports `linux/amd64` and `linux/arm64` (Raspberry Pi, etc.)
- **Persistence**: Node cache, configs, logs persisted via volume

**Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `UI_HOST` | `::` | Web UI bind address |
| `UI_PORT` | `8787` | Web UI port |
| `LOCAL_PROXY_HOST` | `127.0.0.1` | Proxy listen address |
| `LOCAL_PROXY_PORT` | `7928` | HTTP/SOCKS5 proxy port |
| `LOCAL_PROXY_USER` | (none) | Proxy auth username |
| `LOCAL_PROXY_PASS` | (none) | Proxy auth password |
| `LOCAL_PROXY_MAX_CONNECTIONS` | `256` | Max concurrent proxy connections |
| `http_proxy` | (none) | Upstream HTTP proxy for node fetching |
| `OPENVPN_UPSTREAM_SOCKS` | (none) | Upstream SOCKS5 proxy |

> ⚠️ **Important**: Docker containers must use `--network host` and `--cap-add=NET_ADMIN` because they need to operate TUN virtual network cards and system routing tables.

#### 📊 Prometheus Monitoring

The container includes a built-in Prometheus metrics exporter that exposes process, node, connection, and proxy health metrics.

**Quick access:**
```bash
# Metrics endpoint (default port 9798)
curl http://your_vps_ip:9798/metrics
```

**Exposed metrics:**

| Metric | Type | Description |
|--------|------|-------------|
| `aimilivpn_up` | gauge | Component liveness (manager/openvpn/ui/proxy/tun0) |
| `aimilivpn_connection_status` | gauge | Connection status (0=idle, 1=connecting, 2=connected) |
| `aimilivpn_proxy_healthy` | gauge | Outbound proxy health check result |
| `aimilivpn_proxy_latency_ms` | gauge | Outbound proxy latency (ms) |
| `aimilivpn_active_node_info` | gauge | Active node metadata (node_id, country) |
| `aimilivpn_active_node_latency_ms` | gauge | Active node latency (ms) |
| `aimilivpn_active_node_score` | gauge | Active node score |
| `aimilivpn_nodes_total` | gauge | Total managed nodes |
| `aimilivpn_nodes_by_status` | gauge | Nodes grouped by probe status |
| `aimilivpn_nodes_by_type` | gauge | Nodes grouped by IP type (residential/hosting) |
| `aimilivpn_blacklisted_nodes` | gauge | Blacklisted node count |
| `aimilivpn_process_cpu_seconds_total` | counter | Process CPU seconds |
| `aimilivpn_process_resident_memory_bytes` | gauge | Process RSS memory |
| `aimilivpn_uptime_seconds` | gauge | Service uptime (seconds) |
| `aimilivpn_build_info` | gauge | Build version info |

**Prometheus scrape config:**
```yaml
scrape_configs:
  - job_name: aimilivpn
    static_configs:
      - targets: ["your_vps_ip:9798"]
```

**Disable metrics:**
```yaml
environment:
  - METRICS_ENABLED=false
```

#### 📈 Grafana Dashboard

Pre-configured Grafana Dashboard with service health, latency, CPU/memory, and node pool panels.

**Launch monitoring stack (Prometheus + Grafana):**
```bash
docker compose -f docker-compose.yml -f contrib/docker-compose.monitor.yml up -d
```

Open `http://your_vps_ip:3000` (admin/admin), dashboard auto-imported.

#### 🔄 Auto-Update

Automatically pull the latest image and restart the container via Watchtower:

```bash
# Enable auto-update (checks every 6 hours)
docker compose --profile auto-update up -d
```

#### 🛡️ Security Hardening

Container is hardened by default:
- `cap_drop: ALL` -- Drop all capabilities except NET_ADMIN/NET_RAW
- `no-new-privileges: true` -- Prevent privilege escalation
- `tmpfs: /tmp, /run` -- Isolate temporary filesystems
- Resource limits: 2 CPUs / 512MB memory

---

### 💡 Quick Start Guide

#### Step 1: Access the Web UI
Open your browser and navigate to the printed URL (e.g. `http://your_vps_ip:8787/u71e9IXp4TPx`).

#### Step 2: Select Node and Mode
1. Wait for the program to complete its first automatic node speed benchmarks.
2. Under "Admin", you can trigger node fetching. The backend concurrently tests official VPNGate nodes and ranks them by latency.
3. Switch routes mode (Smart Auto, Specific Region, or Specific Server Node) according to your needs.

#### Step 3: Use Localhost Proxy (Core Step)
To prevent unauthorized scanning and abuse of the proxy port on the public internet, the built-in HTTP/SOCKS5 proxy server (default port **`7928`**) **binds to localhost (`127.0.0.1`) by default**. It is designed to route traffic generated locally on the VPS, rather than acting as a public proxy server.

* **🐍 Proxy in Python**:
  ```python
  import requests
  proxies = {
      "http": "http://127.0.0.1:7928",
      "https": "http://127.0.0.1:7928",
  }
  response = requests.get("https://www.google.com", proxies=proxies)
  ```
* **🐚 Proxy in Shell terminal**:
  ```bash
  export http_proxy="http://127.0.0.1:7928"
  export https_proxy="http://127.0.0.1:7928"
  ```
* **⚙️ Other local services**:
  Configure your scrapers, frameworks, or utility tools on this VPS to send traffic via `127.0.0.1:7928`.

> 💡 **Quick Note**: If you really need to open this proxy port to the public internet, you can set the environment variable `export LOCAL_PROXY_HOST="::"` before running the manager.

---

### ⚠️ Common Troubleshooting (FAQ)

#### 1. Error: `Cannot allocate tun` or `Cannot open tun/tap dev`
* **Reason**: Virtual network adapter (TUN/TAP device) is disabled. This is common in OpenVZ/LXC VPS instances.
* **Solution**: Enable **TUN/TAP** in your VPS SolusVM/KiwiVM control panel, or submit a support ticket to your hosting provider.

#### 2. Cannot open the Web UI in the browser
* **Reason 1**: The built-in firewall (UFW or firewalld) is blocking ports `8787` (Web UI) and `7928` (Proxy).
* **Solution 1**: Allow the ports in your OS firewall:
  * **UFW**: `ufw allow 8787/tcp && ufw allow 7928/tcp`
  * **Firewalld**: `firewall-cmd --add-port=8787/tcp --permanent && firewall-cmd --add-port=7928/tcp --permanent && firewall-cmd --reload`
* **Reason 2**: Service provider security group blocking ports.
* **Solution 2**: **Crucial!** Log in to your cloud provider console (AWS, Aliyun, Oracle Cloud, etc.), locate the **Security Group** for your instance, and add an inbound TCP rule to allow ports `8787` and `7928` from `0.0.0.0/0`.

#### 3. "API Domain Blocked" / Candidate nodes pool is empty (0 nodes)
* **Reason**: The official VPNGate domain is blocked or DNS resolution failed on your VPS.
* **Solution**: Add an HTTP/SOCKS5 upstream proxy in the settings panel (Admin -> Proxy Settings), or configure public DNS in `/etc/resolv.conf` (e.g., `nameserver 8.8.8.8`).

---

### 🎁 Donation Support

If you find this project helpful, you can support its development and maintenance via donation:

* **BNB (BSC / BEP20)**: `0xB6d78c42CEB0687A31B8cfEBE4b51b6eB8953C17`
* **TRX (TRC20)**: `TSdzCW6JvsrqcppodYjhSrku4mYmDJ9pxf`

Thank you for your generosity and support! ❤️
