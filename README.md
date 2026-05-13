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

### Instalación (cero terminal)

1. **Doble-click en `INSTALL_TEOIGO.bat`**. Esto:
   - Instala las dependencias (keyboard, sounddevice, pystray, etc.)
   - Crea el icono "TEOIGO Dictado" en el escritorio
   - Configura inicio automático con Windows

### Uso diario

| Atajo | Acción |
|---|---|
| `Ctrl + Flecha Derecha` | Encender micrófono y empezar a dictar |
| `Ctrl + Flecha Izquierda` | Apagar micrófono |
| Doble-click en icono de bandeja | Mostrar / ocultar la píldora |
| `Ctrl + Shift + F12` | Cerrar TEOIGO |

### Comportamiento automático
- Si pasan **3 min sin que hables** durante una grabación → la píldora se oculta (sigue grabando si vuelves a hablar).
- Si pasan **5 min sin que uses la UI** → la píldora se minimiza sola a la bandeja.
- Si pasan **10 min sin uso** → TEOIGO se apaga solo.

### Flujo
1. Doble-click en el icono del escritorio → TEOIGO arranca minimizado en bandeja
2. Posicionas el cursor donde quieras escribir (Word, Chrome, etc.)
3. Presionas **Ctrl + Flecha Derecha** → píldora azul con ondas de voz
4. Hablas — el texto aparece automáticamente en la app activa
5. Presionas **Ctrl + Flecha Izquierda** para apagar el micrófono

> **Sin terminal nunca más.** Solo usas el icono del escritorio o el de la bandeja.

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
│  ├─ Escucha Ctrl+Right (graba) / Ctrl+Left (para)          │
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
