# Attendance Control — Integration API

API version: **1.0.0**. This guide describes the implemented demo API. All successful operations return **200 OK**, including creates. JSON field names are case-sensitive. UUIDs, employee names, tokens and timestamps in examples are illustrative.

## 1. Connect to the server

Use your deployment's origin as `BASE_URL`, for example `https://attendance.example.com`. On the current local demo the origin is `http://127.0.0.1:8017`; localhost is reachable only from that computer. Other systems require a reachable HTTPS deployment, or an explicitly configured private development environment. The default setup instructions use port 8000; use the actual port your server runs on.

```sh
export BASE_URL='https://attendance.example.com'
```

Live resources on that origin:

- `/docs`: interactive Swagger reference, including **Authorize** and **Try it out**. Executing a write changes real data.
- `/openapi.json`: machine-readable OpenAPI schema, importable into API tools and client generators.
- Admin portal → **API Documentation**: examples, endpoint fields, and authenticated downloads of this guide and the Postman collection.

Use server-to-server calls for third-party integrations. Cross-origin browser access (CORS) is not configured. Existing backend routes use `/api/admin/...`; no separate `/api/v1` prefix or public write API exists.

## 2. Authentication and access

Ask a workspace administrator to authorize an integration account. Accounts created under **Administrators** have full administrator privileges in this version, including employee, kiosk, webhook and administrator management. There are no scoped service API keys or read-only roles. Store account credentials and tokens in the integration backend's secret storage; do not put them in public frontend code or URLs.

### Sign in

`POST /api/login` requires no bearer token:

```sh
curl --request POST "$BASE_URL/api/login" \
  --header 'Content-Type: application/json' \
  --data '{"email":"integration@example.com","password":"YOUR_PASSWORD"}'
```

Response:

```json
{"token":"YOUR_ADMIN_TOKEN"}
```

The session expires eight hours after login. The response does not include an expiration field. There is no refresh endpoint: obtain a new session when the previous one expires. Avoid signing in on every request. For following shell examples, set `ADMIN_TOKEN` to the returned token securely:

```sh
export ADMIN_TOKEN='YOUR_ADMIN_TOKEN'
```

Send this header on all `/api/admin/...` requests and on logout:

```http
Authorization: Bearer YOUR_ADMIN_TOKEN
```

### Sign out

```sh
curl --request POST "$BASE_URL/api/logout" \
  --header "Authorization: Bearer $ADMIN_TOKEN"
```

Response: `{"ok":true}`. This revokes only the token sent in this request. Disabling an administrator also prevents their existing sessions from being used. Handle both 401 and 403 for authentication failures; missing-header behavior can differ with framework versions.

### Device authentication

Kiosk endpoints require a separately provisioned **device token**, returned when an administrator creates a kiosk. Device and administrator tokens are not interchangeable. Device tokens do not have an automatic expiration in this demo; disable the kiosk to revoke access. A general HR integration should normally use employee/attendance endpoints and webhooks rather than downloading biometric face embeddings or submitting kiosk matches.

## 3. Employees

### Create an employee

`POST /api/admin/employees`

| JSON field | Type | Rules |
| --- | --- | --- |
| `code` | string | Required, 1–80 characters, unique; use your external employee ID |
| `name` | string | Required, 1–160 characters |

```sh
curl --request POST "$BASE_URL/api/admin/employees" \
  --header "Authorization: Bearer $ADMIN_TOKEN" \
  --header 'Content-Type: application/json' \
  --data '{"code":"EMP-001","name":"Alex Morgan"}'
```

Response:

```json
{"id":"6c824b0a-984b-45a1-9c63-9795987fbbe0"}
```

Save this UUID as your mapping to the attendance system. The employee is active by default and initially has no face embeddings. Reusing a code returns `409` with `{"detail":"Employee code already exists"}`. Employee creation has no idempotency-key header; after an ambiguous timeout, list employees and find the existing code before retrying.

### List employees

```sh
curl "$BASE_URL/api/admin/employees" \
  --header "Authorization: Bearer $ADMIN_TOKEN"
```

