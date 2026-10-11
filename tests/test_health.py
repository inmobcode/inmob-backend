def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}


def test_stub_blueprints_respond_501(client):
    for module in ("payments", "documents"):
        res = client.get(f"/api/{module}/")
        assert res.status_code == 501
