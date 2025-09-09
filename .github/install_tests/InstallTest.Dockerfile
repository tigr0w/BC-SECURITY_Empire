# syntax=docker/dockerfile:1.4
ARG BASE_IMAGE
FROM $BASE_IMAGE
WORKDIR /empire
COPY . /empire

SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get -y install sudo openssh-client git

# Add a non-root user
RUN echo 'empire ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers
RUN useradd -m empire
RUN chown -R empire:empire /empire
USER empire

RUN sed -i 's/use: mysql/use: sqlite/g' empire/server/config.yaml
RUN ssh-keyscan -H github.com | sudo tee -a /etc/ssh/ssh_known_hosts > /dev/null
RUN --mount=type=ssh,mode=0666 \
    yes | /empire/setup/install.sh
RUN rm -rf /empire/empire/server/data/empire*
