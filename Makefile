.PHONY: build push up down logs stats clean shell

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

# 多架构构建 (需要 buildx)
buildx:
	docker buildx build \
		--platform $(PLATFORMS) \
		--build-arg IMAGE_VERSION=$(shell git describe --tags --always --dirty 2>/dev/null || echo "dev") \
		--build-arg BUILD_DATE=$(shell date -u +'%Y-%m-%dT%H:%M:%SZ') \
		--build-arg GIT_COMMIT=$(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown") \
		-t $(IMAGE):$(TAG) \
		--push \
		.

# 推送
push:
	docker push $(IMAGE):$(TAG)

# ── 运行 ──────────────────────────────────────────────
up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

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
	@curl -s http://localhost:9798/metrics || echo "Metrics not available, ensure METRICS_ENABLED=true"

# ── 清理 ──────────────────────────────────────────────
clean:
	docker compose down -v
	rm -rf vpngate_data
