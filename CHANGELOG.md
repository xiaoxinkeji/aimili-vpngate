# Changelog

所有重要变更均记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [v1.51.0] - 2026-08-03

### 新增 (Added)

- `aimilivpn doctor` 诊断命令 (`-d`/`--doctor`) — 一键自检：
  - 本地环境（端口占用 / TUN 设备 / IP 转发 / 防火墙）
  - 系统依赖（openvpn / iptables / ip 可执行文件）
  - 数据源连通性（真实 HTTP 探测区分服务正常 vs TLS 干扰）
  - 运行时数据（节点数据库 / 最近拉取状态）
  - 返回码 0 表示全部通过，1 表示存在问题

- **Web 管理后台安全加固**：
  - 管理密码改为 PBKDF2-SHA256 哈希存储（200k 迭代 + 随机盐），
    `ui_auth.json` 不再保存明文；旧版本明文密码启动时自动迁移，无需手动操作
  - 会话 token 改用 `secrets.token_urlsafe(32)` 强化熵源
  - 新增 CSRF 防护：所有已认证的 POST 请求校验 `Origin`/`Referer` 与
    `Host` 同源，跨站请求返回 403；拒绝 `Origin: null` 边界

### 修复 (Fixes)

- `vpn_utils.diagnose_api_failure()`: TCP 连通时误报 "TLS 干扰"，现通过真实
  HTTP 请求验证，区分服务正常 / HTTP 异常状态码 / TLS 干扰 / 连接超时
- `/api/login` 与 `/api/logout` 处理块缺少 `return`，同一请求产生双重响应
  （200 + 404）并导致 BrokenPipeError 日志污染

## [v1.50.0] - 2026-07-31

### 全项目代码质量改进

本版本专注于代码质量与可靠性提升，共修复 30+ 个缺陷，涉及 17 个文件。

#### 修复 (Fixes)

- **资源泄漏修复 (6 处)**
  - `webhook.py`: HTTP `urlopen` 响应未关闭导致连接泄漏
  - `metrics_exporter.py`: `tcp_port_open()` socket 异常时泄漏
  - `vpn_utils.py`: 带宽测速函数 HTTP 响应未关闭 (×2)
  - `proxy_server.py`: 流量统计文件读写异常静默

- **异常可见性提升 (8 处)**
  - `self_update.py`: 后台更新检查异常被 `pass` 吞噬
  - `metrics_exporter.py`: pgrep 进程读取异常静默
  - `dns_forwarder.py`: `UnicodeDecodeError` 静默 break、`IPV6_V6ONLY` 失败静默 (×2)
  - `proxy_server.py`: 流量统计文件加载/刷盘失败静默 (×2)
  - `vpngate_manager.py`: `except Exception as e` 中 `e` 未使用

- **线程与资源管理 (2 处)**
  - `scheduler.py`: `stop()` 无 thread join/重置，导致无法安全重启
  - `publicvpnlist_scraper.py`: 单节点解析错误导致整页数据丢失

- **环境适配 (1 处)**
  - `docker-stats.py`: 非 TTY 环境输出 ANSI 转义码乱码

- **构建完整性修复 (6 处)**
  - `Dockerfile`: 补充 5 个漏拷贝的 Python 模块
  - `Dockerfile.binary`: 同上
  - `docker-entrypoint.sh` / `docker-host-setup.sh` / `install.sh`: 严格模式 `set -euo pipefail`
  - `aimilivpn.spec`: PyInstaller data files 补充

- **静态分析清理 (11 处)**
  - 移除未使用的 `import re` / `import select`
  - 移除 5 处未用的 `global`/`nonlocal` 声明
  - 修复 4 处空 f-string 前缀
  - pyflakes 警告从 28 → 3 (均为无害)

#### 质量验证

- Python 语法检查：12/12 文件通过
- Shell 语法检查：3/3 文件通过
- pyflakes：28 → 3 个警告
- 安全扫描：无危险函数/硬编码密钥

## [v1.49.2] - 2026-07-28

- 代码质量改进续 (DNS 转发器/Metrics/Shell 脚本)

## [v1.49.1] - 2026-07-27

- PyInstaller spec 补充遗漏 data files (dns_forwarder/scheduler/webhook/geoip)

## [v1.49.0] - 2026-07-27

### 新增 (Added)

- API Key 认证 — 通过 `X-API-Key` 请求头访问受保护 API

## [v1.48.0] - 2026-07-27

### 新增 (Added)

- 按用户流量统计 (UserTrafficAccountant) — JSON 持久化/热重载

## [v1.47.2] - 2026-07-27

### 修复 (Fixes)

- 修复 ACCESS 日志 path 异常
- 修复 alert_rules 空列表不恢复默认规则

## [v1.47.1] - 2026-07-27

### 修复 (Fixes)

- 修复 emit ACCESS 缺少 module 参数
- 修复 config_file KeyError

## [v1.47.0] - 2026-07-27

### 文档 (Docs)

- README 重写 — 完整 API 参考/环境变量表/模块架构/版本历史

## 路线图 (Roadmap)

### v1.51.0 计划

1. **IPv6 支持增强** — 代理/DNS 完整 IPv6 地址族支持
2. **安全加固** — Web UI 会话加密存储、API CSRF 防护、TLS 指纹混淆
3. **可观测性提升** — `/api/debug` 端点、request_id 追踪、Prometheus 节点维度
4. **性能优化** — 节点测试并发自适应、代理中继零拷贝、缓存预加载
5. **运维改进** — `aimilivpn doctor` 诊断命令 ✅、配置热重载扩展、自动备份轮转