Response is a JSON array, including inactive employees:

```json
[
  {
    "id":"6c824b0a-984b-45a1-9c63-9795987fbbe0",
    "code":"EMP-001",
    "name":"Alex Morgan",
    "active":true,
    "faces":2
  }
]
```

`faces` is the number of retained embeddings, not a photo URL. This administrator endpoint does not expose embeddings. There is no single-employee GET, search filter or pagination; select from the returned array by code/UUID. Name/code editing and hard deletion are not currently implemented.

### Disable or enable an employee

`PATCH /api/admin/employees/{person_id}?active=false`

```sh
export EMPLOYEE_ID='6c824b0a-984b-45a1-9c63-9795987fbbe0'
curl --request PATCH "$BASE_URL/api/admin/employees/$EMPLOYEE_ID?active=false" \
  --header "Authorization: Bearer $ADMIN_TOKEN"
```

Response: `{"ok":true}`. Use `active=true` to re-enable. `active` is a required **query parameter**, not a JSON field. Missing employees return 404. Disabling does not delete historical attendance or stored embeddings. Kiosks remove inactive people on their next successful sync (normally every 60 seconds); queued scans for an inactive employee are rejected centrally.

### Register a face

`POST /api/admin/employees/{person_id}/faces`

```sh
curl --request POST "$BASE_URL/api/admin/employees/$EMPLOYEE_ID/faces" \
  --header "Authorization: Bearer $ADMIN_TOKEN" \
  --form 'file=@/absolute/path/face.jpg'
```

The body is `multipart/form-data` with field **file**. Let your HTTP client set the multipart Content-Type and boundary. Send one clear face in a supported image (JPG/PNG recommended), maximum **8 MiB / 8,388,608 bytes**. Zero or multiple detected faces returns 400. Over-limit files return 413; a proxy may enforce additional request limits.

Response:

```json
{"faces":1,"model_version":"sface-2021dec-yunet-2023mar-v1"}
```

Server stores normalized embeddings and keeps the five newest per employee; it does not retain the original uploaded image. Register several clear angles by sending separate photos. Repeating an upload adds another embedding and can replace the oldest; this operation is not idempotent. Kiosks receive changes on their next successful sync.

The admin portal supports both **Use camera** and **Upload photo**. An external integration can send the resulting image using the same multipart endpoint.

## 4. Attendance records

### Retrieve recent records

```sh
curl "$BASE_URL/api/admin/attendance" \
  --header "Authorization: Bearer $ADMIN_TOKEN"
```

Response:

```json
[
  {
    "id":"92298061-4936-44c0-a602-a547294eed23",
    "employee_id":"6c824b0a-984b-45a1-9c63-9795987fbbe0",
    "kiosk_id":"d2a55532-0fd9-45b9-9518-cff5764b422d",
    "captured_at":1792560000.0,
    "received_at":1792560002.0,
    "confidence":0.73
  }
]
```

| Field | Meaning |
| --- | --- |
| `id` | Central attendance UUID; use as the unique event key in your system |
| `employee_id` | Employee UUID; join against the employee directory for name/code |
| `kiosk_id` | Device UUID; join against the kiosk list for its name |
| `captured_at` | Unix seconds in UTC when the kiosk recorded the face match |
| `received_at` | Unix seconds in UTC when the central server received it |
| `confidence` | Cosine similarity match score, not a probability |

**Limit:** this endpoint returns only the latest **200 records**, ordered by `received_at` descending. No filters, pagination, `since` parameter, cursor, complete-history export or in/out classification is implemented. Results are raw scans, not calculated work hours. Offline kiosk events can arrive later with earlier `captured_at` values.

Deduplicate by attendance `id`. Polling this endpoint can miss events if more than 200 arrive between polls; use signed webhooks for continuous capture. Historical recovery beyond this window requires a separate export/backfill capability.

## 5. Real-time attendance webhooks

### Create a subscriber

