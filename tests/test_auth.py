import os, sys
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import db, auth  # noqa

def setup_module(m):
    db.init_db()

def test_register_then_login():
    uid = auth.register("a@x.com", "pw12345")
    assert isinstance(uid, int)
    assert auth.authenticate("a@x.com", "pw12345") == uid
    assert auth.authenticate("a@x.com", "wrong") is None

def test_duplicate_email_rejected():
    auth.register("dup@x.com", "pw12345")
    try:
        auth.register("dup@x.com", "pw12345")
        assert False, "duplicate should raise"
    except auth.AuthError:
        pass

def test_short_password_rejected():
    try:
        auth.register("b@x.com", "123")
        assert False
    except auth.AuthError:
        pass
