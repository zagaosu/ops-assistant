"""工单接口的最小业务测试（Day 10 起：接口需登录，且只返回/绑定自己的工单）。"""


def login(client, username="user1"):
    r = client.post("/api/login", json={"username": username, "password": "ops123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_tickets_require_login(client):
    assert client.get("/api/tickets").status_code == 401


def test_list_tickets_empty(client):
    h = login(client)
    resp = client.get("/api/tickets", headers=h)
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0}


def test_create_ticket_ok_and_owner_bound(client):
    h = login(client)
    resp = client.post("/api/tickets", json={"title": "测试工单"}, headers=h)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "测试工单"
    assert data["status"] == "open"
    assert data["owner"] == "user1"  # 归属由服务端绑定，不信客户端

    # 创建后列表里能查到（写进去了）
    listed = client.get("/api/tickets", headers=h).json()
    assert listed["total"] == 1


def test_create_ticket_default_priority(client):
    # 不传 priority -> 落到默认值 medium
    h = login(client)
    resp = client.post("/api/tickets", json={"title": "没写优先级"}, headers=h)
    assert resp.status_code == 201
    assert resp.json()["priority"] == "medium"


def test_create_ticket_with_priority(client):
    # 指定 high -> 存下来；而且列表接口也要返回它（两处都要改对才过）
    h = login(client)
    resp = client.post("/api/tickets", json={"title": "紧急工单", "priority": "high"}, headers=h)
    assert resp.status_code == 201
    assert resp.json()["priority"] == "high"

    listed = client.get("/api/tickets", headers=h).json()
    assert listed["items"][0]["priority"] == "high"


def test_create_ticket_rejects_bad_priority(client):
    # 不在白名单里的值 -> 422，脏数据进不了数据库
    h = login(client)
    resp = client.post("/api/tickets", json={"title": "非法优先级", "priority": "urgent"}, headers=h)
    assert resp.status_code == 422


def test_ticket_isolation_between_users(client):
    h1 = login(client, "user1")
    h2 = login(client, "user2")
    client.post("/api/tickets", json={"title": "user1 的工单"}, headers=h1)

    assert client.get("/api/tickets", headers=h1).json()["total"] == 1
    assert client.get("/api/tickets", headers=h2).json()["total"] == 0


def test_create_ticket_title_too_long(client):
    h = login(client)
    resp = client.post("/api/tickets", json={"title": "长" * 201}, headers=h)
    assert resp.status_code == 422


def test_create_ticket_missing_title(client):
    h = login(client)
    resp = client.post("/api/tickets", json={}, headers=h)
    assert resp.status_code == 422
