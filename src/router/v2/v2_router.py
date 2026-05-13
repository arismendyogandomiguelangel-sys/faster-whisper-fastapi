"""
Router v2 para transcripcion con texto plano como respuesta.

Endpoint: POST /v2/transcribe
- Requiere Authorization: Bearer <API_KEY>
- Retorna el texto transcrito como string JSON
"""

import io
import logging
import os
import httpx
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from depends import API_KEY, lock, model

logger = logging.getLogger(__name__)

v2_router = APIRouter(prefix="/v2", tags=["transcription-v2"])

# --- Seguridad: Bearer token ---
security = HTTPBearer()


def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Valida que el Bearer token coincida con la API_KEY configurada."""
    if credentials.credentials != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


@v2_router.post(
    "/transcribe",
    response_model=str,
    summary="Transcribe audio to text",
    description="Sube un archivo de audio y recibe el texto transcrito. Requiere API key.",
)
async def transcribe_v2(
    audio: UploadFile,
    _: str = Depends(verify_api_key),
) -> str:
    """
    Transcribe un archivo de audio a texto usando Groq API (ultra rapido) o faster-whisper local (fallback).

    - **audio**: Archivo de audio (ogg, wav, mp3, flac, etc.)
    - Retorna el texto transcrito como string.
    """
    audio_bytes = await audio.read()
    
    # Intento 1: Aceleracion por Hardware LPU via Groq API (Si esta configurada)
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            logger.info("Enviando audio a Groq (whisper-large-v3-turbo)...")
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    data={
                        "model": "whisper-large-v3-turbo",
                        "response_format": "json",
                        "language": "es"  # Optimizacion para español
                    },
                    files={"file": (audio.filename or "dictado.wav", audio_bytes, audio.content_type or "audio/wav")}
                )
                if response.status_code == 200:
                    text = response.json().get("text", "").strip()
                    logger.info("Transcripcion Groq completada (LPU): %d caracteres", len(text))
                    return text
                else:
                    logger.warning("Groq devolvio HTTP %d: %s. Cayendo al modelo local...", response.status_code, response.text)
        except Exception as e:
            logger.warning("Error conectando con Groq: %s. Cayendo al modelo local...", str(e))

    # Intento 2: Modelo Local en Dokploy (CPU/Ampere)
    async with lock:
        try:
            logger.info("Transcribiendo localmente archivo: %s", audio.filename)
            # Volver a crear un objeto tipo archivo para el modelo local
            audio_io = io.BytesIO(audio_bytes)
            audio_io.name = audio.filename or "dictado.wav"
            
            segments, info = model.transcribe(audio_io, beam_size=5)
            text = "".join([segment.text for segment in segments])
            logger.info("Transcripcion local completada: %d caracteres", len(text))
            return text
        except Exception as e:
            logger.error("Error durante transcripcion local: %s", str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Transcription error: {str(e)}",
            )
