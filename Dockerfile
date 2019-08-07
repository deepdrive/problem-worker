FROM python:3.7
RUN curl -sSL https://sdk.cloud.google.com | bash
ENV PATH="/root/google-cloud-sdk/bin:${PATH}"
RUN gcloud components install docker-credential-gcr
RUN mkdir problem-worker
WORKDIR problem-worker
COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# These files will be shadowed by local files due to pwd mount (see Makefile)
COPY . .

CMD bin/configure_gcloud_docker_service_account.sh && python -u worker.py
