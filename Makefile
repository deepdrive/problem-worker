.PHONY: build push run bash test deploy reboot_vm prepare devrun

TAG=deepdriveio/problem-worker
SSH=gcloud compute ssh nvidia-gpu-cloud-tensorflow-image-1-vm-1
RUN_ARGS=-v ~/.gcpcreds/:/root/.gcpcreds -v /mnt/botleague_results:/mnt/botleague_results -v /var/run/docker.sock:/var/run/docker.sock -v `pwd`:/problem-worker
RUN_ARGS_DEV=$(RUN_ARGS) -e INSTANCE_ID=notaninstanceid -e GOOGLE_APPLICATION_CREDENTIALS=/root/.gcpcreds/VoyageProject-d33af8724280.json

build:
	docker build -t $(TAG) .

push:
	echo Pusing docker container. Note that workers will not use the latest docker container unless they are restarted.
	docker push $(TAG)

test: build
	docker run -it $(TAG) test.py

ssh:
	$(SSH)

run:
	docker run $(RUN_ARGS) --restart=unless-stopped --detach -e LOGURU_LEVEL=INFO $(TAG)

devrun:
	docker run $(RUN_ARGS_DEV) -it $(TAG)

test:
	echo RUNNING TESTS --------------------------------------------------------
	docker run $(RUN_ARGS_DEV) -it $(TAG) python test.py

bash:
	docker run $(RUN_ARGS) -it $(TAG) bash

deploy: test push just_deploy

just_deploy:
	echo Pushing to git so that workers will update automatically once their current job is complete
	echo Press enter if you have commited the changes you want to deploy, otherwise press Ctrl+C
	read whatsayyou
	git push origin master:production
	echo Deployed!
