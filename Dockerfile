FROM artefact.skao.int/ska-build-python-ubuntu26:1.0.0 as requirements

RUN mkdir -p /opt/ska_ser_namespace_manager
WORKDIR /opt/ska_ser_namespace_manager

COPY uv.lock pyproject.toml /opt/ska_ser_namespace_manager/

RUN uv sync --frozen --no-dev --no-install-project

FROM artefact.skao.int/ska-python-ubuntu26:1.0.0

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