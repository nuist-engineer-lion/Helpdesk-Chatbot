FROM python:alpine3.19

WORKDIR /app

RUN pip install nonebot-plugin-localstore \
    nonebot_plugin_chatrecorder \
    nonebot-plugin-apscheduler \
    nonebot_plugin_datastore \
    pydantic \
    nonebot-plugin-orm[sqlite] \
    nonebot-adapter-onebot \
    pytz

COPY src ./
COPY bot.py ./
COPY pyproject.toml ./
CMD ["python","bot.py"]