FROM python:3.12-slim
RUN pip install --no-cache-dir paho-mqtt==2.1.0 psycopg2-binary==2.9.10 "pyjwt[crypto]==2.9.0"
WORKDIR /app
COPY *.py .
COPY static static
ENV PYTHONUNBUFFERED=1
EXPOSE 4100
CMD ["python", "server.py"]
