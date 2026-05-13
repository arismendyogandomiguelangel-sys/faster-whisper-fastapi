# Faster Whisper API - Producción

API de transcripción de audio usando [faster-whisper](https://github.com/SYSTRAN/faster-whisper) con FastAPI, protegida por API key y lista para desplegar en Dokploy.

## Subdominio

```
https://teoigo.alianed.com
```

## Variables de entorno

Crea un archivo `.env` basado en `.env.example`:

```bash
cp .env.example .env
```

Edita `.env` con tus valores:

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

## Ejecución local

```bash
# Construir y levantar
docker compose up --build -d

# Ver logs
docker compose logs -f

# Detener
docker compose down
```

## Desplegar en Dokploy

1. En Dokploy, crea un nuevo servicio tipo **Docker Compose**
2. Sube el `docker-compose.yml` o apunta al repo
3. Configura las variables de entorno en el panel de Dokploy:
   - `MODEL_SIZE=small`
   - `PORT=8080`
   - `API_KEY=<tu-clave-secreta>`
   - `DEVICE=cpu`
   - `COMPUTE_TYPE=int8`
   - `ALLOWED_ORIGINS=*`
4. Configura el dominio: `teoigo.alianed.com`
5. Puerto del contenedor: `8080`
6. Haz deploy

## Consumo de la API

### Health check (público)

```bash
curl https://teoigo.alianed.com/health
```

Respuesta:
```json
{"status": "ok", "model": "small"}
```

### Transcripción (protegido)

```bash
curl -X POST \
  'https://teoigo.alianed.com/v2/transcribe' \
  -H 'Authorization: Bearer TU_API_KEY' \
  -H 'accept: application/json' \
  -F 'audio=@tu_audio.ogg;type=audio/ogg'
```

Respuesta:
```json
"texto transcrito del audio"
```

### Error si no envías API key

```bash
curl -X POST 'https://teoigo.alianed.com/v2/transcribe' \
  -F 'audio=@tu_audio.ogg'
```

Respuesta:
```json
{"detail": "Not authenticated"}
```

Status: `401 Unauthorized`

## Endpoints

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| GET | `/health` | No | Health check para Dokploy |
| POST | `/v2/transcribe` | Sí | Transcripción (texto plano) |
| POST | `/transcribe` | Sí | Transcripción legacy (deprecated) |
| GET | `/docs` | No | Swagger UI (desactivable con `DISABLE_DOCS=true`) |

## Arquitectura

```
┌─────────────────────────────────────────┐
│           Dokploy / Docker               │
│  ┌───────────────────────────────────┐   │
│  │    faster-whisper-fastapi         │   │
│  │                                   │   │
│  │  /health        -> PUBLICO        │   │
│  │  /v2/transcribe -> Bearer API_KEY │   │
│  │  /transcribe    -> Bearer API_KEY │   │
│  │                                   │   │
│  │  User: appuser (no root)          │   │
│  │  Port: 8080                       │   │
│  └───────────────────────────────────┘   │
│                                          │
│  Volume: whisper-cache -> HuggingFace    │
└─────────────────────────────────────────┘
```

## Seguridad

- ✅ Usuario no root (`appuser`)
- ✅ API key por Bearer token
- ✅ `/health` público solo para health checks
- ✅ CORS configurable
- ✅ Docs desactivables en producción
- ✅ Volumen persistente para caché de modelos
- ✅ Healthcheck para monitoreo

## Notas

- El modelo se descarga automáticamente al primer arranque
- El volumen `whisper-cache` persiste el modelo entre redeploys
- `COMPUTE_TYPE=int8` reduce consumo de RAM y es compatible con CPU
- `MODEL_SIZE=small` ~500MB RAM, buena relación calidad/rendimiento