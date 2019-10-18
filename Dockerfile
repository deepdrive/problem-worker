FROM python:3.7
RUN curl -sSL https://sdk.cloud.google.com | bash
ENV PATH="/root/google-cloud-sdk/bin:${PATH}"
RUN gcloud components install docker-credential-gcr
RUN mkdir problem-worker
WORKDIR problem-worker
COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
RUN git config --global user.email "problem-worker@deepdrive.io"
RUN git config --global user.name "Problem Worker"

# These files will be shadowed by local files due to pwd mount (see Makefile)
COPY . .

ARG CACHEBUST=1

# Make sure we have up to date github backed libs
RUN pip install --upgrade --force-reinstall --ignore-installed --no-cache-dir git+git://github.com/botleague/botleague-helpers#egg=botleague-helpers
RUN pip install --upgrade --force-reinstall --ignore-installed --no-cache-dir git+git://github.com/deepdrive/problem-constants#egg=problem-constants

CMD bin/run.sh
