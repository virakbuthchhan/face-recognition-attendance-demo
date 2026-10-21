import json
import os
import random
import time
import httpx
from celery import Celery
from sqlalchemy import select
from backend.db import Delivery, Session, Subscription
from backend.security import signature, validate_destination

celery = Celery('attendance', broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
celery.conf.update(task_ignore_result=True, task_acks_late=True, worker_prefetch_multiplier=1,
                   beat_schedule={'outbox': {'task': 'backend.worker.dispatch', 'schedule': 5.0}})


@celery.task(name='backend.worker.dispatch')
def dispatch():
    with Session() as s:
        ids = list(s.scalars(select(Delivery.id).where(Delivery.state == 'pending', Delivery.next_attempt_at <= time.time()).limit(100)))
    for delivery_id in ids:
        deliver.delay(delivery_id)


@celery.task(name='backend.worker.deliver')
def deliver(delivery_id):
    with Session.begin() as s:
        d = s.scalar(select(Delivery).where(Delivery.id == delivery_id).with_for_update(skip_locked=True))
        if not d or d.state != 'pending' or d.next_attempt_at > time.time():
            return
        subscription = s.get(Subscription, d.subscription_id)
        if not subscription.active:
            d.state = 'cancelled'
            return
        d.attempts += 1
        d.last_status = None
        try:
            validate_destination(subscription.url)
            body = json.dumps(d.payload, separators=(',', ':'), sort_keys=True).encode()
            timestamp = str(int(time.time()))
            headers = {'Content-Type': 'application/json', 'X-Attendance-Delivery': d.id,
                       'X-Attendance-Timestamp': timestamp,
                       'X-Attendance-Signature': 'v1=' + signature(subscription.secret, timestamp, body)}
            with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
                # Streaming avoids loading unbounded receiver response bodies.
                with client.stream('POST', subscription.url, content=body, headers=headers) as response:
                    d.last_status = response.status_code
                    if not 200 <= response.status_code < 300:
                        raise ValueError(f'HTTP {response.status_code}')
            d.state = 'delivered'; d.last_error = None
        except (ValueError, OSError, httpx.HTTPError) as error:
            d.last_error = type(error).__name__ + ': delivery failed'
            d.state = 'failed' if d.attempts >= 6 else 'pending'
            d.next_attempt_at = time.time() + min(3600, 5 * 2 ** (d.attempts - 1)) + random.uniform(0, 3)
