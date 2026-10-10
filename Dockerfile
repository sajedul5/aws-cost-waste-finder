# cwf in a container. Credentials are passed at run time, never built into the image.
#   docker build -t cwf .
# Web page (open http://localhost:8080, enter a name, Scan, Download PDF):
#   docker run --rm --env-file .env -p 127.0.0.1:8080:8080 cwf web --host 0.0.0.0
# Command line:
#   docker run --rm --env-file .env cwf scan --all-regions
# (.env holds AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION; or mount a profile
#  with -v ~/.aws:/home/cwf/.aws:ro -e AWS_PROFILE=name)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
# Pinned, hash-checked dependencies (requirements.lock, made with pip-compile; see docs/decisions.md)
# then cwf itself without pulling anything else.
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-deps . && rm -rf /app

RUN useradd --create-home --uid 1000 cwf && mkdir /reports && chown cwf /reports
USER cwf
WORKDIR /home/cwf

EXPOSE 8080
ENTRYPOINT ["cwf"]
CMD ["--help"]
