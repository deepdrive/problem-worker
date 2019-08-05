# problem-worker

Process that runs on all deepdrive evaluation workers responisble for managing local docker container running problems and bots for Deepdrive problems in Botleague.

Process is self-updating from the production branch on GitHub.

Worker is triggered via setting the worker's instance id in a job on Firestore.


## Server setup

```
gcloud auth configure-docker
sudo gcloud components install docker-credential-gcr
sudo apt install python3-pip
sudo apt-get install -y supervisor
cd /usr/local/src
sudo git clone https://github.com/deepdrive/problem-worker
./worker.sh
```
