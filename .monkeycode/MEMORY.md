# 用户指令记忆

## 格式

### 用户指令条目
[用户指令摘要]
- Date: [YYYY-MM-DD]
- Context: [提及的场景或时间]
- Instructions:
  - [用户教导或指示的内容，逐行描述]

### 项目知识条目
[项目知识摘要]
- Date: [YYYY-MM-DD]
- Context: Agent 在执行 [具体任务描述] 时发现
- Category: [运维部署|构建方法|测试方法|排错调试|工作流协作|环境配置]
- Instructions:
  - [具体的知识点，逐行描述]

## 去重策略
- 添加新条目前，检查是否存在相似或相同的指令
- 若发现重复，跳过新条目或与已有条目合并
- 合并时，更新上下文或日期信息

## 条目

### PVL SoftEther 节点共享证书体系 (模板生成配置回退)
- Date: 2026-07-19
- Context: Agent 在执行 publicvpnlist.com token API 失效问题排查时发现
- Category: 排错调试
- Instructions:
  - publicvpnlist.com 所有 SoftEther VPN 节点使用完全相同的 CA 证书(1938 chars)、客户端证书(1036 chars)和 RSA 私钥(1692 chars)
  - `pvl_ovpn_template.conf` 保存了剥离 host/port/proto 后的通用配置模板
  - `_generate_pvl_config(host, port, proto)` 可随时为任意 PVL 节点生成有效 OVPN 配置
  - 无需依赖 token API 或 headless browser 即可为所有 PVL 节点提供配置
  - 模板存储在项目根目录 `pvl_ovpn_template.conf`，不可丢失

### vpngate.net API 连接要求
- Date: 2026-07-19
- Context: Agent 在执行 vpngate API 抓取测试时发现
- Category: 运维部署
- Instructions:
  - vpngate.net API (`https://www.vpngate.net/api/iphone/`) 在某些网络环境中被屏蔽或超时
  - 该 API 直接在响应中提供 Base64 编码的 OpenVPN 配置，无需额外下载步骤
  - `fetch_candidates()` 已移除 TUN_AVAILABLE 门控，所有环境下均尝试拉取
  - API 不可达时自动回退到 PVL 源 + 模板生成
  - API 断路器 `API_CIRCUIT_BREAKER_SECONDS` (默认 600s): 连续失败后自动跳过拉取，避免无效请求
  - 指数退避重试: 1s/3s/7s/15s (上限 30s)，无缓存时 3 次重试

### OpenVPN 2.6.x TUN 驱动硬性依赖
- Date: 2026-07-19
- Context: Agent 在无 TUN 内核环境测试 OpenVPN 连通性时确认
- Category: 环境配置
- Instructions:
  - OpenVPN 2.6.14 在数据通道初始化阶段必须打开 `/dev/net/tun`，即使使用 `--dev null` + `--ifconfig-noexec`
  - `--dev null` 仅影响控制通道，无法绕过 TUN 设备打开调用
  - 无 TUN 环境下所有节点测试均返回 ERR_OVPN_TUN_NOT_AVAILABLE (错误代码 2009)
  - `TUN_AVAILABLE = _check_tun()` 使用 `os.open("/dev/net/tun", O_RDWR)` 实际探测
  - 部署环境必须满足：`CONFIG_TUN=y` 内核编译选项 或 `tun` 内核模块可加载

### CI 构建流水线
- Date: 2026-07-19
- Context: Agent 在执行 CI 工作流管理时确认
- Category: 构建方法
- Instructions:
  - 三条 workflow: `binary-release.yml`、`xmili-binary-release.yml`、`docker-publish.yml`
  - Go 版本硬编码为 `1.26` (CI 和 Dockerfile.xmili 中)
  - Docker 镜像: `ghcr.io/xiaoxinkeji/aimili-vpngate:latest`
  - 推送 tag 自动触发构建，tag 命名格式: `v{major}.{minor}.{patch}`
  - 提交格式: `type(vX.Y.Z): 简短描述`
  - 每次提交后必须 push 到 main 分支

