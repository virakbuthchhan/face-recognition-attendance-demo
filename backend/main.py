import os
import secrets
import threading
import time
from pathlib import Path
from uuid import UUID
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from backend.db import Attendance, Delivery, Employee, Kiosk, LoginSession, Session, Subscription, User
from backend.security import digest, hash_password, validate_destination, verify_password
from shared.vision import MODEL_VERSION
from backend.integration import GUIDE, postman_collection

app = FastAPI(
    title='Attendance Control', version='1.0.0',
    description='Central attendance API. Admin routes accept an eight-hour bearer session from POST /api/login. '
                'Kiosk routes require a separately provisioned device token. All timestamps use Unix seconds in UTC.',
)
bearer = HTTPBearer()
vision_lock = threading.Lock()
vision = None


def db():
    with Session() as session:
        yield session


def admin(auth: HTTPAuthorizationCredentials = Depends(bearer), s: DBSession = Depends(db)):
    login = s.get(LoginSession, digest(auth.credentials))
    user = s.get(User, login.user_id) if login and login.expires_at > time.time() else None
    if not user or not user.active:
        raise HTTPException(401, 'Admin authentication required')
    return user


def device(auth: HTTPAuthorizationCredentials = Depends(bearer), s: DBSession = Depends(db)):
    kiosk = s.scalar(select(Kiosk).where(Kiosk.token_hash == digest(auth.credentials), Kiosk.active.is_(True)))
    if not kiosk:
        raise HTTPException(401, 'Device credential invalid or revoked')
    return kiosk


class Login(BaseModel):
    email: str
    password: str


class NewUser(Login):
    password: str = Field(min_length=12, max_length=256)


class Person(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)


class Named(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class Hook(Named):
    url: str = Field(max_length=2048)


class Scan(BaseModel):
    event_id: UUID
    employee_id: UUID
    captured_at: float = Field(gt=0)
    confidence: float = Field(ge=0.5, le=1.001)
    model_version: str


@app.get('/', include_in_schema=False)
def portal():
    return FileResponse(Path(__file__).parent / 'static/index.html')


@app.get('/assets/api-reference.js', include_in_schema=False)
def documentation_script():
    return FileResponse(Path(__file__).parent / 'static/api-reference.js', media_type='text/javascript')


@app.get('/api/admin/documentation/guide', dependencies=[Depends(admin)], include_in_schema=False)
def integration_guide():
    return FileResponse(GUIDE, media_type='text/markdown', filename='Attendance-Control-API.md')


@app.get('/api/admin/documentation/postman', dependencies=[Depends(admin)], include_in_schema=False)
def integration_collection():
    from fastapi.responses import JSONResponse
    return JSONResponse(postman_collection(app.openapi()),
                        headers={'Content-Disposition': 'attachment; filename="Attendance-Control.postman_collection.json"'})


@app.post('/api/login', tags=['Authentication'], summary='Create an eight-hour administrator session')
def login(body: Login, s: DBSession = Depends(db)):
    user = s.scalar(select(User).where(User.email == body.email, User.active.is_(True)))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, 'Invalid credentials')
    token = secrets.token_urlsafe(32)
    s.add(LoginSession(token_hash=digest(token), user_id=user.id, expires_at=time.time() + 8 * 3600))
    s.commit()
    return {'token': token}


@app.post('/api/logout', tags=['Authentication'], summary='Revoke the current administrator session')
def logout(auth: HTTPAuthorizationCredentials = Depends(bearer), _: User = Depends(admin), s: DBSession = Depends(db)):
    s.delete(s.get(LoginSession, digest(auth.credentials)))
    s.commit()
    return {'ok': True}


@app.get('/api/admin/users', dependencies=[Depends(admin)], tags=['Administrators'], summary='List administrators')
def users(s: DBSession = Depends(db)):
    return [{'id': u.id, 'email': u.email, 'active': u.active} for u in s.scalars(select(User))]


@app.post('/api/admin/users', dependencies=[Depends(admin)], tags=['Administrators'], summary='Create an administrator')
def create_user(body: NewUser, s: DBSession = Depends(db)):
    if s.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, 'Email already exists')
    u = User(email=body.email, password_hash=hash_password(body.password))
    s.add(u); s.commit()
    return {'id': u.id}


@app.patch('/api/admin/users/{user_id}', tags=['Administrators'], summary='Enable or disable an administrator')
def toggle_user(user_id: str, active: bool, current: User = Depends(admin), s: DBSession = Depends(db)):
    u = s.get(User, user_id)
    if not u:
        raise HTTPException(404)
    if u.id == current.id and not active:
        raise HTTPException(400, 'Cannot disable your own account')
    u.active = active; s.commit()
    return {'ok': True}


