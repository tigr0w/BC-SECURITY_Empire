# NOTE: Only use this when you want to build image locally
#       else use `docker pull bcsecurity/empire:{VERSION}`
#       all image versions can be found at: https://hub.docker.com/r/bcsecurity/empire/

# -----BUILD COMMANDS----
# 1) build command: `docker build -t bcsecurity/empire .`
# 2) create volume storage: `docker create -v /empire --name data bcsecurity/empire`
# 3) run out container: `docker run -it --volumes-from data bcsecurity/empire /bin/bash`

FROM python:3.12.2-bullseye

LABEL maintainer="bc-security"
LABEL description="Dockerfile for Empire server and client. https://bc-security.gitbook.io/empire-wiki/quickstart/installation#docker"

ENV STAGING_KEY=RANDOM DEBIAN_FRONTEND=noninteractive DOTNET_CLI_TELEMETRY_OPTOUT=1

SHELL ["/bin/bash", "-c"]

RUN apt-get update && \
    apt-get install -qq \
    --no-install-recommends \
    apt-transport-https \
    libicu-dev \
    sudo \
    xclip \
    zip \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN unameOut="$(uname -m)" && \
    case "$unameOut" in \
      x86_64) export arch=x64 ;; \
      aarch64) export arch=arm64 ;; \
      *) exit 1;; \
    esac && \
    curl -L -o /tmp/powershell.tar.gz https://github.com/PowerShell/PowerShell/releases/download/v7.3.9/powershell-7.3.9-linux-$arch.tar.gz && \
    mkdir -p /opt/microsoft/powershell/7 && \
    tar zxf /tmp/powershell.tar.gz -C /opt/microsoft/powershell/7 && \
    chmod +x /opt/microsoft/powershell/7/pwsh && \
    ln -s /opt/microsoft/powershell/7/pwsh /usr/bin/pwsh && \
    rm /tmp/powershell.tar.gz


RUN wget https://dot.net/v1/dotnet-install.sh -O dotnet-install.sh && \
    chmod +x ./dotnet-install.sh && \
    ./dotnet-install.sh --channel 6.0 && \
    ln -s /root/.dotnet/dotnet /usr/bin/dotnet && \
    rm dotnet-install.sh

RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/bin

WORKDIR /empire

COPY pyproject.toml poetry.lock /empire/

RUN poetry config virtualenvs.create false && \
    poetry install --no-root

COPY . /empire

RUN mkdir -p /usr/local/share/powershell/Modules && \
    cp -r ./empire/server/data/Invoke-Obfuscation /usr/local/share/powershell/Modules && \
    rm -rf /empire/empire/server/data/empire*

RUN sed -i 's/use: mysql/use: sqlite/g' empire/server/config.yaml && \
    sed -i 's/auto_update: true/auto_update: false/g' empire/server/config.yaml

RUN ./ps-empire sync-starkiller

ENTRYPOINT ["./ps-empire"]
CMD ["server"]
