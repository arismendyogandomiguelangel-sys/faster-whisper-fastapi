"""
Router v2 para transcripcion con texto plano como respuesta.

Endpoint: POST /v2/transcribe
- Requiere Authorization: Bearer <API_KEY>
- Retorna el texto transcrito como string JSON
"""

import logging
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
    Transcribe un archivo de audio a texto usando faster-whisper.

    - **audio**: Archivo de audio (ogg, wav, mp3, flac, etc.)
    - Retorna el texto transcrito como string JSON.
    """
    async with lock:
        try:
            logger.info("Transcribiendo archivo: %s", audio.filename)
            segments, info = model.transcribe(audio.file, beam_size=5)
            text = "".join([segment.text for segment in segments])
            logger.info("Transcripcion completada: %d caracteres", len(text))
            return text
        except Exception as e:
            logger.error("Error durante transcripcion: %s", str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Transcription error: {str(e)}",
            )