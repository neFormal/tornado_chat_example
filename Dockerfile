FROM ubuntu:16.04
MAINTAINER Me <localhost@localdomain>
RUN apt-get update && apt-get install -y git python3 python3-pip sqlite3

RUN cd /tmp \
    && git clone https://github.com/neFormal/tornado_chat_example.git chat \
    && cd chat \
    && pip3 install -r reqs.txt

EXPOSE 8000
CMD ["python3", "/tmp/chat/test.py"]
