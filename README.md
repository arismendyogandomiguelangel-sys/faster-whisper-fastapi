# TEOIGO v3.0 — Cliente de Dictado por Voz con Voice ID

Cliente de escritorio para Windows que permite dictar texto por voz en **cualquier aplicación** (Word, VS Code, Chrome, etc.) usando inteligencia artificial para transcripción.

**Servidor backend:** faster-whisper vía FastAPI en Dokploy (Oracle Cloud).

---

## Novedades en v3.0

| Feature | Descripción |
|---|---|
| 🎙️ **Voice ID** | Reconoce tu timbre de voz y filtra audio ajeno (TV, otras personas) |
| 📡 **API Groq** | Transcripción en ~1.3s usando Whisper Large v3 Turbo |
| 🔄 **Fallback automático** | Groq Key 1 → Groq Key 2 → Servidor Whisper |
| 🎛️ **Modos de operación** | Dictado (solo tu voz) / General (todo audio) |
| 🚦 **Telemetría visual** | 5 LEDs de semáforo en la píldora: Whisper, Mic, Voice ID, Groq, Final |
| 📋 **Logs de diagnóstico** | Historial de 20 oraciones con estado de LEDs copiable al portapapeles |
| ⚙️ **Config persistente** | `teoigo_config.json` — umbrales, keys, modos guardados entre reinicios |
| 🗑️ **Perfil de voz** | Botón para eliminar/re-grabar perfil de voz desde menú tray |

---

## Instalación

1. **Ejecutar `INSTALL_TEOIGO.bat`** (doble clic). Esto:
   - Instala dependencias Python (keyboard, sounddevice, pystray, resemblyzer, etc.)
   - Crea acceso directo "TEOIGO Dictado" en el escritorio
   - Configura inicio automático con Windows

2. **Ejecutar desde el icono del escritorio** — sin terminal, sin comandos.

---

## Uso Diario

| Atajo | Acción |
|---|---|
| `Ctrl + Flecha Derecha` | Encender micrófono y empezar a dictar |
| `Ctrl + Flecha Izquierda` | Apagar micrófono |
| Doble clic en icono de bandeja | Mostrar / ocultar píldora |
| `Ctrl + Shift + F12` | Cerrar TEOIGO |

### Menú del System Tray (clic derecho en el icono)

```
┌──────────────────────────────────┐
│ Mostrar/Ocultar Píldora          │
│ Dictar (Ctrl+Right)              │
│ ──────────────────────────────── │
│ Modo ▸  ● Dictado                │
│          ○ General               │
│ 🎙️ Configurar Mi Voz            │
│ 🗑️ Eliminar Perfil de Voz       │
│ ──────────────────────────────── │
│ Copiar Logs de Diagnóstico       │
│ Limpiar Logs                     │
│ ──────────────────────────────── │
│ Auto-Actualizar al Reiniciar     │
│ Reiniciar TEOIGO                 │
│ Salir                            │
│ └──────────────────────────────────┘
```

**Descripción de las opciones:**
- **Mostrar/Ocultar Píldora**: Alterna la visibilidad del widget flotante (píldora).
- **Dictar**: Activa el micrófono y comienza a grabar (equivalente a `Ctrl + Flecha Derecha`).
- **Modo**: 
  - *Dictado*: Solo transcribe tu voz, filtrando otros ruidos o voces usando Voice ID.
  - *General*: Transcribe todo el audio capturado por el micrófono.
- **Configurar Mi Voz**: Inicia el asistente para grabar y crear tu perfil de voz (`voice_profile.npy`).
- **Eliminar Perfil de Voz**: Borra tu perfil de voz actual si deseas grabarlo nuevamente.
- **Copiar Logs de Diagnóstico**: Copia al portapapeles el historial de las últimas transcripciones y el estado de la conexión.
- **Limpiar Logs**: Borra el historial de diagnósticos actual.
- **Auto-Actualizar al Reiniciar**: Activa o desactiva la actualización automática del código desde el repositorio de GitHub al reiniciar.
- **Reiniciar TEOIGO**: Reinicia la aplicación limpiando cachés.
- **Salir**: Cierra TEOIGO por completo.

### Flujo de Dictado

1. Abre TEOIGO desde el icono del escritorio → aparece en bandeja
2. Posiciona el cursor donde quieras escribir (Word, Chrome, etc.)
3. Presiona **Ctrl + Flecha Derecha** → píldora con ondas de voz
4. Habla — texto aparece automáticamente donde está el cursor
5. Presiona **Ctrl + Flecha Izquierda** para apagar

---

## Modos de Operación

| Modo | Comportamiento | Voice ID |
|---|---|---|
| **Dictado** | Solo transcribe tu voz. Ignora TV, videos, otras personas | ✅ Activo |
| **General** | Transcribe todo el audio que entra por el micrófono | ❌ Desactivado |

