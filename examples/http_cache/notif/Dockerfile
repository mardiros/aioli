FROM python:3.13.2-slim
LABEL maintainer="guillaume@gauvr.it"

WORKDIR /srv/notif
EXPOSE 8000

RUN apt-get update && \
    apt-get install -y git && \
    pip install poetry && \
    useradd notif --home /home/notif && \
    mkdir -p /home/notif && \
    chown -R notif:notif /home/notif && \
    chown -R notif:notif /srv/notif
USER notif

COPY pyproject.toml poetry.lock /srv/notif/
RUN poetry install
COPY . /srv/notif/
RUN poetry install

CMD ["poetry", "run", "python", "src/notif/entrypoint.py"]
