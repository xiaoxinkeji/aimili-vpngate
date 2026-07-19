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
  - Docker 构建: `Dockerfile.xmili` 将 `xmili-integration/vpngate_aimili.go` 和 `vpngate.patch` COPY 到 x-mili 源码中
  - Submodule 有改动时需先 `git checkout` 清理，避免本地修改污染
  - 如需合入上游，需先获得仓库 push 权限后推送并更新 submodule 引用

### Submodule 提交工作流
- Date: 2026-07-19
- Context: Agent 在执行子模块代码管理时记录
- Category: 工作流协作
- Instructions:
  - Submodule 内改动需在子模块内切分支、提交、推送
  - 主项目需更新 submodule 引用 commit 并单独提交
  - 分支命名格式: `YYMMDD-(feat|fix|chore|refactor)-简短描述`
  - 推送时使用 MR 自动创建参数: `-o merge_request.create`
