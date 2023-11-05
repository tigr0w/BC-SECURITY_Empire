# NOTE: Only use this when you want to build image locally
#       else use `docker pull bcsecurity/empire:{VERSION}`
#       all image versions can be found at: https://hub.docker.com/r/bcsecurity/empire/

# -----BUILD COMMANDS----
# 1) build command: `docker build -t bcsecurity/empire .`
# 2) create volume storage: `docker create -v /empire --name data bcsecurity/empire`
# 3) run out container: `docker run -it --volumes-from data bcsecurity/empire /bin/bash`

FROM python:3.12.0-bullseye

LABEL maintainer="bc-security"
LABEL description="Dockerfile for Empire server and client. https://bc-security.gitbook.io/empire-wiki/quickstart/installation#docker"

ENV STAGING_KEY=RANDOM DEBIAN_FRONTEND=noninteractive DOTNET_CLI_TELEMETRY_OPTOUT=1

SHELL ["/bin/bash", "-c"]

RUN wget -q https://packages.microsoft.com/config/debian/11/packages-microsoft-prod.deb && \
    dpkg -i packages-microsoft-prod.deb && \
    apt-get update && \
    apt-get install -qq \
    --no-install-recommends \
    apt-transport-https \
    dotnet-sdk-6.0 \
    libicu-dev \
    powershell \
    sudo \
    xclip \
    zip \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 -
RUN ln -s /root/.local/bin/poetry /usr/bin

WORKDIR /empire

COPY pyproject.toml poetry.lock /empire/

RUN poetry config virtualenvs.create false && \
    poetry install --no-root

COPY . /empire

RUN mkdir -p /usr/local/share/powershell/Modules && \
    cp -r ./empire/server/data/Invoke-Obfuscation /usr/local/share/powershell/Modules

RUN rm -rf /empire/empire/server/data/empire*

RUN sed -i 's/use: mysql/use: sqlite/g' empire/server/config.yaml
RUN sed -i 's/auto_update: true/auto_update: false/g' empire/server/config.yaml

RUN ./ps-empire sync-starkiller

ENTRYPOINT ["./ps-empire"]
CMD ["server"]
