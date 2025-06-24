FROM artefact.skao.int/ska-build-python:sha256-e8cdbbd576939f704e1914cf8fa0d53a77629fc689d4fb07a4513d22cb62e07c as requirements

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

FROM artefact.skao.int/ska-python:sha256-f7f35cd442950c4a7dc90d1b157ce98322dec246771a5c00b65b1d897465bf70

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