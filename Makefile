.PHONY: build push run bash test deploy reboot_vm prepare devrun

TAG=deepdriveio/problem-worker
SSH=gcloud beta compute --project "silken-impulse-217423" ssh --zone "us-west1-b" "deepdrive-worker-0"
CONTAINER_NAME=problem_worker
RUN_ARGS=--name $(CONTAINER_NAME) -v ~/.gcpcreds/:/root/.gcpcreds -v /mnt/botleague_results:/mnt/botleague_results -v /var/run/docker.sock:/var/run/docker.sock -v `pwd`:/problem-worker
RUN_ARGS_DEV=$(RUN_ARGS) --net=host -e INSTANCE_ID=notaninstanceid -e GOOGLE_APPLICATION_CREDENTIALS=/root/.gcpcreds/VoyageProject-d33af8724280.json
CACHEBUST:=$(shell date +%s)

build:
	docker build  --network=host --build-arg CACHEBUST=$(CACHEBUST) -t $(TAG) .

push:
	echo Pusing docker container. Note that workers will not use the latest docker container unless they are restarted.
	docker push $(TAG)

ssh:
	$(SSH)

remove_old:
	docker rm $(CONTAINER_NAME) || echo no container, good

run: remove_old
	docker run $(RUN_ARGS) --restart=unless-stopped --detach -e LOGURU_LEVEL=INFO $(TAG)

devrun: remove_old
	docker run $(RUN_ARGS_DEV) -it $(TAG)

test: remove_old build
	echo RUNNING TESTS --------------------------------------------------------
	docker run $(RUN_ARGS_DEV) -it $(TAG) python test.py

test_dummy: remove_old build
	echo RUNNING TEST DUMMY --------------------------------------------------------
	docker run $(RUN_ARGS_DEV) -it $(TAG) python test.py test_dummy_container

test_eval: remove_old build
	echo RUNNING TEST DUMMY --------------------------------------------------------
	docker run $(RUN_ARGS_DEV) -it $(TAG) python test.py test_domain_randomization

test_build: remove_old build
	echo RUNNING TEST DUMMY --------------------------------------------------------
	docker run $(RUN_ARGS_DEV) -it $(TAG) python test.py test_build_sim

bash: remove_old
	docker run $(RUN_ARGS) -it $(TAG) bash

deploy: deploy_confirm test push just_deploy

quick_deploy: deploy_confirm test_dummy push just_deploy

deploy_confirm:
	echo Pushing to git so that workers will update automatically once their current job is complete
	echo Press enter if you have commited the changes you want to deploy to master, otherwise press Ctrl+C
	read whatsayyou

just_deploy:
	git push origin master:production
	echo Deployed!
