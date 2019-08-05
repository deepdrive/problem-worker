# problem-worker

Process that runs on all deepdrive evaluation workers responisble for managing local docker container running problems and bots for Deepdrive problems in Botleague.

Process is self-updating from the production branch on GitHub.

Worker is triggered via setting the worker's instance id in a job on Firestore.


## Requires 

Python 3.7+

## Server setup

Start the NVIDIA GCP instance described [here](https://github.com/deepdrive/problem-endpoint/blob/6872b8df4a9a545918f5adbbd2be41d4dc6fcc57/create-deepdrive-eval-instance.http)

```
sudo apt install python3.7
gcloud auth configure-docker
sudo gcloud components install docker-credential-gcr
sudo apt install python3-pip
sudo apt-get install -y supervisor
cd /usr/local/src
sudo git clone https://github.com/deepdrive/problem-worker
./worker.sh
```
