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
COPY .env /app

# Build tailwind css
RUN . /root/.nvm/nvm.sh && npm run build

WORKDIR /app/src
RUN poetry run python manage.py collectstatic --noinput


FROM base AS runner

WORKDIR /app/src

COPY --from=builder /app/.venv/ /app/.venv/

COPY pyproject.toml poetry.lock .env /app/
COPY src /app/src

# Copy built static files manifest - _after_ copying the rest of /src/ from the host
COPY --from=builder /app/src/staticfiles/staticfiles.json /app/src/staticfiles/

CMD /app/src/docker-entrypoint.sh

FROM runner AS cron

# Install cron in the container
RUN apt-get update && apt-get install --no-install-recommends -y cron procps

WORKDIR /app/src

# Set the cron environment
RUN echo "PYTHONBUFFERED=1" >> /etc/cron.d/crontab
RUN echo "DJANGO_SETTINGS_MODULE=config.settings.prod" >> /etc/cron.d/crontab
RUN echo "PATH=${POETRY_HOME}/bin:\${PATH}" >> /etc/cron.d/crontab
RUN echo "* * * * * cd /app/src; poetry run python manage.py send_queued_mail > /proc/1/fd/1 2>/proc/1/fd/2" >> /etc/cron.d/crontab
RUN echo "0 1 * * * cd /app/src; poetry run python manage.py cleanup_mail --days=30 --delete-attachments > /proc/1/fd/1 2>/proc/1/fd/2" >> /etc/cron.d/crontab

RUN chmod 0644 /etc/cron.d/crontab && /usr/bin/crontab /etc/cron.d/crontab

CMD ["cron", "-f"]



FROM nginx AS nginx

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /static
COPY --from=builder /app/src/staticfiles /static/
COPY ./nginx/nginx.conf /etc/nginx/conf.d/nginx.conf
