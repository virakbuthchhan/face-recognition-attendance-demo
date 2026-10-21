"""Portable API documentation downloads. No live credentials or employee data."""
from pathlib import Path

GUIDE = Path(__file__).resolve().parents[1] / 'docs/API.md'

EXAMPLES = {
    '/api/login': {'email': '{{admin_email}}', 'password': '{{admin_password}}'},
    '/api/admin/users': {'email': 'integration@example.com', 'password': '{{new_admin_password}}'},
    '/api/admin/employees': {'code': 'EMP-001', 'name': 'Alex Morgan'},
    '/api/admin/kiosks': {'name': 'Main entrance'},
    '/api/admin/subscriptions': {'name': 'HR system', 'url': 'https://hooks.example.com/attendance'},
    '/api/kiosk/scans': {'event_id': '{{event_id}}', 'employee_id': '{{employee_id}}',
                         'captured_at': '{{captured_at}}', 'confidence': 0.8,
                         'model_version': 'sface-2021dec-yunet-2023mar-v1'},
}


def postman_collection(schema):
    import json
    groups = {}
    aliases = {'person_id': 'employee_id', 'user_id': 'user_id', 'kiosk_id': 'kiosk_id', 'hook_id': 'subscription_id'}
    for path, operations in schema['paths'].items():
        if not path.startswith('/api/') or path.startswith('/api/admin/documentation'):
            continue
        group = ('Authentication' if path in ('/api/login', '/api/logout') else
                 'Kiosk API' if path.startswith('/api/kiosk/') else path.split('/')[3].capitalize())
        for method, operation in operations.items():
            if method not in ('get', 'post', 'patch', 'delete', 'put'):
                continue
            url = '{{base_url}}' + path
            for name, alias in aliases.items():
                url = url.replace('{' + name + '}', '{{' + alias + '}}')
            if method == 'patch':
                url += '?active={{active}}'
            request = {'method': method.upper(), 'url': url, 'header': [],
                       'description': operation.get('description', operation.get('summary', ''))}
            if path == '/api/login':
                request['auth'] = {'type': 'noauth'}
            elif path.startswith('/api/kiosk/'):
                request['auth'] = {'type': 'bearer', 'bearer': [{'key': 'token', 'value': '{{device_token}}', 'type': 'string'}]}
            if method == 'post' and path in EXAMPLES:
                request['header'] = [{'key': 'Content-Type', 'value': 'application/json'}]
                raw = json.dumps(EXAMPLES[path], indent=2)
                if path == '/api/kiosk/scans':
                    raw = raw.replace('"{{captured_at}}"', '{{captured_at}}')
                request['body'] = {'mode': 'raw', 'raw': raw, 'options': {'raw': {'language': 'json'}}}
            if path.endswith('/faces') and method == 'post':
                request['body'] = {'mode': 'formdata', 'formdata': [{'key': 'file', 'type': 'file', 'src': [],
                                                                                'description': 'One face image, maximum 8 MiB'}]}
            item = {'name': f'{method.upper()} {path}', 'request': request}
            variable = 'admin_token' if path == '/api/login' else 'employee_id' if path == '/api/admin/employees' and method == 'post' else None
            if variable:
                field = 'token' if variable == 'admin_token' else 'id'
                item['event'] = [{'listen': 'test', 'script': {'type': 'text/javascript', 'exec': [
                    f'if (pm.response.code === 200) pm.collectionVariables.set("{variable}", pm.response.json().{field});']}}]
            if path == '/api/kiosk/scans':
                item['event'] = [{'listen': 'prerequest', 'script': {'type': 'text/javascript', 'exec': [
                    'if (!pm.collectionVariables.get("event_id")) pm.collectionVariables.set("event_id", pm.variables.replaceIn("{{$guid}}"));',
                    'if (!pm.collectionVariables.get("captured_at")) pm.collectionVariables.set("captured_at", Math.floor(Date.now() / 1000));',
                ]}}]
            groups.setdefault(group, []).append(item)
    return {
        'info': {'name': 'Attendance Control API', 'schema': 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
                 'description': 'Set base_url and login variables. Send Login first. All admin requests use an eight-hour administrator session. Kiosk requests require a separate device token. API writes change real data.'},
        'auth': {'type': 'bearer', 'bearer': [{'key': 'token', 'value': '{{admin_token}}', 'type': 'string'}]},
        'variable': [{'key': key, 'value': value, 'type': 'string'} for key, value in {
            'base_url': 'https://attendance.example.com', 'admin_email': '', 'admin_password': '', 'admin_token': '',
            'new_admin_password': '', 'employee_id': '', 'user_id': '', 'kiosk_id': '', 'subscription_id': '',
            'device_token': '', 'active': 'true', 'event_id': '', 'captured_at': ''}.items()],
        'item': [{'name': name, 'item': items} for name, items in groups.items()],
    }