@app.get('/api/admin/employees', dependencies=[Depends(admin)], tags=['Employees'], summary='List employees and face counts')
def employees(s: DBSession = Depends(db)):
    return [{'id': p.id, 'code': p.code, 'name': p.name, 'active': p.active, 'faces': len(p.embeddings)}
            for p in s.scalars(select(Employee))]


@app.post('/api/admin/employees', dependencies=[Depends(admin)], tags=['Employees'], summary='Create an employee')
def create_person(body: Person, s: DBSession = Depends(db)):
    if s.scalar(select(Employee).where(Employee.code == body.code)):
        raise HTTPException(409, 'Employee code already exists')
    p = Employee(**body.model_dump()); s.add(p); s.commit()
    return {'id': p.id}


@app.patch('/api/admin/employees/{person_id}', dependencies=[Depends(admin)], tags=['Employees'], summary='Enable or disable an employee')
def toggle_person(person_id: str, active: bool, s: DBSession = Depends(db)):
    p = s.get(Employee, person_id)
    if not p:
        raise HTTPException(404)
    p.active = active; s.commit()
    return {'ok': True}


@app.post('/api/admin/employees/{person_id}/faces', dependencies=[Depends(admin)], tags=['Employees'], summary='Enroll one face image', description='Multipart file, maximum 8 MiB, exactly one face. Keeps the five newest embeddings and does not retain the image.')
def register_face(person_id: str, file: UploadFile = File(...), s: DBSession = Depends(db)):
    import cv2
    import numpy as np
    from shared.vision import Vision
    global vision
    p = s.scalar(select(Employee).where(Employee.id == person_id).with_for_update())
    if not p:
        raise HTTPException(404)
    data = file.file.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, 'Maximum image size is 8 MB')
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(400, 'Invalid image')
    if max(frame.shape[:2]) > 1920:
        frame = cv2.resize(frame, None, fx=1920/max(frame.shape[:2]), fy=1920/max(frame.shape[:2]))
    with vision_lock:
        vision = vision or Vision(os.getenv('MODEL_DIR', 'models'))
        faces = vision.detect(frame)
        if len(faces) != 1:
            raise HTTPException(400, 'Upload a clear image containing exactly one face')
        embedding = vision.embedding(frame, faces[0]).tolist()
    p.embeddings = (p.embeddings + [embedding])[-5:]
    s.commit()
    return {'faces': len(p.embeddings), 'model_version': MODEL_VERSION}


@app.post('/api/admin/kiosks', dependencies=[Depends(admin)], tags=['Kiosk management'], summary='Provision a kiosk and return its device token once')
def create_kiosk(body: Named, s: DBSession = Depends(db)):
    token = secrets.token_urlsafe(32)
    k = Kiosk(name=body.name, token_hash=digest(token)); s.add(k); s.commit()
    return {'id': k.id, 'token': token}


@app.get('/api/admin/kiosks', dependencies=[Depends(admin)], tags=['Kiosk management'], summary='List kiosks')
def kiosks(s: DBSession = Depends(db)):
    return [{'id': k.id, 'name': k.name, 'active': k.active} for k in s.scalars(select(Kiosk))]


@app.patch('/api/admin/kiosks/{kiosk_id}', dependencies=[Depends(admin)], tags=['Kiosk management'], summary='Enable or revoke a kiosk')
def toggle_kiosk(kiosk_id: str, active: bool, s: DBSession = Depends(db)):
    k = s.get(Kiosk, kiosk_id)
    if not k:
        raise HTTPException(404)
    k.active = active; s.commit()
    return {'ok': True}


@app.get('/api/kiosk/faces', tags=['Trusted kiosk API'], summary='Synchronize active employee embeddings', description='Requires a device token. Returns sensitive biometric embeddings for the trusted recognition kiosk.')
def sync(_: Kiosk = Depends(device), s: DBSession = Depends(db)):
    return {'model_version': MODEL_VERSION, 'employees': [
        {'id': p.id, 'name': p.name, 'embeddings': p.embeddings}
        for p in s.scalars(select(Employee).where(Employee.active.is_(True)))]}


