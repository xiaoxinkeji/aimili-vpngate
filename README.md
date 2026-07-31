# AimiliVPN

[![Docker Image](https://img.shields.io/badge/ghcr.io-xiaoxinkeji%2Faimili--vpngate-blue?logo=docker)](https://github.com/xiaoxinkeji/aimili-vpngate/pkgs/container/aimili-vpngate)
[![GitHub Actions](https://img.shields.io/github/actions/workflow/status/xiaoxinkeji/aimili-vpngate/docker-publish.yml?branch=main&label=build)](https://github.com/xiaoxinkeji/aimili-vpngate/actions)

Bilingual: [Chinese](#chinese) | [English](#english)

---

<a name="chinese"></a>
## Chinese

AimiliVPN is a high-performance, zero-dependency VPN proxy gateway based on the VPNGate open protocol. Written entirely in Python standard library (zero external dependencies), it features concurrent node speed testing, multi-route modes, HTTP/SOCKS5 dual-protocol outbound proxy, DNS leak prevention, offline GeoIP, Prometheus monitoring, and an advanced Web management panel with 30+ REST API endpoints.

---

### Deployment

#### One-Click Script (Debian/Ubuntu/CentOS/Alpine)

```bash
bash <(curl -Ls https://raw.githubusercontent.com/baoweise-bot/aimili-vpngate/main/install.sh)
```

After installation, the terminal outputs a URL with a random security suffix (e.g. `http://your_ip:8787/u71e9IXp4TPx`). Type `ml` in the terminal for an interactive CLI management menu.

#### Docker

Pre-requisite: host must have the TUN kernel module loaded.

```bash
# One-click pre-check script
wget https://raw.githubusercontent.com/xiaoxinkeji/aimili-vpngate/main/docker-host-setup.sh
sudo bash docker-host-setup.sh
```

**docker-compose (Recommended):**

```bash
wget https://raw.githubusercontent.com/xiaoxinkeji/aimili-vpngate/main/docker-compose.yml
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

Required parameters: `--network host`, `--cap-add=NET_ADMIN`, `--device=/dev/net/tun`.

**Container management:**

```bash
docker exec -it aimilivpn docker-stats   # Live status (processes, ports, nodes, routes)
docker logs -f aimilivpn                 # Follow startup logs
docker inspect --format='{{.State.Health.Status}}' aimilivpn  # Health check
```

Container features: startup pre-check (TUN, openvpn, iptables, kernel params), 30s health check, graceful shutdown (SIGTERM cleanup), multi-arch (amd64/arm64), volume persistence.

#### Binary Deployment (No Python/Docker Required)

Single pre-compiled binary with embedded Python interpreter. Requires system-level `openvpn` and `iptables`.

```bash
# Install system dependencies
apt-get install -y openvpn iptables iproute2 curl   # Debian/Ubuntu
yum install -y openvpn iptables iproute curl         # CentOS/RHEL

# Download and run
wget https://github.com/xiaoxinkeji/aimili-vpngate/releases/latest/download/aimilivpn-linux-amd64.tar.gz
tar xzf aimilivpn-linux-amd64.tar.gz
chmod +x aimilivpn
sudo ./aimilivpn
```

CLI commands: `--version`, `--show-auth`, `--check-update`, `--update`.

---

### REST API Reference

All protected APIs require session cookie authentication obtained via `/api/login`. Public endpoints are accessible without authentication.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | Public | Liveness probe (returns uptime) |
| GET | `/ready` | Public | Readiness probe (returns node count) |
| GET | `/metrics` | Public | Prometheus metrics (via metrics_exporter on port 9798) |
| POST | `/api/login` | Public | Session login, returns Set-Cookie |
| POST | `/api/logout` | Session | Invalidate current session |
| GET | `/api/nodes` | Session | List all nodes, supports ?tag=xx filter |
| POST | `/api/nodes/discover` | Session | Trigger manual node discovery |
| GET | `/api/node_perf/<id>` | Session | Node performance history |
| GET | `/api/top_performers` | Session | Top 20 nodes by success rate |
| GET | `/api/tags` | Session | Global tag counts |
| POST | `/api/nodes/<id>/tags` | Session | Set tags on a node |
| GET | `/api/profile` | Session | Current session user profile |
| GET | `/api/proxy_users` | Session | List proxy auth users |
| GET | `/api/rate_limits` | Session | API endpoint rate limiting status |
| GET | `/api/client_limits` | Session | Per-client bandwidth limiter status |
| GET | `/api/client_acls` | Session | IP access control rules (allow/deny) |
| POST | `/api/update_routing` | Session | Update routing mode and strategy |
| GET | `/api/sessions` | Session | Active proxy session list |
| GET | `/api/sessions/<id>` | Session | Single session details (bytes in/out) |
| GET | `/api/logs` | Session | Query audit logs (from_ts/to_ts/level/module) |
| GET | `/api/log_stats` | Session | Log statistics by level and module |
| GET | `/api/alert_rules` | Session | List alert rules |
| POST | `/api/alert_rules` | Session | Replace alert rules |
| GET | `/api/webhook` | Session | Webhook queue and config status |
| GET | `/api/health_full` | Session | Full health check (requires VPN connected) |
| GET | `/api/scheduler` | Session | Scheduler task status |
| POST | `/api/scheduler/trigger/<name>` | Session | Manually trigger a scheduled task |
| GET | `/api/backup/export` | Session | Export full config backup |
| POST | `/api/backup/import` | Session | Import config backup (merge or replace) |
| GET | `/api/dns_stats` | Session | DNS forwarder statistics |
| GET | `/api/geoip_stats` | Session | GeoIP database status |
| GET | `/api/traffic` | Session | Traffic statistics (bytes in/out, throughput) |

---

### Environment Variables

#### Core Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VPNGATE_DATA_DIR` | `/opt/aimilivpn/vpngate_data` | Data directory (state, cache, logs, configs) |
| `UI_HOST` | `::` | Web UI bind address |
| `UI_PORT` | `8787` | Web UI port |
| `LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARN, ERROR) |

#### Proxy Server

| Variable | Default | Description |
|----------|---------|-------------|
| `LOCAL_PROXY_HOST` | `127.0.0.1` | Proxy listen address |
| `LOCAL_PROXY_PORT` | `7928` | HTTP/SOCKS5 proxy port |
| `LOCAL_PROXY_USER` / `LOCAL_PROXY_USERNAME` | (none) | Proxy auth username (single user) |
| `LOCAL_PROXY_PASS` / `LOCAL_PROXY_PASSWORD` | (none) | Proxy auth password (single user) |
| `LOCAL_PROXY_MAX_CONNECTIONS` | `256` | Max concurrent proxy connections |
| `LOCAL_PROXY_RELAY_BUFFER_KB` | `256` | Relay buffer size (KB) |
| `LOCAL_PROXY_USERS_FILE` | (none) | Multi-user JSON file path |
| `LOCAL_PROXY_RATE_LIMIT_PER_S` | `10` | API rate limit (requests/sec) |
| `LOCAL_PROXY_RATE_LIMIT_BURST` | `20` | API rate limit burst |

#### Client ACL and Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `PER_CLIENT_ALLOW_IPS` | (none) | Allowed IPs (comma-separated) |
| `PER_CLIENT_DENY_IPS` | (none) | Denied IPs (comma-separated) |
| `PER_CLIENT_LIMIT_KBPS` | `0` | Per-client bandwidth limit (KB/s, 0=disabled) |
| `PER_CLIENT_BURST_KB` | `0` | Per-client burst allowance (KB) |

#### OpenVPN

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENVPN_CMD` | `openvpn` | OpenVPN executable path |
| `OPENVPN_AUTH_USER` | `vpn` | OpenVPN auth username |
| `OPENVPN_AUTH_PASS` | `vpn` | OpenVPN auth password |
| `OPENVPN_UPSTREAM_SOCKS` | (none) | Upstream SOCKS5 proxy for OpenVPN |
| `OPENVPN_UPSTREAM_USER` / `OPENVPN_UPSTREAM_USERNAME` | (none) | Upstream proxy username |
| `OPENVPN_UPSTREAM_PASS` / `OPENVPN_UPSTREAM_PASSWORD` | (none) | Upstream proxy password |

#### Upstream Proxy for Node Fetching

| Variable | Default | Description |
|----------|---------|-------------|
| `http_proxy` | (none) | HTTP proxy for fetching VPNGate node list |

#### DNS Forwarder

| Variable | Default | Description |
|----------|---------|-------------|
| `DNS_FORWARDER_ENABLED` | (none) | Enable built-in DNS forwarder |
| `DNS_FORWARDER_HOST` | `127.0.0.1` | DNS forwarder bind address |
| `DNS_UPSTREAM_SERVERS` | `8.8.8.8:53,8.8.4.4:53` | Upstream DNS servers |
| `DNS_BLOCKLIST_PATH` | (none) | Ad-block host list path |
| `DNS_BLOCKLIST_ENABLED` | `true` | Enable DNS blocklist filtering |

#### Monitoring

| Variable | Default | Description |
|----------|---------|-------------|
| `METRICS_ENABLED` | `true` | Enable Prometheus metrics exporter |
| `METRICS_PORT` | `9798` | Metrics exporter port |
| `METRICS_HOST` | `0.0.0.0` | Metrics exporter bind address |
| `METRICS_REFRESH_INTERVAL` | `15` | Metrics refresh interval (seconds) |
| `GEOIP_DB_PATH` | (none) | GeoIP offline database CSV path |

#### Webhook Notifications

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_URLS` | (none) | Webhook notification URLs (comma-separated) |
| `WEBHOOK_TIMEOUT` | `10` | Request timeout (seconds) |
| `WEBHOOK_RETRIES` | `3` | Max retry attempts |
| `WEBHOOK_RETRY_DELAY` | `2.0` | Retry delay (seconds) |

#### Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `X_MILI_TOKEN` | (none) | X-MILI integration auth token |

#### Build Info (Metadata)

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAGE_VERSION` | `dev` | Image version string |
| `BUILD_DATE` | `unknown` | Build date |
| `GIT_COMMIT` | `unknown` | Git commit hash |

---

### Core Modules

| Module | Lines | Purpose |
|--------|-------|---------|
| `vpngate_manager.py` | 7,747 | Main entry point -- request dispatch, API routing, node management, session auth, backup, alert rules, scheduler, Web UI |
| `proxy_server.py` | 1,119 | HTTP/SOCKS5 dual-protocol proxy -- SessionTracker, ClientRateLimiter, ACL, multi-user auth, counted relay |
| `vpn_utils.py` | 875 | Shared utilities -- node data management, OpenVPN config generation, probe testing, IP caching, country translation, performance history |
| `dns_forwarder.py` | 482 | Built-in UDP DNS forwarder -- RFC 1035, ad-block filtering, leak prevention |
| `metrics_exporter.py` | 415 | Standalone Prometheus exporter sidecar -- reads state files, exposes /metrics |
| `geoip.py` | 168 | Offline GeoIP -- DB-IP Lite CSV, binary search by IP range |
| `docker-stats.py` | 154 | Container status viewer -- live display of processes, ports, nodes, routes |
| `self_update.py` | 153 | Auto-update module -- GitHub Releases check and binary self-replace |
| `publicvpnlist_scraper.py` | 135 | PublicVPNList scraper -- additional node source beyond VPNGate |
| `metrics.py` | 134 | Prometheus metric definitions and text format output |
| `webhook.py` | 128 | Async webhook notification system -- event queue, retry with backoff |
| `scheduler.py` | 99 | Lightweight task scheduler -- auto_backup (24h), prune_perf_history (24h) |

**Total: ~11,600 lines of pure Python standard library (zero external dependencies).**

---

### Key Features (v1.31.0 - v1.46.0)

**Multi-User Proxy Authentication** -- JSON file-based user list with mtime hot-reload, `secrets.compare_digest` timing-safe comparison.

**Node Performance History** -- Persistent latency/success records per node in `perf_history.json`, used by weighted routing.

**API Endpoint Rate Limiting** -- Token bucket per-API-path, configurable per-second rate and burst.

**Webhook Notifications** -- Async worker with event queue, 4 event types (node.status_change, proxy.health_change, node.blacklisted, proxy.startup), exponential backoff retry.

**Session Tracking** -- Thread-safe session registry tracking per-connection bytes_in/bytes_out across SOCKS5 CONNECT, HTTP CONNECT, and HTTP forward paths.

**Audit Log Query Engine** -- Multi-dimensional filtering (timestamp range, level, module) plus log statistics by level/module grouping.

**Node Tags and Grouping** -- Arbitrary tag assignment per node, global tag counts, tag-based node filtering.

**Per-Client Bandwidth Limiting** -- Token bucket per source IP, 64KB-interval throttling, configurable limit and burst.

**Alert Rules Engine** -- JSON-persisted rules, background 30s evaluation, cooldown dedup, webhook integration, 3 built-in rule types (node_latency, proxy_fail_count, session_count).

**Prometheus Metrics** -- `_MetricFamily` class ensuring proper HELP/TYPE ordering and label value escaping, 16+ metrics across uptime, proxy health, traffic, sessions, nodes, DNS, rate limits, GeoIP.

**IP Access Control** -- Allow/deny IP lists with 403 blocking and cumulative blocked counter.

**Node Auto-Discovery Enhancement** -- IP deduplication, auto-tagging of new nodes as `auto-discovered`.

**Configuration Backup and Restore** -- Export/import nodes, UI config, and alert rules with merge or replace mode.

**Task Scheduler** -- Periodic tasks with configurable intervals, built-in auto_backup and prune_perf_history.

**Weighted Load-Balanced Routing** -- `select_node_weighted` algorithm combining latency (1000/latency), score (1+score/100), and success_rate, top-5 weighted random selection.

---

### Prometheus + Grafana

**Exposed metrics:**

| Metric | Type | Description |
|--------|------|-------------|
| `aimili_uptime_seconds` | gauge | Service uptime |
| `aimili_proxy_healthy` | gauge | Proxy health (1=ok, 0=error) |
| `aimili_traffic_bytes_total` | counter | Total traffic (direction=in/out) |
| `aimili_connections_total` | counter | Total connections |
| `aimili_active_connections` | gauge | Current active connections |
| `aimili_nodes_total` | gauge | Total managed nodes |
| `aimili_nodes_by_status` | gauge | Nodes grouped by probe status |
| `aimili_nodes_by_type` | gauge | Nodes grouped by IP type |
| `aimili_blacklisted_nodes` | gauge | Blacklisted node count |
| `aimili_active_node_latency_ms` | gauge | Active node latency |
| `aimili_active_node_score` | gauge | Active node score |
| `aimili_process_cpu_seconds_total` | counter | Process CPU time |
| `aimili_process_resident_memory_bytes` | gauge | Process RSS memory |
| `aimili_dns_queries_total` | counter | DNS queries served |
| `aimili_dns_blocked_total` | counter | DNS ads blocked |
| `aimili_sessions_active` | gauge | Active proxy sessions |
| `aimili_rate_limit_hits_total` | counter | Rate limit triggers |
| `aimili_build_info` | gauge | Build version metadata |

**Launch monitoring stack:**

```bash
docker compose -f docker-compose.yml -f contrib/docker-compose.monitor.yml up -d
```

Access Grafana at `http://host_ip:3000` (admin/admin), dashboard auto-imported.

**Prometheus scrape config:**

```yaml
scrape_configs:
  - job_name: aimilivpn
    static_configs:
      - targets: ["host_ip:9798"]
```

---

### Quick Start Guide

#### Step 1: Access Web UI

Open the URL printed during deployment (e.g. `http://your_ip:8787/u71e9IXp4TPx`).

#### Step 2: Fetch and Connect Nodes

1. Wait for initial auto-discovery or click **Update Nodes**.
2. The backend concurrently tests all nodes and ranks by latency.
3. Choose routing mode:
   - **Smart Auto** (recommended): automatic failover to healthy nodes
   - **Fixed Region**: best node in a specific country
   - **Fixed IP**: always connect to a specific node

#### Step 3: Use Local Proxy

The proxy (default port **7928**, HTTP/SOCKS5) binds to `127.0.0.1` for local-only access.

**Python:**
```python
import requests
proxies = {"http": "http://127.0.0.1:7928", "https": "http://127.0.0.1:7928"}
response = requests.get("https://www.google.com", proxies=proxies)
```

**Shell:**
```bash
export http_proxy="http://127.0.0.1:7928"
export https_proxy="http://127.0.0.1:7928"
```

To expose the proxy to other devices, set `LOCAL_PROXY_HOST="::"`.

---

### FAQ

**1. "Cannot allocate tun" or "Cannot open tun/tap dev"**

The VPS host does not have TUN/TAP enabled. Enable it in your VPS control panel (SolusVM/Proxmox) or contact your provider.

**2. Web UI not accessible (timeout or connection refused)**

Check firewall rules:
- UFW: `ufw allow 8787/tcp && ufw allow 7928/tcp`
- Firewalld: `firewall-cmd --add-port=8787/tcp --permanent && firewall-cmd --add-port=7928/tcp --permanent && firewall-cmd --reload`
- Cloud security group: add inbound TCP rules for ports 8787 and 7928.

**3. "API Domain Blocked" / zero candidate nodes**

The VPNGate domain may be blocked on your VPS. Configure an upstream proxy via the Web UI settings, or change DNS in `/etc/resolv.conf` to `8.8.8.8` / `1.1.1.1`.

**4. VPN connected but no traffic through proxy**

Your system may have strict reverse path filtering. Run `ml` for the interactive CLI which auto-detects and fixes `rp_filter` settings.

---

### Auto-Update (Docker)

```bash
docker compose --profile auto-update up -d
```

Watchtower checks every 6 hours and automatically pulls the latest image.

### Security Hardening (Docker)

Defaults: `cap_drop: ALL` (only NET_ADMIN/NET_RAW retained), `no-new-privileges: true`, `tmpfs: /tmp, /run`, resource limits (2 CPU / 512MB memory).

---

<a name="english"></a>
## English

AimiliVPN is a high-performance, zero-dependency VPN proxy gateway based on the VPNGate open protocol. Written entirely in Python standard library (zero external dependencies), it features concurrent node speed testing, multi-route modes, HTTP/SOCKS5 dual-protocol outbound proxy, DNS leak prevention, offline GeoIP, Prometheus monitoring, and an advanced Web management panel with 30+ REST API endpoints.

### Deployment

#### One-Click Script

```bash
bash <(curl -Ls https://raw.githubusercontent.com/baoweise-bot/aimili-vpngate/main/install.sh)
```

Type `ml` in the terminal for an interactive CLI management menu.

#### Docker

Pre-requisite: TUN kernel module loaded on the host.

**docker-compose (Recommended):**

```bash
wget https://raw.githubusercontent.com/xiaoxinkeji/aimili-vpngate/main/docker-compose.yml
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

#### Binary Deployment

```bash
wget https://github.com/xiaoxinkeji/aimili-vpngate/releases/latest/download/aimilivpn-linux-amd64.tar.gz
tar xzf aimilivpn-linux-amd64.tar.gz
chmod +x aimilivpn
sudo ./aimilivpn
```

---

### REST API Reference

All protected endpoints require session cookie from `/api/login`. Public endpoints are unauthenticated.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | Public | Liveness probe |
| GET | `/ready` | Public | Readiness probe |
| GET | `/metrics` | Public | Prometheus metrics (port 9798) |
| POST | `/api/login` | Public | Session login |
| POST | `/api/logout` | Session | Invalidate session |
| GET | `/api/nodes` | Session | List nodes, ?tag=xx filter |
| POST | `/api/nodes/discover` | Session | Trigger node discovery |
| GET | `/api/node_perf/<id>` | Session | Node performance history |
| GET | `/api/top_performers` | Session | Top 20 by success rate |
| GET | `/api/tags` | Session | Global tag counts |
| POST | `/api/nodes/<id>/tags` | Session | Set node tags |
| GET | `/api/profile` | Session | Current user profile |
| GET | `/api/proxy_users` | Session | Proxy auth user list |
| GET | `/api/rate_limits` | Session | API rate limit status |
| GET | `/api/client_limits` | Session | Per-client bandwidth limiter |
| GET | `/api/client_acls` | Session | IP access control rules |
| POST | `/api/update_routing` | Session | Update routing strategy |
| GET | `/api/sessions` | Session | Active proxy sessions |
| GET | `/api/sessions/<id>` | Session | Session details |
| GET | `/api/logs` | Session | Audit log query |
| GET | `/api/log_stats` | Session | Log statistics |
| GET | `/api/alert_rules` | Session | Alert rules list |
| POST | `/api/alert_rules` | Session | Replace alert rules |
| GET | `/api/webhook` | Session | Webhook status |
| GET | `/api/health_full` | Session | Full health check |
| GET | `/api/scheduler` | Session | Scheduler status |
| POST | `/api/scheduler/trigger/<name>` | Session | Trigger scheduled task |
| GET | `/api/backup/export` | Session | Export config backup |
| POST | `/api/backup/import` | Session | Import config backup |
| GET | `/api/dns_stats` | Session | DNS forwarder stats |
| GET | `/api/geoip_stats` | Session | GeoIP database status |
| GET | `/api/traffic` | Session | Traffic statistics |

---

### Environment Variables

See the Chinese section above for the complete 30+ variable reference. All variable names and defaults are identical across locales.

---

### Core Modules

| Module | Lines | Purpose |
|--------|-------|---------|
| `vpngate_manager.py` | 7,747 | Main entry point -- request dispatch, API routing, node management, session auth, backup, alert rules, scheduler, Web UI |
| `proxy_server.py` | 1,119 | HTTP/SOCKS5 dual-protocol proxy -- SessionTracker, ClientRateLimiter, ACL, multi-user auth |
| `vpn_utils.py` | 875 | Shared utilities -- node data management, OpenVPN config, probe testing, performance history |
| `dns_forwarder.py` | 482 | Built-in UDP DNS forwarder -- RFC 1035, ad-block filtering |
| `metrics_exporter.py` | 415 | Standalone Prometheus exporter sidecar |
| `geoip.py` | 168 | Offline GeoIP lookup -- DB-IP Lite binary search |
| `webhook.py` | 128 | Async webhook notifications -- event queue, retry |
| `scheduler.py` | 99 | Lightweight task scheduler |
| `metrics.py` | 134 | Prometheus metric definitions |
| `docker-stats.py` | 154 | Container status viewer |
| `self_update.py` | 153 | Binary auto-update |
| `publicvpnlist_scraper.py` | 135 | PublicVPNList scraper |

Total: ~11,600 lines of Python standard library code.

---

### Prometheus + Grafana

```bash
docker compose -f docker-compose.yml -f contrib/docker-compose.monitor.yml up -d
```

Grafana: `http://host_ip:3000` (admin/admin), dashboard auto-imported.

---

### Quick Start Guide

1. Access Web UI at the printed URL
2. Wait for auto-discovery or click **Update Nodes**
3. Select routing mode (Smart Auto / Fixed Region / Fixed IP)
4. Configure your applications to use `127.0.0.1:7928` (HTTP/SOCKS5 proxy)

```python
import requests
proxies = {"http": "http://127.0.0.1:7928", "https": "http://127.0.0.1:7928"}
response = requests.get("https://www.google.com", proxies=proxies)
```

---

### FAQ

See the Chinese section above for common issues (TUN, firewall, domain blocking, rp_filter).

---

### Auto-Update (Docker)

```bash
docker compose --profile auto-update up -d
```

### Security Hardening (Docker)

`cap_drop: ALL`, `no-new-privileges: true`, `tmpfs: /tmp, /run`, resource limits (2 CPU / 512MB memory).

---

### Version History

| Version | Feature |
|---------|---------|
| v1.49.1 | PyInstaller spec 补充遗漏 data files (dns_forwarder/scheduler/webhook/geoip) |
| v1.49.2 | 代码质量改进续 (DNS 转发器/Metrics/Shell 脚本) |
| v1.50.0 | 全项目代码质量改进 (资源泄漏/异常处理) — 16 文件 134+, 78-/pyflakes 28→3/Dockerfile 完整性/Shell 严格模式 |
| v1.49.0 | API Key 认证 — 通过 X-API-Key 请求头访问受保护 API |
| v1.48.0 | 按用户流量统计 (UserTrafficAccountant) — JSON 持久化/热重载 |
| v1.47.2 | 修复 ACCESS 日志 path 异常和 alert_rules 空列表不恢复默认规则 |
| v1.47.1 | 修复 emit ACCESS 缺少 module 参数和 config_file KeyError |
| v1.47.0 | README 重写 — 完整 API 参考/环境变量表/模块架构/版本历史 |
| v1.46.3 | Fix `test_multiple_nodes()` not recording perf history |
| v1.46.2 | Fix `metrics_exporter.py` state variable references |
| v1.46.1 | Fix 6 critical bugs (proxy checker indentation, missing imports, auth, globals) |
| v1.46.0 | Weighted load-balanced routing (`select_node_weighted`) |
| v1.45.0 | Task scheduler (auto_backup, prune_perf_history) |
| v1.44.0 | Configuration backup and restore (export/import) |
| v1.43.0 | Node auto-discovery enhancement (IP dedup, auto-tagging) |
| v1.42.0 | IP access control (allow/deny lists) |
| v1.41.0 | Prometheus metrics endpoint (new `metrics.py` module) |
| v1.40.0 | Alert rules engine |
| v1.39.0 | Per-client bandwidth limiting (token bucket) |
| v1.38.0 | Node tags and grouping |
| v1.37.0 | Audit log query engine |
| v1.36.0 | Proxy session tracking (SessionTracker) |
| v1.35.0 | Webhook notification system |
| v1.34.0 | Enhanced health check (`/api/health_full`) |
| v1.33.0 | API endpoint rate limiting |
| v1.32.0 | Node performance history (`perf_history.json`) |
| v1.31.0 | Multi-user proxy authentication |
| v1.30.0 and earlier | Architecture foundation -- DNS forwarder, SOCKS5 UDP, bandwidth speed test, offline GeoIP, traffic stats, DNS ad-blocking |