```sh
curl --request POST "$BASE_URL/api/admin/subscriptions" \
  --header "Authorization: Bearer $ADMIN_TOKEN" \
  --header 'Content-Type: application/json' \
  --data '{"name":"HR system","url":"https://hooks.example.com/attendance"}'
```

`name`: required 1–160 characters. `url`: at most 2048 characters, must be HTTPS on port 443, have an operator-allowlisted hostname (`WEBHOOK_ALLOWED_HOSTS`), and resolve to public addresses. Redirects are not followed. Operator-controlled egress rules are also required for hardened production deployment.

Response:

```json
{"id":"5207c64f-fb85-461d-a75d-f5d14449787c","secret":"ONE_TIME_SIGNING_SECRET"}
```

Save the secret in your receiver's secret storage. It is returned only at creation; GET does not reveal it. There is no secret-rotation endpoint in this demo. The subscription is active by default. All active subscriptions receive future `attendance.recorded` events; there are no employee/event-type filters or retrospective replay. Creating a subscription does not send historical events.

List subscribers: `GET /api/admin/subscriptions`, returning `[{"id":"...","name":"HR system","url":"https://hooks.example.com/attendance","active":true}]`.

Pause/enable: `PATCH /api/admin/subscriptions/{hook_id}?active=false` (or `true`), returning `{"ok":true}`. Pending deliveries cancel when processed while a subscription is disabled; enabling does not replay cancelled deliveries. A previously cancelled delivery stays cancelled.

### Test and monitor

```sh
export SUBSCRIPTION_ID='5207c64f-fb85-461d-a75d-f5d14449787c'
curl --request POST "$BASE_URL/api/admin/subscriptions/$SUBSCRIPTION_ID/test" \
  --header "Authorization: Bearer $ADMIN_TOKEN"
```

Response: `{"delivery_id":"DELIVERY_UUID"}`. A test for a missing/inactive subscription returns 404. The payload is `{"type":"webhook.test","created_at":1792560000.0}`. Queued means saved for delivery, not successfully delivered.

`GET /api/admin/deliveries` returns the latest 200 rows ordered by `next_attempt_at` descending:

```json
[
  {
    "id":"DELIVERY_UUID",
    "subscription_id":"5207c64f-fb85-461d-a75d-f5d14449787c",
    "state":"pending",
    "attempts":1,
    "last_status":503,
    "last_error":"ValueError: delivery failed",
    "next_attempt_at":1792560010.0
  }
]
```

States: `pending`, `delivered`, `failed`, `cancelled`. Status/error fields may be null. `failed` means six total attempts have been exhausted. No manual replay endpoint is implemented.

### Attendance event payload

```json
{
  "id":"92298061-4936-44c0-a602-a547294eed23",
  "type":"attendance.recorded",
  "employee":{
    "id":"6c824b0a-984b-45a1-9c63-9795987fbbe0",
    "code":"EMP-001",
    "name":"Alex Morgan"
  },
  "kiosk_id":"d2a55532-0fd9-45b9-9518-cff5764b422d",
  "captured_at":1792560000.0,
  "received_at":1792560002.0,
  "confidence":0.73
}
```

Headers:

```http
Content-Type: application/json
X-Attendance-Delivery: DELIVERY_UUID
X-Attendance-Timestamp: 1792560005
X-Attendance-Signature: v1=HEX_HMAC_SHA256
```

Compute HMAC-SHA256 using the subscription secret over the exact bytes:

```text
timestamp_header + "." + raw_request_body
```

Verify **raw bytes**, before parsing/re-serializing JSON. Example receiver helper:

```python
import hashlib
import hmac
import time

def valid_webhook(secret, timestamp_header, signature_header, raw_body):
    try:
        timestamp = int(timestamp_header)
    except (TypeError, ValueError):
        return False
    if abs(time.time() - timestamp) > 300:
        return False
    message = timestamp_header.encode() + b'.' + raw_body
    expected = 'v1=' + hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header or '')
```

