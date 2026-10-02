"""工单草稿与确认流程测试：事务、重复确认去重、版本校验、归属隔离。"""


def login(client, username="user1"):
    r = client.post("/api/login", json={"username": username, "password": "ops123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def make_draft(client, h, title="草稿工单", content="水温 95 度"):
    r = client.post("/api/drafts", json={"title": title, "content": content}, headers=h)
    assert r.status_code == 201
    return r.json()


def test_confirm_creates_ticket_once(client):
    h = login(client)
    d = make_draft(client, h)

    # 第一次确认：真正写入工单
    r = client.post(f"/api/drafts/{d['id']}/confirm", json={"version": d["version"]}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["already_confirmed"] is False
    assert body["ticket"]["title"] == "草稿工单"
    assert body["ticket"]["owner"] == "user1"

    # 重复确认（模拟手抖点两次）：不再写第二张，返回同一张
    r2 = client.post(f"/api/drafts/{d['id']}/confirm", json={"version": d["version"]}, headers=h)
    assert r2.status_code == 200
    assert r2.json()["already_confirmed"] is True
    assert r2.json()["ticket"]["id"] == body["ticket"]["id"]

    # 工单表里只有 1 张
    assert client.get("/api/tickets", headers=h).json()["total"] == 1


def test_cancel_does_not_write_ticket(client):
    h = login(client)
    d = make_draft(client, h)

    r = client.post(f"/api/drafts/{d['id']}/cancel", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"

    # 取消后不能确认
    r2 = client.post(f"/api/drafts/{d['id']}/confirm", json={"version": d["version"]}, headers=h)
    assert r2.status_code == 409

    # 工单表里一张都没有（取消 = 不写入）
    assert client.get("/api/tickets", headers=h).json()["total"] == 0


def test_confirm_version_mismatch_rejected(client):
    h = login(client)
    d = make_draft(client, h)
    r = client.post(f"/api/drafts/{d['id']}/confirm", json={"version": 999}, headers=h)
    assert r.status_code == 409
    assert client.get("/api/tickets", headers=h).json()["total"] == 0


def test_draft_isolation_between_users(client):
    h1 = login(client, "user1")
    h2 = login(client, "user2")
    d = make_draft(client, h1)

    # user2 看不到 user1 的草稿
    assert client.get("/api/drafts", headers=h2).json()["items"] == []
    # user2 也不能确认 user1 的草稿
    r = client.post(f"/api/drafts/{d['id']}/confirm", json={"version": d["version"]}, headers=h2)
    assert r.status_code == 404
