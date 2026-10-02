"""测试公共设施：所有接口测试都连独立的测试数据库（ops_assistant_test），不碰开发数据。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main
from auth import hash_password
from db import Base
from models import User

TEST_DB_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/ops_assistant_test"

test_engine = create_engine(TEST_DB_URL)
TestSession = sessionmaker(bind=test_engine)


@pytest.fixture()
def client():
    # 每个测试前重建表：测试库永远从空开始，结果才可复现
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)

    # 预置两组测试账户（与 seed.py 的账户一致）
    with TestSession() as s:
        s.add_all([
            User(username="user1", password_hash=hash_password("ops123")),
            User(username="user2", password_hash=hash_password("ops123")),
        ])
        s.commit()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    # 关键一步：把接口内部的 get_db 换成"连测试库"的版本
    # （这就是 FastAPI 的依赖注入：生产用开发库，测试用测试库，接口代码一行不改）
    main.app.dependency_overrides[main.get_db] = override_get_db
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