Verify the signature, reject timestamps outside a five-minute tolerance, and transactionally record the delivery UUID with your local processing. Return 2xx only after durable acceptance. Also deduplicate attendance `id` across different subscriptions delivering to the same downstream system.

Delivery is **at least once**, so duplicates are possible. Retries keep the same delivery UUID but use a fresh signing timestamp. Six total attempts use delays of `min(3600, 5 × 2^(attempt−1))` seconds plus 0–3 seconds jitter after failures. Beat polls due records every five seconds; actual arrival depends on queue/network availability. All non-2xx results, including redirects, count as failures.

The central API persists attendance and delivery records atomically. Redis, Celery worker and Celery Beat must run for dispatch; saving an attendance log alone does not run the dispatcher.

## 6. Kiosks and administrator management

### Kiosk management (administrator token)

| Method and path | Request | Response |
| --- | --- | --- |
| `GET /api/admin/kiosks` | None | `[{"id":"...","name":"Main entrance","active":true}]` |
| `POST /api/admin/kiosks` | JSON `{"name":"Main entrance"}`; 1–160 characters | `{"id":"...","token":"ONE_TIME_DEVICE_TOKEN"}` |
| `PATCH /api/admin/kiosks/{kiosk_id}?active=false` | Required query `active`; use true to re-enable | `{"ok":true}` |

Device tokens are shown once. Name edits and automatic token rotation are not implemented. Disabling the kiosk rejects further API calls; an offline kiosk cannot learn about revocation until it contacts the server.

### Trusted kiosk API (device token)

`GET /api/kiosk/faces` returns:

```json
{
  "model_version":"sface-2021dec-yunet-2023mar-v1",
  "employees":[{"id":"EMPLOYEE_UUID","name":"Alex Morgan","embeddings":[[0.1,0.2]]}]
}
```

The short embedding above illustrates the JSON structure only. Actual SFace embeddings have 128 normalized components. Treat them as sensitive biometric data. This endpoint returns all active employees, including employees with an empty embeddings array.

`POST /api/kiosk/scans` accepts:

```json
{
  "event_id":"4d406b5f-566d-41dc-b115-c2835daa052f",
  "employee_id":"6c824b0a-984b-45a1-9c63-9795987fbbe0",
  "captured_at":1792560000.0,
  "confidence":0.73,
  "model_version":"sface-2021dec-yunet-2023mar-v1"
}
```

Both IDs must be UUIDs. `captured_at` must be positive and no more than 300 seconds in the future; older offline events are accepted. `confidence` must be between 0.5 and 1.001 inclusive (floating-point tolerance). The model version must match the server, and the employee must exist and be active.

First response: `{"id":"ATTENDANCE_UUID","duplicate":false}`. Retrying the same `(kiosk, event_id)` returns the same ID with `duplicate:true`; retain the UUID and payload until acknowledged. The server does not revalidate a duplicate payload's employee/model fields after finding the existing event. New scans need new event UUIDs. This endpoint trusts authenticated kiosk recognition; submitting an employee UUID is not independent proof of a face match.

### Administrator accounts (administrator token)

| Method and path | Request | Response |
| --- | --- | --- |
| `GET /api/admin/users` | None | `[{"id":"...","email":"...","active":true}]` |
| `POST /api/admin/users` | JSON `email`, `password`; password 12–256 characters | `{"id":"USER_UUID"}` |
| `PATCH /api/admin/users/{user_id}?active=false` | Required query `active` | `{"ok":true}` |

Duplicate email returns 409; disabling your own account returns 400. Password change/reset, scoped permissions and MFA are not implemented. All admin users have equal privileges.

## 7. Errors, retries and current limits

Standard application errors have the shape:

```json
{"detail":"Employee code already exists"}
```

Validation errors may instead contain an array:

```json
{"detail":[{"loc":["body","code"],"msg":"Field required","type":"missing"}]}
```

