FROM python:3.7
RUN curl -sSL https://sdk.cloud.google.com | bash
RUN mkdir problem-worker
WORKDIR problem-worker
COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY . .
CMD python -u worker.py
