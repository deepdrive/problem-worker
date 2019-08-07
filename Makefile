.PHONY: build push run bash test deploy reboot_vm prepare devrun

TAG=deepdriveio/problem-worker
SSH=gcloud compute ssh nvidia-gpu-cloud-tensorflow-image-1-vm-1
RUN_ARGS=-v ~/.gcpcreds/:/root/.gcpcreds -v /var/run/docker.sock:/var/run/docker.sock -v `pwd`:/problem-worker
RUN_ARGS_DEV=$(RUN_ARGS) -e INSTANCE_ID=notaninstanceid

build:
	docker build -t $(TAG) .

push:
	docker push $(TAG)

test: build
	docker run -it $(TAG) test.py

ssh:
	$(SSH)

run:
	docker run $(RUN_ARGS) -e LOGURU_LEVEL=INFO -it $(TAG)

devrun:
	docker run $(RUN_ARGS_DEV) -it $(TAG)

bash:
	docker run $(RUN_ARGS) -it $(TAG) bash
