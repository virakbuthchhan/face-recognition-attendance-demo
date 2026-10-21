import hashlib
import hmac
import importlib
import os
import time
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.db import Attendance, Base, Delivery, Employee, Kiosk, LoginSession, Subscription, User
from backend.security import digest, hash_password, signature
from shared.vision import MODEL_VERSION


@pytest.fixture
def system(monkeypatch):
    main = importlib.import_module('backend.main')
    worker = importlib.import_module('backend.worker')
    database_url = os.getenv('TEST_DATABASE_URL')
    engine = create_engine(database_url) if database_url else create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(engine, expire_on_commit=False)
    def db():
        with session() as s:
            yield s
    main.app.dependency_overrides[main.db] = db
    monkeypatch.setattr(worker, 'Session', session)
    with session.begin() as s:
        p = Employee(code='E01', name='Ada', embeddings=[[1.0, 0.0]])
        k = Kiosk(name='Lobby', token_hash=digest('device-token'))
        u = User(email='admin@example.com', password_hash=hash_password('test-password-123'))
        s.add_all([p, k, u]); s.flush()
        s.add(LoginSession(token_hash=digest('admin-token'), user_id=u.id, expires_at=time.time()+60))
        s.add(Subscription(name='Client', url='https://hooks.example.com/events', secret='hook-secret'))
        employee_id = p.id
    yield TestClient(main.app), session, employee_id, worker
    main.app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_auth_is_required(system):
    client, *_ = system
    assert client.get('/api/kiosk/faces').status_code in (401, 403)
    assert client.get('/api/admin/employees', headers={'Authorization': 'Bearer device-token'}).status_code == 401


def test_idempotency_and_outbox_are_atomic(system):
    client, session, employee_id, _ = system
    body = {'event_id': str(uuid.uuid4()), 'employee_id': employee_id, 'captured_at': time.time(),
            'confidence': 0.8, 'model_version': MODEL_VERSION}
    headers = {'Authorization': 'Bearer device-token'}
    first = client.post('/api/kiosk/scans', json=body, headers=headers)
    assert first.status_code == 200
    assert client.post('/api/kiosk/scans', json=body, headers=headers).json()['duplicate'] is True
    with session() as s:
        assert len(list(s.scalars(select(Attendance)))) == 1
        assert len(list(s.scalars(select(Delivery)))) == 1


def test_revocation_and_disabled_employee(system):
    client, session, employee_id, _ = system
    with session.begin() as s:
        s.get(Employee, employee_id).active = False
    headers = {'Authorization': 'Bearer device-token'}
    assert client.get('/api/kiosk/faces', headers=headers).json()['employees'] == []
    body = {'event_id': str(uuid.uuid4()), 'employee_id': employee_id, 'captured_at': time.time(), 'confidence': .8, 'model_version': MODEL_VERSION}
    assert client.post('/api/kiosk/scans', headers=headers, json=body).status_code == 422
    with session.begin() as s:
        s.scalar(select(Kiosk)).active = False
    assert client.get('/api/kiosk/faces', headers=headers).status_code == 401


def test_worker_retries_and_signs_exact_bytes(system, monkeypatch):
    _, session, _, worker = system
    monkeypatch.setattr(worker, 'validate_destination', lambda url: None)
    with session.begin() as s:
        subscription = s.scalar(select(Subscription))
        d = Delivery(subscription_id=subscription.id, payload={'type': 'webhook.test'})
        s.add(d); s.flush(); delivery_id = d.id
    calls = []
    class Response:
        status_code = 503
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, method, url, content, headers):
            calls.append((content, headers)); return Response()
    monkeypatch.setattr(worker.httpx, 'Client', Client)
    worker.deliver.run(delivery_id)
    with session() as s:
        d = s.get(Delivery, delivery_id)
        assert d.state == 'pending' and d.attempts == 1
        assert d.next_attempt_at > time.time()
    content, headers = calls[0]
    expected = hmac.new(b'hook-secret', headers['X-Attendance-Timestamp'].encode()+b'.'+content, hashlib.sha256).hexdigest()
    assert headers['X-Attendance-Signature'] == 'v1='+expected
    Response.status_code = 204
    with session.begin() as s:
        s.get(Delivery, delivery_id).next_attempt_at = 0
    worker.deliver.run(delivery_id)
    worker.deliver.run(delivery_id)
    with session() as s:
        d = s.get(Delivery, delivery_id)
        assert d.state == 'delivered' and d.attempts == 2
    assert len(calls) == 2


def test_hmac_detects_tampering():
    assert signature('secret', '123', b'{}') != signature('secret', '123', b'{ }')


def test_exhausted_delivery_fails(system, monkeypatch):
    _, session, _, worker = system
    def blocked(url):
        raise ValueError('Destination blocked')
    monkeypatch.setattr(worker, 'validate_destination', blocked)
    with session.begin() as s:
        subscription = s.scalar(select(Subscription))
        d = Delivery(subscription_id=subscription.id, payload={}, attempts=5)
        s.add(d); s.flush(); delivery_id = d.id
    worker.deliver.run(delivery_id)
    with session() as s:
        d = s.get(Delivery, delivery_id)
        assert d.state == 'failed' and d.attempts == 6


def test_kiosk_persistent_queue(tmp_path):
    from kiosk.storage import Store
    path = tmp_path / 'kiosk.db'
    store = Store(path)
    store.enqueue({'event_id': 'one', 'employee_id': 'ada'})
    store.connection.close()
    store = Store(path)
    assert store.pending()[0][0] == 'one'
    store.reject('one', 'HTTP 422')
    assert not store.pending() and store.counts() == (1, 1)


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='Requires isolated PostgreSQL test database')
def test_concurrent_duplicate_scans(system):
    from concurrent.futures import ThreadPoolExecutor
    client, session, employee_id, _ = system
    body = {'event_id': str(uuid.uuid4()), 'employee_id': employee_id, 'captured_at': time.time(),
            'confidence': .8, 'model_version': MODEL_VERSION}
    def send(_):
        return client.post('/api/kiosk/scans', headers={'Authorization': 'Bearer device-token'}, json=body)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(send, range(4)))
    assert all(r.status_code == 200 for r in responses)
    assert sum(not r.json()['duplicate'] for r in responses) == 1
    with session() as s:
        assert len(list(s.scalars(select(Attendance)))) == 1
        assert len(list(s.scalars(select(Delivery)))) == 1


def test_match_rejects_ambiguous_people():
    import numpy as np
    from shared.vision import match
    people = [{'id': 'one', 'embeddings': [[1., 0.]]}, {'id': 'two', 'embeddings': [[.99, .01]]}]
    assert match(np.array([1., 0.]), people) is None
    assert match(np.array([1., 0.]), people[:1])[1]['id'] == 'one'
    assert match(np.array([0., 1.]), people[:1]) is None
