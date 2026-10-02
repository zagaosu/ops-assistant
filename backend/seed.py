"""写入示例数据：两组测试账户 + 3 条示例工单（已有则跳过）。

运行：D:/anaconda/envs/spider_env/python.exe -X utf8 seed.py
"""

from sqlalchemy import select

from auth import hash_password
from db import SessionLocal
from models import Ticket, User

USERS = [("user1", "ops123"), ("user2", "ops123")]

TICKETS = [
    {"title": "3 号冷却泵高温停机", "status": "open", "owner": "user1"},
    {"title": "电池组充电异常告警", "status": "in_progress", "owner": "user2"},
    {"title": "日志采集服务重启", "status": "closed", "owner": "user3"},
]

with SessionLocal() as db:
    for username, password in USERS:
        if db.scalar(select(User).where(User.username == username)) is None:
            db.add(User(username=username, password_hash=hash_password(password)))
            print(f"已创建用户 {username}（密码 {password}）")
        else:
            print(f"用户 {username} 已存在，跳过")
    db.commit()

    if db.scalars(select(Ticket)).first() is None:
        db.add_all([Ticket(**t) for t in TICKETS])
        db.commit()
        print(f"已写入 {len(TICKETS)} 条示例工单")
    else:
        print("工单表已有数据，跳过")
