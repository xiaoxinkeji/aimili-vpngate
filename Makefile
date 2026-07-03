.PHONY: build push up down logs stats clean shell monitor-up monitor-down auto-update

IMAGE ?= ghcr.io/xiaoxinkeji/aimili-vpngate
TAG   ?= latest
PLATFORMS ?= linux/amd64,linux/arm64

# ── 构建 ──────────────────────────────────────────────
build:
	docker build \
		--build-arg IMAGE_VERSION=$(shell git describe --tags --always --dirty 2>/dev/null || echo "dev") \
		--build-arg BUILD_DATE=$(shell date -u +'%Y-%m-%dT%H:%M:%SZ') \
		--build-arg GIT_COMMIT=$(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown") \
		-t $(IMAGE):$(TAG) \
		.

# 多架构构建 + 推送
buildx:
	docker buildx build \
		--platform $(PLATFORMS) \
		--build-arg IMAGE_VERSION=$(shell git describe --tags --always --dirty 2>/dev/null || echo "dev") \
		--build-arg BUILD_DATE=$(shell date -u +'%Y-%m-%dT%H:%M:%SZ') \
		--build-arg GIT_COMMIT=$(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown") \
		-t $(IMAGE):$(TAG) \
		--push \
		.

push:
	docker push $(IMAGE):$(TAG)

# ── 运行 ──────────────────────────────────────────────
up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

# ── 自动更新 ──────────────────────────────────────────
auto-update:
	docker compose --profile auto-update up -d watchtower

# ── 监控栈 ────────────────────────────────────────────
monitor-up:
	docker compose -f docker-compose.yml -f contrib/docker-compose.monitor.yml up -d

monitor-down:
	docker compose -f docker-compose.yml -f contrib/docker-compose.monitor.yml down

# ── 运维 ──────────────────────────────────────────────
logs:
	docker logs -f --tail 100 aimilivpn

stats:
	docker exec -it aimilivpn docker-stats

shell:
	docker exec -it aimilivpn bash

health:
	@docker inspect --format='{{.State.Health.Status}}' aimilivpn

metrics:
	@curl -s http://localhost:9798/metrics | head -50 || echo "Metrics not available"

# ── 清理 ──────────────────────────────────────────────
# 注意: clean 会删除所有容器数据和配置，使用前请确认
# 用法: make clean CONFIRM=yes
clean:
	@if [ "$(CONFIRM)" != "yes" ]; then \
		echo "!!! 警告: 此操作将删除所有容器、数据和配置"; \
		echo "    如需继续，请执行: make clean CONFIRM=yes"; \
		exit 1; \
	fi
	docker compose down -v
	rm -rf vpngate_data
	docker compose -f contrib/docker-compose.monitor.yml down -v 2>/dev/null || true
