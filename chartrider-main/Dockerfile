FROM python:3.11-buster as builder

RUN pip install poetry==1.5.0

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1

WORKDIR /app

COPY pyproject.toml poetry.lock ./

# Install ta-lib
ARG TARGETPLATFORM
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar xf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && \
    echo "[TA-LIB] Building for $TARGETPLATFORM" && \
    ARCHITECTURE=$(case "$TARGETPLATFORM" in \
        "linux/amd64") echo "aarch64-unknown-linux-gnu" ;; \
        "linux/arm64") echo "arm-unknown-linux-gnu" ;; \
        *) echo "amd64-linux" ;; esac) && \
    echo "[TA-LIB] Build architecture $ARCHITECTURE" && \
    ./configure --build arm-linux --prefix=/usr/local && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib-0.4.0-src.tar.gz ta-lib

RUN poetry install --without dev --no-root

FROM python:3.11-slim-buster as runtime

RUN set -xe && \
    apt-get update -y && \
    apt-get install -y git procps && \
    rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="$PYTHONPATH:/app/"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

COPY . /app

WORKDIR /app

ENTRYPOINT ["python"]
