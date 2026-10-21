import argparse
import getpass
from sqlalchemy import select
from backend.db import Base, engine, Session, User
from backend.security import hash_password

parser = argparse.ArgumentParser()
parser.add_argument('command', choices=['init', 'create-admin'])
args = parser.parse_args()
if args.command == 'init':
    Base.metadata.create_all(engine)
else:
    email = input('Admin email: ').strip()
    password = getpass.getpass('Password (12+ characters): ')
    if len(password) < 12:
        raise SystemExit('Password too short')
    with Session.begin() as s:
        if s.scalar(select(User).where(User.email == email)):
            raise SystemExit('User already exists')
        s.add(User(email=email, password_hash=hash_password(password)))
