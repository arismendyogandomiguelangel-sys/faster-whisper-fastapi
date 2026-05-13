# Faster Whisper API + Cliente de Dictado — TEOIGO

API de transcripción de audio usando [faster-whisper](https://github.com/SYSTRAN/faster-whisper) con FastAPI, protegida por API key y lista para desplegar en Dokploy.

**Incluye un cliente de escritorio para Windows** que permite dictar texto en cualquier aplicación.

## Subdominio

```
https://teoigo.alianed.com
```

---

## Cliente de Dictado (Windows)

El cliente de escritorio te permite dictar texto usando tu voz en **cualquier aplicación** (Word, Excel, VS Code, Chrome, Antigravity, etc.).

### Instalación rápida

```bash
# 1. Doble clic en INSTALL_CLIENT.bat
#    o manualmente:
pip install -r client_requirements.txt
```

### Uso

```bash
# Ejecutar el cliente (se queda en segundo plano)
pythonw teoigo_client.pyw
```

| Atajo | Acción |
|-------|--------|
| `Ctrl + Flecha Derecha` | Iniciar / Detener grabación |
| `Ctrl + Shift + F12` | Cerrar TEOIGO |

### Flujo
1. Ejecutas `teoigo_client.pyw` (se queda en fondo)
2. Posicionas el cursor donde quieras escribir (Word, Chrome, etc.)
3. Presionas **Ctrl + Flecha Derecha** → aparece notificación "Grabando..."
4. Hablas lo que quieras dictar
5. Presionas **Ctrl + Flecha Derecha** de nuevo → el texto se pega automáticamente

### Configuración

Edita las variables al inicio de `teoigo_client.pyw`:

```python
WHISPER_URL = "https://teoigo.alianed.com/v2/transcribe"
API_KEY = "TU_API_KEY_AQUI"
```

O usa variables de entorno:
```bash
set TEOIGO_URL=https://teoigo.alianed.com/v2/transcribe
set TEOIGO_API_KEY=tu_clave_secreta
```

---

## Servidor (Backend API)

### Variables de entorno

Crea un archivo `.env` basado en `.env.example`:

```bash
cp .env.example .env
```

```env
MODEL_SIZE=small
PORT=8080
API_KEY=tu_clave_super_larga_y_random
DEVICE=cpu
COMPUTE_TYPE=int8
ALLOWED_ORIGINS=*
DISABLE_DOCS=false
```

> **IMPORTANTE**: Nunca subas el archivo `.env` al repositorio. Solo `.env.example` está versionado.

### Ejecución local

```bash
docker compose up --build -d
docker compose logs -f
docker compose down
```

### Desplegar en Dokploy

1. Crea un nuevo servicio tipo **Docker Compose**
2. Apunta al repo
3. Configura las variables de entorno en Dokploy
4. Dominio: `teoigo.alianed.com` → Puerto `8080`
5. Deploy

### Consumo de la API

#### Health check (público)
```bash
curl https://teoigo.alianed.com/health
```

#### Transcripción (protegido)
```bash
curl -X POST \
  'https://teoigo.alianed.com/v2/transcribe' \
  -H 'Authorization: Bearer TU_API_KEY' \
  -F 'audio=@tu_audio.ogg'
```

### Endpoints

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| GET | `/` | No | UI web (demo) |
| GET | `/health` | No | Health check para Dokploy |
| POST | `/v2/transcribe` | Sí | Transcripción (texto plano) |
| POST | `/transcribe` | Sí | Transcripción legacy (deprecated) |
| GET | `/docs` | No | Swagger UI (desactivable) |

## Arquitectura

```
┌────────────────────────────────────────────────┐
│               TU PC (Windows)                    │
│                                                  │
│  teoigo_client.pyw                                │
│  │                                                │
│  ├─ Escucha Ctrl+Flecha Derecha (global)          │
│  ├─ Graba audio del micrófono                     │
│  ├─ Envía audio a teoigo.alianed.com ────────────┐ │
│  ├─ Recibe texto transcrito   ◄────────────────┘ │
│  └─ Pega texto en app activa (Ctrl+V)              │
│                                                  │
│  Word │ Excel │ VS Code │ Chrome │ Antigravity    │
└────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────┐
│           Dokploy (Oracle Cloud)                  │
│                                                  │
│  faster-whisper-fastapi                           │
│  │                                                │
│  ├─ /health        → PÚBLICO                      │
│  ├─ /v2/transcribe → Bearer API_KEY               │
│  └─ /transcribe    → Bearer API_KEY (deprecated)   │
│                                                  │
│  Volume: whisper-cache → HuggingFace             │
└────────────────────────────────────────────────┘
```

## Seguridad

- ✅ Usuario no root (`appuser`)
- ✅ API key por Bearer token
- ✅ `/health` público solo para health checks
- ✅ CORS configurable
- ✅ Docs desactivables en producción
- ✅ Volumen persistente para caché de modelos
- ✅ Healthcheck para monitoreo
