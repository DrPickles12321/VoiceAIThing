from fastapi.testclient import TestClient

from web_app import create_app


def test_browser_assets_and_six_question_api_flow():
    with TestClient(create_app()) as client:
        assert client.get('/').status_code == 200
        assert client.get('/static/app.js').status_code == 200
        assert client.get('/.env').status_code == 404
        turn = client.post('/api/sessions', json={'mode': 'offline'}).json()
        path = f"/api/sessions/{turn['session_id']}/turns"
        for index in range(6):
            pending = client.post(path, json={'transcript': 'Mild'}).json()
            assert pending['state'] == 'confirming'
            assert pending['answered_count'] == index
            turn = client.post(path, json={'transcript': 'Yes'}).json()
        assert turn['state'] == 'complete'
        assert len(turn['responses']) == 6
        assert client.post(path, json={'transcript': 'Yes'}).status_code == 409


def test_api_input_and_session_errors():
    with TestClient(create_app()) as client:
        assert client.post('/api/sessions', json={'mode': 'invalid'}).status_code == 422
        assert client.post('/api/sessions/missing/turns', json={'transcript': 'mild'}).status_code == 404
        sid = client.post('/api/sessions', json={}).json()['session_id']
        path = f'/api/sessions/{sid}/turns'
        for text in ['', '   ', 'a' * 8001]:
            assert client.post(path, json={'transcript': text}).status_code == 422
        assert client.post(path, json={'transcript': 'stop'}).json()['state'] == 'stopped'


def test_missing_key_is_explicit_and_not_exposed(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', '')
    with TestClient(create_app()) as client:
        assert client.get('/api/config').json() == {'openai_available': False, 'default_mode': 'offline'}
        assert client.post('/api/sessions', json={'mode': 'openai'}).status_code == 503


def test_cross_origin_requests_blocked():
    with TestClient(create_app()) as client:
        assert client.post('/api/sessions', json={}, headers={'Origin': 'https://other.example'}).status_code == 403
        assert client.post('/api/sessions', json={}, headers={'Origin': 'http://testserver'}).status_code == 200
