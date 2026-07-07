# AimiliVPN + X-MILI 集成说明

X-MILI 是基于 3X-UI + Xray 内核的新一代代理管理面板，内置 VPNGate 公益节点出站。
AimiliVPN 提供更丰富的 VPN 节点源 (VPNGate + publicvpnlist.com) 和节点预检测。

## 集成方式

AimiliVPN 作为 X-MILI 的节点数据提供方 (服务端对接)：

1. AimiliVPN 拉取并检测 VPN 节点
2. X-MILI 通过 HTTP API 获取 AimiliVPN 的节点数据
3. X-MILI 自主管理 OpenVPN 连接和 Xray 路由

## 快速部署

```bash
# 1. 获取代码
git clone --recurse-submodules https://github.com/xiaoxinkeji/aimili-vpngate.git
cd aimili-vpngate

# 2. 预检宿主机环境
sudo bash docker-host-setup.sh

# 3. 启动联合部署
docker compose -f docker-compose.x-mili.yml up -d

# 4. 查看 X-MILI 面板信息
docker logs xmili | grep -E "面板地址|用户名|密码"

# 5. 查看 AimiliVPN 面板信息
docker logs aimilivpn | grep "Web 管理后台"
```

## 端口说明

| 服务 | 端口 | 用途 |
|------|------|------|
| AimiliVPN Web | 8787 | VPN 节点管理后台 |
| AimiliVPN Proxy | 7928 | HTTP/SOCKS5 代理出口 |
| X-MILI Web | 自动分配 | Xray 代理管理面板 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `X_MILI_TOKEN` | `xmili-integration-token-change-me` | 服务间认证令牌，两个服务必须一致 |
| `AIMILI_NODE_API` | `http://127.0.0.1:8787` | AimiliVPN API 地址 (不含 /api/nodes) |

## 工作流程

```
X-MILI 面板                AimiliVPN
    |                         |
    | GET /api/nodes          |
    | (Bearer token)          |
    |------------------------>|
    |                         | 返回 VPNGate + publicvpnlist 节点
    |<------------------------|
    |                         |
    | 用户在 X-MILI 选择节点   |
    | X-MILI 启动 openvpn      |
    | 配置策略路由             |
    | 更新 Xray outbound       |
    |                         |
```

## 手动集成到已有 X-MILI

如果你已单独部署了 X-MILI，可以手动添加 AimiliVPN 支持：

1. 复制 `xmili-integration/vpngate_aimili.go` 到 X-MILI 的 `web/service/`
2. 复制 `xmili-integration/vpngate.patch` 到 X-MILI 根目录
3. 执行: `patch -p1 < vpngate.patch`
4. 重新编译 X-MILI: `go build -o x-ui main.go`
5. 配置环境变量 `AIMILI_NODE_API` 和 `X_MILI_TOKEN`

## 注意事项

- 两个服务都使用 host 网络模式和 TUN 设备，需要宿主机加载 tun 模块
- `X_MILI_TOKEN` 仅用于服务间认证，不会暴露给外部
- AimiliVPN 的 secret_path 对 Bearer token 请求不生效 (直接路径 `/api/nodes`)
