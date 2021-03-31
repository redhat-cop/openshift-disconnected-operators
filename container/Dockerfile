#FROM registry.access.redhat.com/ubi8/ubi:latest

FROM quay.io/podman/stable
ENV PYCURL_SSL_LIBRARY=openssl

ENV LC_CTYPE=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8

LABEL \
    name="Mirror Operator Catalogue" \
    description="Utility for mirroring operators a la cart " \
    maintainer="RedHat4Gov Team"

USER root

RUN \
    curl -L -o /etc/yum.repos.d/devel:kubic:libcontainers:stable.repo \
    https://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/stable/CentOS_7/devel:kubic:libcontainers:stable.repo \
    && dnf install -y \
        jq \
        autoconf \
        automake \
        git \
        gcc \
        openssl-devel \
        bzip2-devel \
        libffi-devel \
        libtool \
        libmnl \
        zlib-devel \
        make \
        sqlite \
        vim \
        wget \
        which \
    && wget https://raw.githubusercontent.com/arvin-a/openshift-disconnected-operators/cf34b896e44b861c7111dc92f979aad7663f951b/mirror-operator-catalogue.py \
    && chmod +x mirror-operator-catalogue.py \ 
    && wget https://www.python.org/ftp/python/3.7.6/Python-3.7.6.tgz \
    && tar xzvf Python-3.7.6.tgz \
    && rm -f Python-3.7.6.tgz \
    && cd Python-3.7.6 \
    && ./configure --enable-optimizations \
    && make install \
    && python3 -m pip install pyyaml jinja2 \
    && cd - \
    && rm -Rf Python-3.7.6 \
    && wget http://mirror.openshift.com/pub/openshift-v4/clients/ocp/4.7.4/openshift-client-linux-4.7.4.tar.gz \
    && tar xzvf openshift-client-linux-4.7.4.tar.gz \ 
    && rm -f openshift-client-linux-4.7.4.tar.gz \
    && mv oc /usr/bin/ \
    && rm -f kubectl README.md \
    && dnf install -y skopeo \
    && dnf clean all 

COPY ./container/entrypoint.sh ./
COPY ./mirror-operator-catalogue.py ./
COPY ./container/bundle.sh ./
COPY ./catalog-source-template ./
COPY ./image-content-source-template ./
COPY ./known-bad-images ./
COPY ./container/offline-operator-list ./

ENTRYPOINT ["/entrypoint.sh"]