@app.post('/api/kiosk/scans', tags=['Trusted kiosk API'], summary='Record an idempotent kiosk scan', description='Requires a device token. Reuse the event UUID for retries of the same scan. The API trusts the kiosk match.')
def scan(body: Scan, kiosk: Kiosk = Depends(device), s: DBSession = Depends(db)):
    # Serializes same-device requests; PostgreSQL is required for concurrent production use.
    s.scalar(select(Kiosk).where(Kiosk.id == kiosk.id).with_for_update())
    existing = s.scalar(select(Attendance).where(Attendance.kiosk_id == kiosk.id, Attendance.event_id == str(body.event_id)))
    if existing:
        return {'id': existing.id, 'duplicate': True}
    if body.model_version != MODEL_VERSION or body.captured_at > time.time() + 300:
        raise HTTPException(422, 'Model version or capture timestamp invalid')
    p = s.get(Employee, str(body.employee_id))
    if not p or not p.active:
        raise HTTPException(422, 'Employee inactive or missing')
    log = Attendance(event_id=str(body.event_id), employee_id=p.id, kiosk_id=kiosk.id,
                     captured_at=body.captured_at, confidence=body.confidence)
    s.add(log); s.flush()
    payload = {'id': log.id, 'type': 'attendance.recorded', 'employee': {'id': p.id, 'code': p.code, 'name': p.name},
               'kiosk_id': kiosk.id, 'captured_at': log.captured_at, 'received_at': log.received_at,
               'confidence': log.confidence}
    for subscription in s.scalars(select(Subscription).where(Subscription.active.is_(True))):
        s.add(Delivery(subscription_id=subscription.id, payload=payload))
    s.commit()
    return {'id': log.id, 'duplicate': False}


@app.get('/api/admin/attendance', dependencies=[Depends(admin)], tags=['Attendance'], summary='Read the latest 200 attendance records', description='Newest received_at first. No filters or pagination. Timestamps are Unix seconds in UTC. Use webhooks for continuous capture.')
def attendance(s: DBSession = Depends(db)):
    return [{'id': a.id, 'employee_id': a.employee_id, 'kiosk_id': a.kiosk_id, 'captured_at': a.captured_at,
             'received_at': a.received_at, 'confidence': a.confidence}
            for a in s.scalars(select(Attendance).order_by(Attendance.received_at.desc()).limit(200))]


@app.get('/api/admin/subscriptions', dependencies=[Depends(admin)], tags=['Webhooks'], summary='List webhook subscribers')
def subscriptions(s: DBSession = Depends(db)):
    return [{'id': h.id, 'name': h.name, 'url': h.url, 'active': h.active} for h in s.scalars(select(Subscription))]


@app.post('/api/admin/subscriptions', dependencies=[Depends(admin)], tags=['Webhooks'], summary='Create a subscriber and return its signing secret once')
def create_hook(body: Hook, s: DBSession = Depends(db)):
    try:
        validate_destination(body.url)
    except (ValueError, OSError) as error:
        raise HTTPException(400, str(error))
    h = Subscription(**body.model_dump(), secret=secrets.token_urlsafe(32)); s.add(h); s.commit()
    return {'id': h.id, 'secret': h.secret}


@app.patch('/api/admin/subscriptions/{hook_id}', dependencies=[Depends(admin)], tags=['Webhooks'], summary='Pause or enable a subscriber')
def toggle_hook(hook_id: str, active: bool, s: DBSession = Depends(db)):
    h = s.get(Subscription, hook_id)
    if not h:
        raise HTTPException(404)
    h.active = active; s.commit()
    return {'ok': True}


@app.post('/api/admin/subscriptions/{hook_id}/test', dependencies=[Depends(admin)], tags=['Webhooks'], summary='Queue a signed test delivery')
def test_hook(hook_id: str, s: DBSession = Depends(db)):
    h = s.get(Subscription, hook_id)
    if not h or not h.active:
        raise HTTPException(404)
    d = Delivery(subscription_id=h.id, payload={'type': 'webhook.test', 'created_at': time.time()})
    s.add(d); s.commit()
    return {'delivery_id': d.id}


@app.get('/api/admin/deliveries', dependencies=[Depends(admin)], tags=['Webhooks'], summary='Read the latest 200 delivery states')
def deliveries(s: DBSession = Depends(db)):
    return [{'id': d.id, 'subscription_id': d.subscription_id, 'state': d.state, 'attempts': d.attempts,
             'last_status': d.last_status, 'last_error': d.last_error, 'next_attempt_at': d.next_attempt_at}
            for d in s.scalars(select(Delivery).order_by(Delivery.next_attempt_at.desc()).limit(200))]
