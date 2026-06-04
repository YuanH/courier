IMAGE ?= courier:latest
CONTAINER ?= courier
CONFIG ?= $(PWD)/config.yaml
DATA_VOLUME ?= courier-data

.PHONY: help build run stop restart rebuild logs ps shell data test-item clean

help:
	@echo "Courier Podman commands:"
	@echo "  make build     Build $(IMAGE)"
	@echo "  make run       Run $(CONTAINER) using ./config.yaml and $(DATA_VOLUME)"
	@echo "  make stop      Stop $(CONTAINER) if running"
	@echo "  make restart   Restart $(CONTAINER) without rebuilding"
	@echo "  make rebuild   Stop, build, and run $(CONTAINER)"
	@echo "  make logs      Follow container logs"
	@echo "  make ps        Show Courier container status"
	@echo "  make data      Show /data contents in the container"
	@echo "  make test-item Send a synthetic test item using config.yaml"
	@echo "  make shell     Open a shell in the container"
	@echo "  make clean     Stop and remove the container"

build:
	podman build -t $(IMAGE) -f Containerfile .

run:
	podman run -d \
		--name $(CONTAINER) \
		--replace \
		--restart=unless-stopped \
		-v "$(CONFIG):/config/config.yaml:ro" \
		-v $(DATA_VOLUME):/data \
		$(IMAGE)

stop:
	-podman stop $(CONTAINER)

restart:
	podman restart $(CONTAINER)

rebuild: stop build run

logs:
	podman logs -f $(CONTAINER)

ps:
	podman ps --filter name=$(CONTAINER) --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.RunningFor}}'

data:
	podman exec $(CONTAINER) sh -lc 'ls -la /data; test -f /data/state.json && cat /data/state.json || true'

test-item:
	uv run python scripts/send_test_item.py -c config.yaml

shell:
	podman exec -it $(CONTAINER) sh

clean: stop
	-podman rm $(CONTAINER)
