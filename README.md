# 工单客服机器人

## 依赖
```bash
python -m pip install --user pipx
python -m pipx ensurepath
pipx install nb-cli
nb plugin install nonebot-plugin-localstore
nb plugin install nonebot_plugin_chatrecorder
pip install pydantic nonebot-plugin-orm[sqlite] nonebot-adapter-onebot
```