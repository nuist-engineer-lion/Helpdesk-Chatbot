# 工单客服机器人

## 依赖
```bash
pip install -r .\requirements.txt
```

## 运行
```bash
python bot.py
```

## 配置
当需要双机器人时推荐只使用反向ws，也就是让onebot实现开启反向ws并指向`ws://localhost:8080/onebot/v11/ws`
可用配置项请到config.py中查找
必填项在`.env.example`中可以找到
如果不设置receive_bot和send_bot则会使用同一个机器人同时作接受和通知

## onebot实现
<https://napneko.github.io>
<https://llonebot.github.io>