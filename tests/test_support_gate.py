import os, sys
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import db, server  # noqa

LINK = "https://buy.stripe.com/test_link"


def setup_module(m):
    db.init_db()


def _client(email):
    c = server.app.test_client()
    c.post("/api/register", json={"email": email, "password": "pw123456"})
    return c


def _boot_support_url(c):
    return c.get("/api/bootstrap").get_json()["supportUrl"]


def test_support_url_shown_on_web_when_set():
    os.environ.pop("STORE_BUILD", None)
    os.environ["SUPPORT_URL"] = LINK
    c = _client("sg1@c.com")
    assert _boot_support_url(c) == LINK


def test_support_url_hidden_in_store_build():
    # rep #40: Play TWA 등 스토어 빌드에서 외부 Stripe 노출 = Play Billing 반려 위험.
    # STORE_BUILD=1이면 SUPPORT_URL이 설정돼 있어도 외부결제 경로를 강제 숨김.
    os.environ["SUPPORT_URL"] = LINK
    os.environ["STORE_BUILD"] = "1"
    c = _client("sg2@c.com")
    assert _boot_support_url(c) == ""
    os.environ.pop("STORE_BUILD", None)


def test_support_url_empty_when_unset():
    os.environ.pop("STORE_BUILD", None)
    os.environ.pop("SUPPORT_URL", None)
    c = _client("sg3@c.com")
    assert _boot_support_url(c) == ""
