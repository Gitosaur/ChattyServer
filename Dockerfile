FROM python:3.10-slim-bullseye

WORKDIR /usr/src/app

COPY ./requirements.txt .

ENV PYTHONPATH .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000

CMD [ "python", "-u", "./server.py"]
