# cwf in a container. Credentials are mounted at run time, never built into the image:
#   docker build -t cwf .
#   docker run --rm -v ~/.aws:/home/cwf/.aws:ro -e AWS_PROFILE=my-profile \
#     -v "$PWD/reports:/reports" cwf scan --region ap-southeast-1 \
#     --format html --output /reports/scan.html
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . && rm -rf /app

RUN useradd --create-home --uid 1000 cwf && mkdir /reports && chown cwf /reports
USER cwf
WORKDIR /home/cwf

ENTRYPOINT ["cwf"]
CMD ["--help"]
