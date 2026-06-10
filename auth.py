"""회원가입·로그인. werkzeug 비번 해시."""
from werkzeug.security import generate_password_hash, check_password_hash
import db


class AuthError(Exception):
    pass


def register(email, password):
    email = (email or "").strip().lower()
    if "@" not in email:
        raise AuthError("이메일 형식 오류")
    if len(password or "") < 6:
        raise AuthError("비밀번호는 6자 이상")
    with db.SessionLocal() as s:
        if s.query(db.User).filter_by(email=email).one_or_none():
            raise AuthError("이미 가입된 이메일")
        u = db.User(email=email, pw_hash=generate_password_hash(password))
        s.add(u); s.commit()
        return u.id


def authenticate(email, password):
    email = (email or "").strip().lower()
    with db.SessionLocal() as s:
        u = s.query(db.User).filter_by(email=email).one_or_none()
        if u and check_password_hash(u.pw_hash, password or ""):
            return u.id
    return None
