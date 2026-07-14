FROM python:3.14-slim AS base

ENV POETRY_HOME=/opt/poetry
ENV PATH=${POETRY_HOME}/bin:${PATH}
ENV DJANGO_SETTINGS_MODULE=config.settings.prod

RUN apt-get update \
  && apt-get install --no-install-recommends -y \
  curl default-libmysqlclient-dev netcat-traditional libxmlsec1 libxmlsec1-dev libxml2-dev \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 - && poetry --version


# Use a seperate builder image to minimise rebuild time
FROM base AS builder

WORKDIR /app
RUN apt-get update \
  && apt-get install --no-install-recommends -y \
  pkg-config build-essential

# Install NVM in our python project
RUN curl https://raw.githubusercontent.com/creationix/nvm/master/install.sh | bash

COPY pyproject.toml poetry.lock /app/

RUN poetry config virtualenvs.in-project true && \
  poetry install --only main --no-interaction

# This workaround is due to known bug https://github.com/nvm-sh/nvm/issues/1985 with nvm
WORKDIR /tailwindcss
COPY .nvmrc ./

WORKDIR /app
RUN . /root/.nvm/nvm.sh && nvm install $(cat /tailwindcss/.nvmrc) && nvm use $(cat /tailwindcss/.nvmrc)

COPY package.json package-lock.json styles.css ./
RUN . /root/.nvm/nvm.sh && npm install

COPY src /app/src

# Build tailwind css
RUN . /root/.nvm/nvm.sh && npm run build

# collectstatic uses a credential-free build settings module so that no .env
# file needs to be present inside the image. Runtime secrets are injected at
# startup via docker-compose env_file.
WORKDIR /app/src
RUN DJANGO_SETTINGS_MODULE=config.settings.build poetry run python manage.py collectstatic --noinput --skip-checks


FROM base AS runner

WORKDIR /app/src

COPY --from=builder /app/.venv/ /app/.venv/

COPY pyproject.toml poetry.lock /app/
COPY src /app/src

# Copy built static files manifest - _after_ copying the rest of /src/ from the host
COPY --from=builder /app/src/staticfiles/staticfiles.json /app/src/staticfiles/

CMD /app/src/docker-entrypoint.sh

FROM runner AS cron

WORKDIR /app/src

# Run the mail worker as PID 1 (not system cron): cron scrubs the environment, so
# a cron job cannot see the secrets injected via docker-compose env_file and Django's
# prod settings fail to load — the historical cause of verification emails piling up
# unsent in the queue. Running as a child of PID 1 inherits the full environment.
COPY scripts/mail-worker.sh /usr/local/bin/mail-worker.sh
RUN chmod +x /usr/local/bin/mail-worker.sh

CMD ["/usr/local/bin/mail-worker.sh"]



FROM nginx AS nginx

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /static
COPY --from=builder /app/src/staticfiles /static/
COPY ./nginx/nginx.conf /etc/nginx/conf.d/nginx.conf
