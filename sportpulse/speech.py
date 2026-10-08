"""Optional microphone recording transcription; browser-native speech is still primary.

Only send audio off-device when OpenAI STT is explicitly active (or auto with an
OpenAI API key). Local faster-whisper stays on device except its initial model download.
"""
import asyncio
import logging
import tempfile
from pathlib import Path

import httpx

MAX_AUDIO_BYTES = 8 * 1024 * 1024
MIME_EXTENSIONS = {
    'audio/webm': '.webm', 'audio/ogg': '.ogg', 'audio/mp4': '.mp4',
    'audio/mpeg': '.mp3', 'audio/wav': '.wav', 'audio/x-wav': '.wav',
}
logger = logging.getLogger('pitchpulse.speech')
_local_models = {}
_local_lock = asyncio.Lock()


class STTFailure(Exception):
    """Safe client-facing reason, not a raw vendor exception or secret."""


def transcribe_local_sync(audio: bytes, extension: str, model_name: str, language: str) -> str:
    from faster_whisper import WhisperModel
    if model_name not in ('tiny', 'base', 'small'):
        raise STTFailure('Invalid local model. Choose tiny, base or small in .env.')
    if model_name not in _local_models:
        _local_models[model_name] = WhisperModel(model_name, device='cpu', compute_type='int8')
    # Write temporary audio only for decoder compatibility; delete immediately afterward.
    with tempfile.TemporaryDirectory(prefix='pitchpulse-voice-') as folder:
        file_path = Path(folder) / ('speech' + extension)
        file_path.write_bytes(audio)
        kwargs = {'beam_size': 1, 'vad_filter': True}
        if language in ('hi', 'en'):
            kwargs['language'] = language
        segments, _ = _local_models[model_name].transcribe(str(file_path), **kwargs)
        return ' '.join(segment.text.strip() for segment in segments).strip()


async def transcribe(audio: bytes, mime_type: str, language: str, settings, client: httpx.AsyncClient) -> str:
    mime_type = mime_type.split(';', 1)[0].strip().lower()
    if mime_type not in MIME_EXTENSIONS:
        raise STTFailure('Unsupported recording type. Use current Chrome or Edge.')
    if not 300 <= len(audio) <= MAX_AUDIO_BYTES:
        raise STTFailure('Recording must contain audio and be under 8 MB.')
    provider = settings.stt_backend
    if provider == 'none':
        raise STTFailure('Recording transcription not configured. Add OPENAI_API_KEY or install offline voice.')
    if provider == 'local':
        # Expensive CPU recognition is moved off the event loop. Guard model load.
        async with _local_lock:
            try:
                text = await asyncio.to_thread(transcribe_local_sync, audio, MIME_EXTENSIONS[mime_type],
                                               settings.stt_local_model, language)
            except STTFailure:
                raise
            except Exception:
                logger.exception('Offline transcription failed')
                raise STTFailure('Offline transcription failed. Check the server console and local model setup.')
    else:
        try:
            r = await client.post('https://api.openai.com/v1/audio/transcriptions',
                                  headers={'Authorization': 'Bearer ' + settings.openai_api_key},
                                  data={'model': settings.stt_model},
                                  files={'file': ('speech' + MIME_EXTENSIONS[mime_type], audio, mime_type)},
                                  timeout=httpx.Timeout(65, connect=10))
            if r.status_code in (401, 403):
                raise STTFailure('OpenAI transcription key or account access was rejected.')
            if r.status_code == 429:
                raise STTFailure('OpenAI transcription rate limit reached; try again later.')
            if r.status_code >= 400:
                logger.warning('OpenAI transcription HTTP status: %d', r.status_code)
                raise STTFailure('Transcription service returned an error. Check API credentials and credit.')
            text = str(r.json().get('text') or '').strip()
        except STTFailure:
            raise
        except (httpx.TimeoutException, httpx.RequestError):
            raise STTFailure('Transcription service unreachable. Check your internet connection.')
        except (ValueError, TypeError, KeyError):
            raise STTFailure('Transcription service sent an unexpected response.')
    if not text:
        raise STTFailure('No words detected in this recording. Speak clearly and try again.')
    return text[:750].strip()
