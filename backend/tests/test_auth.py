"""登录与多用户隔离测试（全部走测试库，不调真模型）。"""


def login(client, username="user1", password="ops123"):
    r = client.post("/api/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_login_ok_and_wrong_password(client):
    r = client.post("/api/login", json={"username": "user1", "password": "ops123"})
    assert r.status_code == 200
    assert r.json()["token"]

    # 密码错：401，且不说明是"用户不存在"还是"密码错"
    r2 = client.post("/api/login", json={"username": "user1", "password": "wrong"})
    assert r2.status_code == 401


def test_sessions_require_login(client):
    # 不带令牌访问会话列表 -> 401
    assert client.get("/api/sessions").status_code == 401
    # 令牌乱填 -> 401
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert client.get("/api/sessions", headers=bad).status_code == 401


def test_session_isolation_between_users(client):
    h1 = login(client, "user1")
    h2 = login(client, "user2")

    # user1 建两个会话
    r = client.post("/api/sessions", json={"title": "我的会话"}, headers=h1)
    assert r.status_code == 201
    sid = r.json()["id"]
    client.post("/api/sessions", json={"title": "第二个"}, headers=h1)

    # user1 看得到自己的 2 个；user2 一个都看不到
    assert len(client.get("/api/sessions", headers=h1).json()["items"]) == 2
    assert client.get("/api/sessions", headers=h2).json()["items"] == []

    # user2 直接访问 user1 的会话 -> 404（不泄露"存在但无权"）
    assert client.get(f"/api/sessions/{sid}", headers=h2).status_code == 404
    # user1 访问自己的 -> 200
    ok = client.get(f"/api/sessions/{sid}", headers=h1)
    assert ok.status_code == 200
    assert ok.json()["title"] == "我的会话"


def test_session_messages_persist(client):
    from models import ChatMessage
    from tests.conftest import TestSession

    h = login(client, "user1")
    sid = client.post("/api/sessions", json={}, headers=h).json()["id"]

    # 直接往测试库塞两条消息（绕开 Agent，避免测试里调真模型）
    with TestSession() as db:
        db.add(ChatMessage(session_id=sid, role="user", content="水温高怎么办？"))
        db.add(ChatMessage(session_id=sid, role="assistant", content="应立即停机。"))
        db.commit()

    got = client.get(f"/api/sessions/{sid}", headers=h).json()
    assert [m["role"] for m in got["messages"]] == ["user", "assistant"]
    assert got["messages"][0]["content"] == "水温高怎么办？"
