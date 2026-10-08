from fastapi.testclient import TestClient
from sportpulse.main import app


def test_health_and_frontend():
    with TestClient(app) as client:
        health = client.get('/api/health')
        assert health.status_code == 200
        assert health.json()['ok'] is True
        html = client.get('/')
        assert html.status_code == 200
        assert 'PitchPulse AI' in html.text
        assert 'Content-Security-Policy' in html.headers
        js = client.get('/static/app.js')
        assert js.status_code == 200
        assert 'SpeechRecognition' in js.text


def test_validation_and_missing_keys():
    with TestClient(app) as client:
        assert client.post('/api/chat', json={'message':''}).status_code == 422
        assert client.get('/api/news?sport=volleyball').status_code == 422
        assert client.get('/api/matches?sport=hockey').status_code == 422
        assert client.get('/api/matches?sport=cricket').status_code == 200
