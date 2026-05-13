"""
Aplicacion principal FastAPI para faster-whisper.

Endpoints:
- GET  /           -> Retorna la UI estatica de Whisper ALiaNeD
- GET  /health     -> Health check (PUBLICO, sin auth)
- POST /transcribe -> Transcripcion legacy (protegido con API key, deprecated)
- POST /v2/transcribe -> Transcripcion v2 (protegido con API key, texto plano)

Seguridad:
- /health es PUBLICO para que Dokploy pueda hacer health checks
- /transcribe y /v2/transcribe requieren Authorization: Bearer <API_KEY>
"""

import logging
import os
from typing import Literal

import uvicorn
from fastapi import FastAPI, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from depends import API_KEY, DISABLE_DOCS, PORT, lock, model
from router.v2.v2_router import v2_router

# --- Configuracion de logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# --- Configuracion de CORS ---
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# --- Configuracion de la app ---
app = FastAPI(
    title="Faster Whisper API",
    description="API de transcripcion de audio usando faster-whisper. Protegida por API key.",
    version="1.1.0",
    docs_url="/docs" if not DISABLE_DOCS else None,
    redoc_url="/redoc" if not DISABLE_DOCS else None,
)

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir archivos estaticos (UI y Logo)
# Verificamos si existe el directorio para no romper en desarrollo si falta
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Incluir router v2
app.include_router(v2_router)

# --- Seguridad: Bearer token ---
security = HTTPBearer()


def verify_api_key(credentials: HTTPAuthorizationCredentials = security) -> str:
    """Valida que el Bearer token coincida con la API_KEY configurada."""
    if credentials.credentials != API_KEY:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


# --- Endpoints ---

@app.get("/", include_in_schema=False)
def index():
    """Retorna la UI web si existe, si no, redirige a /docs."""
    index_file = os.path.join(static_dir, "index.html")
    if os.path.isfile(index_file):
        return FileResponse(index_file)
    
    if DISABLE_DOCS:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Documentation disabled and UI not found"},
        )
    return RedirectResponse(url="/docs")


@app.get("/health")
def health():
    """
    Health check PUBLICO.

    Este endpoint NO requiere autenticacion para que Dokploy
    pueda verificar el estado del servicio.
    """
    return {"status": "ok", "model": os.getenv("MODEL_SIZE", "unknown")}


@app.post(
    "/transcribe",
    deprecated=True,
    summary="Transcribe audio (legacy)",
    description="Endpoint legacy. Usa /v2/transcribe en su lugar.",
)
async def transcribe_legacy(
    response: Response,
    audio: UploadFile,
    credentials: HTTPAuthorizationCredentials = security,
) -> dict[Literal["response", "status"], str]:
    """
    Endpoint legacy de transcripcion (protegido con API key).

    Usa /v2/transcribe para la version actualizada.
    """
    # Validar API key
    if credentials.credentials != API_KEY:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"status": "error", "response": "Invalid API key"}

    async with lock:
        try:
            segments, info = model.transcribe(audio.file, beam_size=5)
            text = "".join([segment.text for segment in segments])
            return {"status": "ok", "response": text}
        except Exception as e:
            logger.error("Error en transcripcion legacy: %s", str(e))
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return {"status": "error", "response": f"error: {e}"}


@app.exception_handler(Exception)
def handle_exception(request: Request, exc: Exception):
    """Manejador global de excepciones."""
    logger.error("Excepcion no manejada: %s", str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc)},
    )


# --- Entry point ---
if __name__ == "__main__":
    logger.info("Iniciando servidor en puerto %d", PORT)
    logger.info("Modelo: %s | Device: %s | Compute: %s",
                os.getenv("MODEL_SIZE", "unknown"),
                os.getenv("DEVICE", "cpu"),
                os.getenv("COMPUTE_TYPE", "int8"))
    logger.info("Docs habilitados: %s", not DISABLE_DOCS)
    logger.info("CORS origins: %s", ALLOWED_ORIGINS)

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=PORT,
        workers=1,  # Un solo worker para evitar conflictos con el lock
    )