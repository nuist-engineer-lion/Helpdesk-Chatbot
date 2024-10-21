FROM python:alpine3.19

WORKDIR /app

COPY requirements.txt ./

RUN pip install -r requirements.txt

COPY src ./
COPY bot.py ./
COPY pyproject.toml ./
CMD ["python","bot.py"]