FROM registry.gitlab.com/ska-telescope/ska-base-images/ska-build-python:0.1.2-dev.c39f576c5 as requirements

RUN mkdir -p /opt/ska_ser_namespace_manager
WORKDIR /opt/ska_ser_namespace_manager

COPY poetry.lock pyproject.toml /opt/ska_ser_namespace_manager/

ENV POETRY_NO_INTERACTION=1
ENV POETRY_VIRTUALENVS_IN_PROJECT=1
ENV POETRY_VIRTUALENVS_CREATE=1

#no-root is required because in the build
#step we only want to install dependencies
#not the code under development
RUN poetry install --no-root

FROM registry.gitlab.com/ska-telescope/ska-base-images/ska-python:0.1.3-dev.c39f576c5

WORKDIR /opt/ska_ser_namespace_manager
#Adding the virtualenv binaries
#to the PATH so there is no need
#to activate the venv
ENV VIRTUAL_ENV=/opt/ska_ser_namespace_manager/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY --from=requirements ${VIRTUAL_ENV} ${VIRTUAL_ENV}

COPY src/ /opt/ska_ser_namespace_manager

#Add source code to the PYTHONPATH
#so python is able to find our package
#when we use it on imports
ENV PYTHONPATH="${PYTHONPATH}:/opt/ska_ser_namespace_manager"

ENTRYPOINT ["python3", "-u"]
CMD ["/opt/ska_ser_namespace_manager/api.py"]