FROM debian:trixie-slim

ENV PATH=/python-sdk/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/sdk

# Python install
RUN apt update && \
    apt install -y ca-certificates python3-full python-is-python3 pip locales

RUN sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

RUN mkdir /python-sdk && python3 -m venv /python-sdk

# Install kubernetes clients
RUN apt install -y curl && \
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin && \
    curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 && \
    chmod 700 get_helm.sh && \
    ./get_helm.sh && \
    rm get_helm.sh

# Install Docker
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y \
    gnupg \
    lsb-release && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
    $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    groupadd -g 999 docker && \
    apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce-cli docker-compose-plugin

RUN apt install -y jq genisoimage gettext-base wget

# Install plugin values
#RUN helm plugin install /helm/plugins/chart-downloader

RUN wget https://github.com/mikefarah/yq/releases/download/v4.23.1/yq_linux_amd64 && \
    chmod +x yq_linux_amd64 && \
    mv yq_linux_amd64 /usr/local/bin/yq4 && \
    /python-sdk/bin/pip install yq==2.11.1

RUN GLOW_VERSION=2.1.2 && \
    wget https://github.com/charmbracelet/glow/releases/download/v${GLOW_VERSION}/glow_${GLOW_VERSION}_amd64.deb && \
    dpkg -i glow_${GLOW_VERSION}_amd64.deb && \
    rm glow_${GLOW_VERSION}_amd64.deb

RUN mkdir /tmp/kube && cd /tmp/kube && VER=0.9.4 && \
    wget https://github.com/ahmetb/kubectx/releases/download/v${VER}/kubectx_v${VER}_linux_x86_64.tar.gz && \
    wget https://github.com/ahmetb/kubectx/releases/download/v${VER}/kubens_v${VER}_linux_x86_64.tar.gz && \
    tar xzvf kubectx_v${VER}_linux_x86_64.tar.gz && \
    tar xzvf kubens_v${VER}_linux_x86_64.tar.gz && \
    mv kubectx /usr/local/bin && \
    mv kubens /usr/local/bin && \
    cd /tmp && rm -rf /tmp/kube

RUN apt-get install -y nano vim rsync git inetutils-ping telnet curl sudo bash-completion dnsutils uuid-runtime gettext-base zip

RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy SDK source and install dependencies
COPY sdk /sdk
WORKDIR /sdk

# Python deps
RUN mkdir -p /data /sdk/k8s && \
    /python-sdk/bin/pip install .

EXPOSE 22

WORKDIR /home/sdk

ENTRYPOINT ["/sdk/ost"]
