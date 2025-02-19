FROM python:3.14.0a1-slim
LABEL maintainer="guillaume@gauvr.it"

WORKDIR /srv/user
EXPOSE 8000

RUN pip install poetry

RUN useradd user --home /home/user && \
    mkdir -p /home/user && \
    chown -R user:user /home/user && \
    chown -R user:user /srv/user
USER user

COPY pyproject.toml poetry.lock /srv/user/
RUN poetry install
COPY . /srv/user/
RUN poetry install

CMD ["poetry", "run", "python", "src/user/__init__.py"]
