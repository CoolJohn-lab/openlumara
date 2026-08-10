FROM debian:latest

# avoid interactive prompts during apt
ENV DEBIAN_FRONTEND=noninteractive

# pip is annoying
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# install base tools
RUN apt-get update
RUN apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    cron \
    zip \
    unzip \
    7zip \
    tar \
    jq \
    file \
    tree \
    procps \
    ssh \
    python3 python3-venv python3-pip \
    nodejs npm
RUN apt-get clean

# create user and set up virtual environment
RUN useradd -m -u 1000 -s /bin/bash lumara && chown -R 1000:1000 /home/lumara

# set environment
ENV HOME=/home/lumara

# working directory
WORKDIR /home/lumara

# keep the container alive
CMD ["tail", "-f", "/dev/null"]
