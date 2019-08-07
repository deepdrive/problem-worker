# problem-worker

Process that runs on all deepdrive evaluation workers responisble for managing local docker container running problems and bots for Deepdrive problems in Botleague.

Process is self-updating from the production branch on GitHub.

Worker is triggered via setting the worker's instance id in a job on Firestore.


## Requires 

Python 3.7+

## Server setup

Start the NVIDIA GCP instance described [here](https://github.com/deepdrive/problem-endpoint/blob/6872b8df4a9a545918f5adbbd2be41d4dc6fcc57/create-deepdrive-eval-instance.http)

```

sudo git clone https://github.com/deepdrive/problem-worker
./worker.sh
```


```
# Copy creds to /root/.gcpcreds
mkdir ~/.gcpcreds

# On local machine
gcloud compute scp ~/.gcpcreds/silken-impulse-217423-8fbe5bbb2a10.json nvidia-gpu-cloud-tensorflow-image-1-vm-2:~/.gcpcreds/silken-impulse-217423-8fbe5bbb2a10.json
silken-impulse-217423-8fbe5bbb2a10.json

# On server
sudo cp -p /home/craig_voyage_auto/.gcpcreds/silken-impulse-217423-8fbe5bbb2a10.json /root/.gcpcreds

# Clone this repo to /usr/local/src
sudo apt install ruby
sudo gem install pleaserun
sudo pleaserun --install "docker-compose up -d"
sudo systemctl enable docker-compose_up_-d.service
```
