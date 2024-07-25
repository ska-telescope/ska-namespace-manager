FROM python:3.10-alpine as requirements

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

FROM python:3.10-alpine

ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=random
ENV PIP_NO_CACHE_DIR=off
ENV PIP_DISABLE_PIP_VERSION_CHECK=on
ENV PIP_DEFAULT_TIMEOUT=100

RUN mkdir -p /opt/ska_ser_namespace_manager
WORKDIR /opt/ska_ser_namespace_manager
ENV PATH="${PATH}:/opt/ska_ser_namespace_manager"

COPY --from=requirements /opt/ska_ser_namespace_manager/requirements.txt /opt/ska_ser_namespace_manager
RUN pip install -r /opt/ska_ser_namespace_manager/requirements.txt

RUN apk add bash curl jq

COPY src/ /opt/ska_ser_namespace_manager

ENV PYTHONPATH="/opt/ska_ser_namespace_manager"

ENTRYPOINT ["python3", "-u"]
CMD ["/opt/ska_ser_namespace_manager/api.py"]
