# NOTE: Only use this when you want to build image locally
#       else use `docker pull bcsecurity/empire:{VERSION}`
#       all image versions can be found at: https://hub.docker.com/r/bcsecurity/empire/

# -----BUILD COMMANDS----
# 1) build command: `docker build -t bcsecurity/empire .`
# 2) create volume storage: `docker create -v /empire --name data bcsecurity/empire`
# 3) run out container: `docker run -it --volumes-from data bcsecurity/empire /bin/bash`

# -----RELEASE COMMANDS----
# Handled by GitHub Actions

# -----BUILD ENTRY-----

# image base
FROM python:3.11.4-bullseye

# extra metadata
LABEL maintainer="bc-security"
LABEL description="Dockerfile for Empire server and client. https://bc-security.gitbook.io/empire-wiki/quickstart/installation#docker"

# env setup
ENV STAGING_KEY=RANDOM DEBIAN_FRONTEND=noninteractive DOTNET_CLI_TELEMETRY_OPTOUT=1

# set the def shell for ENV
SHELL ["/bin/bash", "-c"]

RUN wget -q https://packages.microsoft.com/config/debian/10/packages-microsoft-prod.deb && \
    dpkg -i packages-microsoft-prod.deb && \
    apt-get update && \
    apt-get install -qq \
    --no-install-recommends \
    apt-transport-https \
    dotnet-sdk-6.0 \
    libicu-dev \
    powershell \
    python3-dev \
    python3-pip \
    sudo \
    xclip \
    zip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /empire

COPY pyproject.toml poetry.lock /empire/

RUN pip install poetry \
    --disable-pip-version-check && \
    poetry config virtualenvs.create false && \
    poetry install --no-root

COPY . /empire

RUN sed -i 's/use: mysql/use: sqlite/g' empire/server/config.yaml

RUN mkdir -p /usr/local/share/powershell/Modules && \
    cp -r ./empire/server/data/Invoke-Obfuscation /usr/local/share/powershell/Modules

RUN rm -rf /empire/empire/server/data/empire*

ENTRYPOINT ["./ps-empire"]
CMD ["server"]