### X-MILI submodule 管理
- Date: 2026-07-19
- Context: Agent 在执行 x-mili 子模块集成时确认
- Category: 工作流协作
- Instructions:
  - x-mili submodule 引用 `Aimilibot/X-MILI.git` 的 commit `071dc46`
  - 上游仓库无 push 权限，集成代码在 `xmili-integration/` 目录维护
  - Submodule 内改动需在子模块内切分支 (格式: `YYMMDD-(feat|fix|chore|refactor)-描述`)、提交、推送，使用 `-o merge_request.create` 自动创建 MR
  - 主项目需更新 submodule 引用并单独提交
  - Docker 构建: `Dockerfile.xmili` 将 `xmili-integration/vpngate_aimili.go` 和 `vpngate.patch` COPY 到 x-mili 源码中

### 检测效率 + 弹性容错 + 可观测性 (v1.4.0-v1.6.4)
- Date: 2026-07-20
- Context: Agent 在执行周期检测性能优化与可观测性增强时实现
- Category: 运维部署 / 排错调试
- Instructions:
  - 检测效率四层优化: 冷却跳过 (RETEST_COOLDOWN_SECONDS=900) → 预热加速 (WARMUP_CHECK_INTERVAL_SECONDS=60) → 延迟排序 → 渐进终止/饱和跳过
  - 弹性容错: 电池浮 (GRACE_CYCLES=1) → API 断路器 (API_CIRCUIT_BREAKER_SECONDS=600) → 指数退避重连
  - I/O 优化: BATCH_FLUSH_SIZE=10 批量刷盘 (I/O 降 90%)
  - `_discover_cert_templates()`: 扫描 <ca>/<cert>/<key> 块提取独立证书组合，SHA256 去重，持久化到 cert_templates.json
  - AUTH_FAILED 节点自动尝试替代模板重测
  - Prometheus `/metrics` (9798 端口): 30+ 指标，由 sidecar `metrics_exporter.py` 读取 state.json + nodes.json 生成
  - API gzip 压缩 (>1024 bytes) → 分页 (/api/nodes?offset=N&limit=M)
  - AUTO_EXPIRE_HOURS=48: 持续不可用超时自动移除节点

### API 高可用 + 运行时可观测性 (v1.7.0-v1.12.0)
- Date: 2026-07-23
- Context: Agent 在执行生产级 API 安全加固 + Worker 管理 + 优雅停机 + 结构化日志时实现
- Category: 运维部署
- Instructions:
  - API 速率限制: `API_RATE_LIMIT_PER_MINUTE` (默认 60), IP 级别限流, 超限返回 429
  - `/health` + `/ready` 端点: 免认证健康检查 + 启动就绪探测
  - CORS: 所有响应含 `Access-Control-Allow-Origin: *` + OPTIONS 预检
  - 日志轮转: `LOG_MAX_SIZE_MB` (默认 50), Tee 类内置轮转, 每 60s 检查
  - SIGHUP 热重载: 5s 防抖, 为运行时配置热更新预留钩子
  - Worker 自适应 v2: CPU loadavg (`/proc/loadavg`, `WORKER_CPU_LOAD_LIMIT=0.7`) + 内存阈值 (`WORKER_MEM_LIMIT_MB=500`)
  - `/ws` WebSocket 实时推送: `nodes_updated` + `nodes_expired` 事件广播，死连接自动清理
  - SIGTERM/SIGINT 优雅停机: 广播 WebSocket shutdown → 关闭 HTTP 服务 → 保存 state.json → kill OpenVPN
  - SIGHUP 热重载: 运行时重读 5 个关键环境变量 (RATE_LIMIT, CPU_LOAD, MEM_LIMIT, COOLDOWN, CIRCUIT_BREAKER)
  - `emit(level, module, message)`: 统一 print + log_to_json 接口，Fetcher/Collector/Maintenance/VPN 模块已迁移
  - 新增 `env_float()` 工具函数支持浮点型环境变量
  - `vpngate_manager.py` 是 ~6900 行的单文件 Python 应用 (标准库 only)
  - `metrics_exporter.py` 是独立的 Prometheus sidecar，也仅用标准库
