"""Day 9：登录与令牌校验（最小实现）。

流程：用户名+密码 → 校验 → 发一个随机令牌 → 之后每个请求带
     Authorization: Bearer <令牌> → 查到用户 → 接口按用户过滤数据

安全要点（今天记住三条）：
- 绝不存明文密码：存"盐 + 哈希"
- 令牌是随机字符串，登录时现场生成（重新登录换新的）
- 查不到用户和令牌无效都返回同样的 401，不泄露细节
"""

import hashlib
import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import get_db
from models import User

# 演示用固定盐。真实项目：每个用户一个随机盐 + bcrypt/argon2 这类慢哈希
_SALT = "ops-assistant-demo-salt"


def hash_password(password: str) -> str:
    return hashlib.sha256((_SALT + password).encode("utf-8")).hexdigest()


def create_token() -> str:
    return secrets.token_hex(16)  # 32 位十六进制随机串


def login(db: Session, username: str, password: str) -> str | None:
    # 成功返回令牌；用户名或密码错都返回 None（不区分是哪个错）
    user = db.scalar(select(User).where(User.username == username))
    if user is None or user.password_hash != hash_password(password):
        return None
    user.api_token = create_token()
    db.commit()
    return user.api_token


def current_user(authorization: str | None = Header(None),
                 db: Session = Depends(get_db)) -> User:
    # FastAPI 依赖：从请求头里取令牌，查出当前用户；查不到直接 401
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少登录令牌")
    token = authorization.split(" ", 1)[1]
    user = db.scalar(select(User).where(User.api_token == token))
    if user is None:
        raise HTTPException(status_code=401, detail="令牌无效，请重新登录")
    return user
