.PHONY: build push run bash test deploy reboot_vm prepare

TAG=gcr.io/silken-impulse-217423/problem-worker
SSH=gcloud compute ssh nvidia-gpu-cloud-tensorflow-image-1-vm-1

build:
	docker build -t $(TAG) .

push:
	docker push $(TAG)

test: build
	docker run -it $(TAG) test.py

ssh:
	$(SSH)

run:
	docker run -it -v ~/.gcpcreds/:/root/.gcpcreds -v /var/run/docker.sock:/var/run/docker.sock -e GOOGLE_APPLICATION_CREDENTIALS=/root/.gcpcreds/VoyageProject-d33af8724280.json -e INSTANCE_ID=notaninstanceid $(TAG)

bash:
	docker run -it $(TAG) bash
