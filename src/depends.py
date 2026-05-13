"""
Dependencias globales del servicio Whisper.

Este módulo carga el modelo faster-whisper una sola vez al arrancar
y expone el lock asyncio para serializar las peticiones de transcripcion.
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from faster_whisper import WhisperModel

# Cargar variables de entorno desde .env
load_dotenv()

# --- Configuracion del modelo ---
MODEL_SIZE = os.getenv("MODEL_SIZE", "small")
DEVICE = os.getenv("DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "int8")

# Validar que API_KEY este definida
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise RuntimeError(
        "La variable de entorno API_KEY no esta definida. "
        "Crea un archivo .env basado en .env.example con tu clave secreta."
    )

# Puerto para uvicorn
PORT = int(os.getenv("PORT", "8080"))

# Flag para desactivar docs en produccion
DISABLE_DOCS = os.getenv("DISABLE_DOCS", "false").lower() == "true"

# --- Inicializar modelo ---
logger = logging.getLogger(__name__)
logger.info(
    "Cargando modelo Whisper: size=%s, device=%s, compute_type=%s",
    MODEL_SIZE,
    DEVICE,
    COMPUTE_TYPE,
)

model = WhisperModel(
    model_size_or_path=MODEL_SIZE,
    device=DEVICE,
    compute_type=COMPUTE_TYPE,
)

logger.info("Modelo Whisper cargado correctamente.")

# --- Lock para serializar peticiones (evita saturacion de memoria) ---
lock = asyncio.Lock()