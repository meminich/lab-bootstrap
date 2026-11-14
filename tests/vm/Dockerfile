FROM ubuntu:22.04@sha256:74b12b11ffa550fba1929ad4d8d16533c34f6612728469671afba1b03b66881c
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    qemu-system-x86 qemu-utils cloud-image-utils genisoimage openssh-client \
    python3 python3-pexpect ca-certificates curl openssl \
    && rm -rf /var/lib/apt/lists/*
ENV TERM=xterm-256color PYTHONDONTWRITEBYTECODE=1
WORKDIR /work
CMD ["python3", "-B", "/harness/guest_driver.py"]
