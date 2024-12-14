# NOTE: Only use this when you want to build image locally
#       else use `docker pull bcsecurity/empire:{VERSION}`
#       all image versions can be found at: https://hub.docker.com/r/bcsecurity/empire/

# -----BUILD COMMANDS----
# 1) build command: `docker build -t bcsecurity/empire .`
# 2) create volume storage: `docker create -v /empire --name data bcsecurity/empire`
# 3) run out container: `docker run -it --volumes-from data bcsecurity/empire /bin/bash`

FROM python:3.13.0-bullseye

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

RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/bin

ENV PARENT_PATH="/empire"

RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        ARCH="linux-amd64"; \
    elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then \
        ARCH="linux-arm64"; \
    else \
        echo -e "[!] Unsupported architecture: $ARCH. Exiting." && exit 1; \
    fi && \
    curl -L -o /tmp/go.tar.gz https://go.dev/dl/go1.23.2.$ARCH.tar.gz && \
    tar zxf /tmp/go.tar.gz -C /opt && \
    ln -s /opt/go/bin/go /usr/bin/go && \
    rm /tmp/go.tar.gz

WORKDIR /empire

COPY pyproject.toml poetry.lock /empire/

RUN poetry config virtualenvs.create false && \
    poetry install --no-root

COPY . /empire

RUN rm -rf /empire/empire/server/data/empire*

RUN sed -i 's/use: mysql/use: sqlite/g' empire/server/config.yaml && \
    sed -i 's/auto_update: true/auto_update: false/g' empire/server/config.yaml

RUN ./ps-empire -f sync-starkiller
RUN ./ps-empire -f sync-empire-compiler

ENTRYPOINT ["./ps-empire"]
CMD ["-f", "server"]
