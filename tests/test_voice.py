"""No external APIs or model downloads are called in this suite."""
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient
from sportpulse.config import Settings
from sportpulse.main import app
from sportpulse.speech import transcribe, STTFailure, MAX_AUDIO_BYTES


def test_health_has_voice_capability():
    with TestClient(app) as client:
        health = client.get('/api/health')
        assert health.status_code == 200
        assert health.json()['version'] == '1.3.0'
        assert isinstance(health.json()['stt_ready'], bool)
        assert health.json()['stt_backend'] in ('none', 'openai', 'local')
        assert 'Test microphone' in client.get('/').text
        assert 'backup recording' in client.get('/static/app.js').text


def test_transcribe_wrong_type_and_oversize():
    with TestClient(app) as client:
        bad = client.post('/api/transcribe', files={'audio': ('evil.txt', b'x' * 500, 'text/plain')})
        assert bad.status_code in (415, 503)  # Provider may be unset.
        huge = client.post('/api/transcribe', content=b'x' * (MAX_AUDIO_BYTES + 66000),
                           headers={'Content-Type': 'application/octet-stream'})
        assert huge.status_code == 413


@pytest.mark.asyncio
async def test_audio_mime_and_empty_rejections():
    opts = replace(Settings(), stt_provider='openai', openai_api_key='fake-secret')
    async with httpx.AsyncClient() as client:
        with pytest.raises(STTFailure, match='Unsupported'):
            await transcribe(b'a' * 400, 'text/plain', 'en', opts, client)
        with pytest.raises(STTFailure, match='Recording must'):
            await transcribe(b'', 'audio/webm', 'en', opts, client)


@pytest.mark.asyncio
async def test_openai_transcription_contract():
    def handler(request):
        assert request.url.path == '/v1/audio/transcriptions'
        assert request.headers['Authorization'] == 'Bearer fake-secret'
        assert b'gpt-4o-mini-transcribe' in request.content
        assert b'filename="speech.webm"' in request.content
        return httpx.Response(200, json={'text': 'What is the India cricket score?'})
    opts = replace(Settings(), stt_provider='openai', openai_api_key='fake-secret')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        text = await transcribe(b'x'*2000, 'audio/webm;codecs=opus', 'en', opts, client)
    assert text == 'What is the India cricket score?'


@pytest.mark.asyncio
async def test_transcription_vendor_key_error_safe():
    opts = replace(Settings(), stt_provider='openai', openai_api_key='fake-secret')
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(401, text='sensitive'))) as client:
        with pytest.raises(STTFailure, match='key or account access') as info:
            await transcribe(b'x' * 800, 'audio/webm', 'en', opts, client)
        assert 'sensitive' not in str(info.value)


def test_stt_settings_no_provider():
    opts = replace(Settings(), stt_provider='off', openai_api_key='fake-secret')
    assert opts.stt_backend == 'none'
    opts = replace(Settings(), stt_provider='openai', openai_api_key='fake-secret')
    assert opts.stt_backend == 'openai'


def test_backend_audio_unconfigured_returns_503():
    # Tests on a machine without keys/local engine; if environment has keys skip.
    from sportpulse.main import settings
    if settings.stt_backend != 'none':
        pytest.skip('Optional transcription provider configured in environment.')
    with TestClient(app) as client:
        r=client.post('/api/transcribe', files={'audio': ('speech.webm', b'a'*1024, 'audio/webm')})
        assert r.status_code == 503
        assert 'Recording transcription is not configured' in r.json()['detail']