---

## Configuración de Voz (Voice ID)

1. Clic derecho en icono de bandeja → **"Grabar Mi Voz"**
2. Lee el párrafo guía durante 20 segundos variando tu tono (normal, suave, enérgico, rápido)
3. TEOIGO genera un perfil de voz y lo guarda como `voice_profile.npy`
4. En modo **Dictado**, solo transcribirá tu voz

**Recomendación:** Varia tu tono durante la grabación — normal, bajo (oración), alto (predicación), y rápido — para que el modelo capte todo tu espectro vocal.

---

## Telemetría Visual (Píldora)

La píldora muestra 5 LEDs tipo semáforo en la parte inferior:

| LED | Significado | Estados |
|---|---|---|
| **S** (Whisper) | Servicio de transcripción | 🟡 standby → 🟢 enviando → 🔴 error |
| **M** (Mic) | Micrófono | ⚫ apagado → 🟢 capturando |
| **V** (Voice ID) | Verificación de voz | ⚫ inactivo → 🟡 verificando → 🟢 voz propia → 🔴 rechazada |
| **G** (Groq) | API Groq | 🟡 esperando → 🟢 éxito → 🔴 falló |
| **T** (Final) | Resultado del ciclo | ⚫ en proceso → 🟢 éxito → 🔴 abortado |

---

## Logs de Diagnóstico

- El historial guarda las últimas 20 oraciones con el estado de cada LED
- **Copiar Logs de Diagnóstico**: copia la tabla al portapapeles
- **Limpiar Logs**: vacía el historial

Ejemplo de salida:
```
=== TEOIGO v3.0 — Logs de Diagnóstico ===
S=Whisper, M=Mic, V=VoiceID, G=Groq, T=Final
--------------------------------------------------
S:🟡, M:🟢, V:🟢, G:🟢, T:🟢 | 1.3s | "Bienaventurado el varón..."
```

---

## Comportamiento Automático

- **3 min sin hablar** durante grabación → píldora se oculta (sigue grabando)
- **5 min sin usar UI** → píldora se minimiza a bandeja
- **30 min sin uso** → TEOIGO se cierra automáticamente

---

## Archivos de Configuración

| Archivo | Propósito |
|---|---|
| `teoigo_config.json` | Config persistente (auto-generado). Contiene API keys, umbrales, modo activo |
| `voice_profile.npy` | Embedding de voz del usuario (256 dimensiones) |
| `teoigo.log` (en `%TEMP%`) | Log de ejecución |

**Nunca compartas `teoigo_config.json`** — contiene tus API keys.

---

## Dependencias

```
keyboard, sounddevice, numpy, requests, pyperclip, pyautogui
pystray, Pillow, resemblyzer, librosa, torch (CPU)
```

Instaladas automáticamente por `INSTALL_TEOIGO.bat`.

---

## Servidor Backend

El servidor de transcripción usa [faster-whisper](https://github.com/SYSTRAN/faster-whisper) con FastAPI, desplegado en Dokploy (Oracle Cloud).

**Subdominio:** `https://teoigo.alianed.com`

### Endpoints

| Método | Endpoint | Auth | Descripción |
|---|---|---|---|
| GET | `/health` | No | Health check |
| POST | `/v2/transcribe` | API Key | Transcripción de audio |
| GET | `/docs` | No | Swagger UI |

---

## Arquitectura

```
┌──────────────────────────────────────────────────────┐
│                   TU PC (Windows)                    │
│                                                      │
│  teoigo_client.pyw                                    │
│  ├─ Escucha Ctrl+Right (graba) / Ctrl+Left (para)    │
│  ├─ Graba audio del micrófono                         │
│  ├─ Voice ID: verifica si es tu voz (Resemblyzer)     │
│  ├─ Envía a Groq API ──────────────────────────────┐ │
│  │   ├─ Groq Key 1 (Whisper Large v3 Turbo)        │ │
│  │   ├─ Groq Key 2 (fallback)                      │ │
│  │   └─ Servidor Whisper (fallback final)           │ │
│  ├─ Recibe texto transcrito ◄──────────────────────┘ │
│  └─ Pega texto en app activa (Ctrl+V)                │
│                                                      │
└──────────────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
┌─────────────────┐    ┌──────────────────────┐
│   Groq Cloud    │    │  Dokploy (Oracle)    │
│  (whisper-v3)   │    │  faster-whisper API  │
└─────────────────┘    └──────────────────────┘
```

## Seguridad

- ✅ Usuario no root (`appuser`)
- ✅ API key por Bearer token
- ✅ `/health` público solo para health checks
- ✅ CORS configurable
- ✅ Docs desactivables en producción
- ✅ Volumen persistente para caché de modelos
- ✅ Healthcheck para monitoreo
