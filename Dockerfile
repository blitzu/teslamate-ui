FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py VERSION CHANGELOG.md ./
COPY features features
COPY static static
ARG BUILD_COMMIT=
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 BUILD_COMMIT=${BUILD_COMMIT}
EXPOSE 4100
# server.py starts as root only to give /data to an unprivileged user (APP_UID, default 10001) and then drops root before doing anything else
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:4100/api/health', timeout=4).status == 200 else 1)"
CMD ["python", "server.py"]
