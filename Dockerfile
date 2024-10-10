FROM artefact.skao.int/ska-build-python:0.1.1 as requirements

ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV POETRY_VERSION="1.8.2"

RUN mkdir -p /opt/ska_ser_namespace_manager
WORKDIR /opt/ska_ser_namespace_manager

RUN pip install --upgrade pip && \
    pip install "poetry==${POETRY_VERSION}"

COPY poetry.lock /opt/ska_ser_namespace_manager
COPY pyproject.toml /opt/ska_ser_namespace_manager

RUN poetry export --without-hashes -o requirements.txt

RUN pip install -r /opt/ska_ser_namespace_manager/requirements.txt

FROM artefact.skao.int/ska-python:0.1.1

ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=random
ENV PIP_NO_CACHE_DIR=off
ENV PIP_DISABLE_PIP_VERSION_CHECK=on
ENV PIP_DEFAULT_TIMEOUT=100

RUN mkdir -p /opt/ska_ser_namespace_manager
WORKDIR /opt/ska_ser_namespace_manager
ENV PATH="${PATH}:/opt/ska_ser_namespace_manager"

COPY --from=requirements /usr/local/lib/python3.10 /usr/local/lib/python3.10

RUN apt-get install curl jq -y

COPY src/ /opt/ska_ser_namespace_manager

ENV PYTHONPATH="/opt/ska_ser_namespace_manager"

ENTRYPOINT ["python3", "-u"]
CMD ["/opt/ska_ser_namespace_manager/api.py"]