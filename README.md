# problem-worker

Process that runs on all deepdrive evaluation workers responisble for managing local docker container running problems and bots for Deepdrive problems in Botleague.

Process is self-updating from the production branch on GitHub.

Worker is triggered via setting the worker's instance id in a job on Firestore.


## Requires 

Python 3.7+

## Server setup

Start the NVIDIA GCP instance described [here](https://github.com/deepdrive/problem-endpoint/blob/6872b8df4a9a545918f5adbbd2be41d4dc6fcc57/create-deepdrive-eval-instance.http)

```
mkdir ~/.gcpcreds

# On local machine
gcloud compute scp ~/.gcpcreds/silken-impulse-217423-8fbe5bbb2a10.json nvidia-gpu-cloud-tensorflow-image-1-vm-2:~/.gcpcreds/silken-impulse-217423-8fbe5bbb2a10.json
silken-impulse-217423-8fbe5bbb2a10.json

# On server
sudo mkdir /root/.gcpcreds
sudo cp /home/craig_voyage_auto/.gcpcreds/silken-impulse-217423-8fbe5bbb2a10.json /root/.gcpcreds/

# Clone repo
cd /usr/local/src
sudo git clone https://github.com/deepdrive/problem-worker 

# Note that the repo gets auto-updated with pushes to the production branch
sudo apt install ruby
sudo gem install pleaserun
sudo pleaserun --install --overwrite --name problem-worker --platform systemd /usr/local/src/problem-worker/bin/run_problem_worker.sh
sudo systemctl enable problem-worker
sudo systemctl start problem-worker

# Check the logs
sudo journalctl -u problem-worker -e -f
```
