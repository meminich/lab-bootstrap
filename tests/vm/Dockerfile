FROM ubuntu:24.04@sha256:2198e4c65076e9cb0b3d695219df667c0e3b0072da64ca3c2648aca17dcecaf5
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    qemu-system-x86 qemu-utils seabios cloud-image-utils genisoimage openssh-client \
    python3 python3-pexpect ca-certificates curl openssl \
    && rm -rf /var/lib/apt/lists/*
ENV TERM=xterm-256color PYTHONDONTWRITEBYTECODE=1
WORKDIR /work
CMD ["python3", "-B", "/harness/guest_driver.py"]
