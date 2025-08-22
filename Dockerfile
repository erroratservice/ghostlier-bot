FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Kolkata

# Set timezone non-interactively
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install dependencies (including all required for qbittorrent-nox 4.1.7)
RUN apt-get update && \
    apt-get install -y wget ca-certificates python3 python3-pip python3.8-venv aria2 curl git \
    libssl1.1 libtorrent-rasterbar9 zlib1g \
    libqt5core5a libqt5network5 libqt5xml5

# Detect architecture, download and install correct qbittorrent-nox 4.1.7 .deb
RUN ARCH=$(dpkg --print-architecture) && \
    case "$ARCH" in \
      amd64)  DEB_URL="http://launchpadlibrarian.net/463448601/qbittorrent-nox_4.1.7-1ubuntu3_amd64.deb" ;; \
      arm64)  DEB_URL="http://launchpadlibrarian.net/463448605/qbittorrent-nox_4.1.7-1ubuntu3_arm64.deb" ;; \
      *)      echo "Unsupported architecture: $ARCH" && exit 1 ;; \
    esac && \
    wget -O /tmp/qbittorrent-nox.deb "$DEB_URL" && \
    dpkg -i /tmp/qbittorrent-nox.deb && \
    rm /tmp/qbittorrent-nox.deb

# Verify install
RUN qbittorrent-nox --version

RUN apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR /usr/src/app
RUN chmod 777 /usr/src/app
COPY . .
RUN python3 -m venv ghost
RUN ghost/bin/pip3 install --no-cache-dir -r requirements.txt
RUN chmod +x aria.sh
CMD ["bash", "start.sh"]
