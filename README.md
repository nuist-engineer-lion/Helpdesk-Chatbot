# 工单客服机器人

## 使用

输入指令的中文和英文都可以
预约过的工单可以直接关闭，默认关单者为接单者


- help获取指令
- take 接单 ： 工单建立完成后可以接单
- untake 放单 ： 解除接的工单
- close 关单 ：在接单后可以关单
- qq 搜索 ： 可以用qq号搜索该用户的工单
- qclose qq关单 ： 可以用qq号直接关单，与take一致
- schedule 预约 ： 工单状态转换成预约
- set_schedule 设置默认预约 ： 设置默认的预约内容
- list 列出 ： 列出特定类型的工单
- report 报告 统计 ： 统计关单数量
- send 留言 ： 给特定单号的机主留言

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
如果不设置front_bot和backend_bot则会使用同一个机器人同时作接受和通知

## onebot实现
<https://napneko.github.io>
<https://llonebot.github.io>