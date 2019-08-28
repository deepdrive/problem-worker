# problem-worker

Process that runs on all deepdrive evaluation workers responisble for managing local docker container running problems and bots for Deepdrive problems in Botleague.

Process is self-updating from the production branch on GitHub.

Worker is triggered via setting the worker's instance id in a job on Firestore.

This process runs in a docker container and starts the sim or bot container via mapping the docker socket.

Instance managed by the [problem-endpoint](https://github.com/deepdrive/problem-endpoint)


## Requires 

Python 3.7+
Docker

## Server setup

Start the NVIDIA GCP instance described [here](https://github.com/deepdrive/problem-endpoint/tree/229dec8a12663791c05b772cd65c2c5903c6d9eb/cloud_configs)

```
mkdir ~/.gcpcreds

# On local machine
gcloud compute scp ~/.gcpcreds/silken-impulse-217423-8fbe5bbb2a10.json <your-problem-worker>:~/.gcpcreds/silken-impulse-217423-8fbe5bbb2a10.json
silken-impulse-217423-8fbe5bbb2a10.json

# On server
sudo mkdir /root/.gcpcreds
sudo cp /home/craig_voyage_auto/.gcpcreds/silken-impulse-217423-8fbe5bbb2a10.json /root/.gcpcreds/

# Clone repo
cd /usr/local/src
sudo git clone https://github.com/deepdrive/problem-worker --branch production

# Perform initial run
cd problem-worker
make run
docker ps
docker logs <your-new-container-name> -f

```
If everything looks good after 10 seconds, the container will run on boot and 
restart if it dies.
c.f. [docker restart](https://docs.docker.com/engine/reference/run/#restart-policies---restart)

Now stop the instance (leave the container running so it restarts) 
and create an image to fully bake your new eval VM!


Note that from now on, the source will be automatically updated with the 
auto_updater using git. There's no need to rebuild the container even if 
the python dependencies change (since we install requirements.txt on start
and will restart if requirements.txt changes).

If you do need to update the container, you'll have to bake a new VM image
and reference that image in problem-coordinator.
