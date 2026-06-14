import os, sys, importlib
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PLACEHOLDER = "CONTACT_EMAIL (운영자 이메일 기재 예정)"


def _reload_server():
    import server
    return importlib.reload(server)


def test_privacy_public_200_both_paths():
    os.environ.pop("CONTACT_EMAIL", None)
    server = _reload_server()
    c = server.app.test_client()  # 비로그인
    for path in ("/privacy", "/privacy.html"):
        r = c.get(path)
        assert r.status_code == 200, path


def test_contact_email_substituted_when_set():
    os.environ["CONTACT_EMAIL"] = "owner@daymate.app"
    server = _reload_server()
    body = server.app.test_client().get("/privacy").get_data(as_text=True)
    assert "owner@daymate.app" in body
    assert PLACEHOLDER not in body


def test_no_raw_placeholder_when_unset():
    # rep #31 footgun: 미설정 시 디버그 플레이스홀더 원문이 새어나오면 심사 반려 위험
    os.environ.pop("CONTACT_EMAIL", None)
    server = _reload_server()
    body = server.app.test_client().get("/privacy").get_data(as_text=True)
    assert PLACEHOLDER not in body
    assert "계정 삭제" in body  # 기능적 폴백 문구로 강등됨