| Status | Typical cause | Integration behavior |
| --- | --- | --- |
| 400 | Invalid/ambiguous face image, rejected webhook destination, prohibited action | Correct request; do not retry unchanged |
| 401 / 403 | Missing, expired, inactive or wrong-type credentials | Re-authenticate or check the appropriate token |
| 404 | Resource missing, or webhook test for an inactive subscriber | Verify UUID and state |
| 409 | Employee code or administrator email already exists | Reconcile with the existing record |
| 413 | Face image exceeds 8 MiB | Resize/re-encode and retry |
| 422 | Missing fields, invalid UUID/limits, inactive employee or model mismatch in a new scan | Inspect `detail` and correct fields/state |
| 429 | Optional proxy rate limit, if configured by the operator | Honor Retry-After if present; back off |
| 5xx / timeout | Server/network failure | Back off; reconcile non-idempotent writes before retrying |

Only kiosk scan submission provides event-ID idempotency. No general idempotency header, bulk operations, pagination, attendance filters or full-history export is implemented. The API does not define a built-in rate quota; operators should apply suitable proxy limits. The demo's image request limit does not replace a reverse-proxy body-size limit.

## 8. Python integration example

Install `httpx` in your integration environment and set these variables in your secret manager or shell: `ATTENDANCE_BASE_URL`, `ATTENDANCE_ADMIN_EMAIL`, `ATTENDANCE_ADMIN_PASSWORD`.

```python
import os
import httpx

with httpx.Client(
    base_url=os.environ['ATTENDANCE_BASE_URL'].rstrip('/'),
    timeout=20,
) as client:
    response = client.post('/api/login', json={
        'email': os.environ['ATTENDANCE_ADMIN_EMAIL'],
        'password': os.environ['ATTENDANCE_ADMIN_PASSWORD'],
    })
    response.raise_for_status()
    client.headers['Authorization'] = 'Bearer ' + response.json()['token']
    try:
        # Reconcile by unique external code before attempting a new create.
        response = client.get('/api/admin/employees')
        response.raise_for_status()
        employee = next((p for p in response.json() if p['code'] == 'EMP-001'), None)
        if employee is None:
            response = client.post('/api/admin/employees', json={
                'code': 'EMP-001', 'name': 'Alex Morgan',
            })
            response.raise_for_status()
            employee_id = response.json()['id']
        else:
            employee_id = employee['id']

        # Optional: enroll a photo, with permission to process that employee's image.
        # with open('/absolute/path/face.jpg', 'rb') as photo:
        #     response = client.post(
        #         f'/api/admin/employees/{employee_id}/faces',
        #         files={'file': ('face.jpg', photo, 'image/jpeg')},
        #     )
        #     response.raise_for_status()

        response = client.get('/api/admin/attendance')
        response.raise_for_status()
        recent_records = response.json()  # Latest 200 only, not a complete history.
        for record in recent_records:
            print(record['id'], record['employee_id'], record['captured_at'])
    finally:
        client.post('/api/logout').raise_for_status()
```

Long-running integrations should cache a valid session for up to eight hours and handle expiry, instead of running this short-lived login/logout pattern per event. Concurrent creators must reconcile 409 conflicts. Do not blindly retry ambiguous face uploads, administrator creation, provisioning or subscription creation.

## 9. Postman

1. Sign in to the admin portal → **API Documentation** → **Postman collection**.
2. Import the downloaded JSON into Postman.
3. Set `base_url`, `admin_email` and `admin_password` in your local collection variables. Keep credentials out of shared exports.
4. Send **Authentication → POST /api/login**. The post-response script saves `admin_token` for subsequent admin requests.
5. Send **Employees → POST /api/admin/employees** when you intend to create a real record. The script saves `employee_id`.
6. For face upload, select a local image in the multipart `file` field. Set other resource UUIDs as needed.
7. Kiosk API requests require `device_token`; scan requests initialize `event_id` and `captured_at` if empty. Keep the event ID unchanged to retry the same event; clear both values before sending a genuinely new scan.

The generated collection includes actual mutating operations. It is not an automatic test run and does not contain your live credentials, session tokens, employee data or webhook secrets. If you prefer another tool, import `/openapi.json`.
