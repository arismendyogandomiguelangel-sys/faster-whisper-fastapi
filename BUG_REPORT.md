# BUG_REPORT — TEOIGO v1.1.0 (2026-05-13)

## Resumen Ejecutivo

El cliente de dictado TEOIGO transcribe audio correctamente (servidor responde HTTP 200 con texto), pero **NO inyecta el texto en la aplicación objetivo** (Word, Excel, navegador, etc.). El texto solo es visible en la terminal cuando se ejecuta con `python teoigo_client.pyw`, pero nunca llega a donde está el cursor.

---

## BUG #1 [CRÍTICO] — Foco robado por la ventana overlay antes del pegado

| Campo | Detalle |
|---|---|
| **Archivo** | `teoigo_client.pyw` |
| **Línea exacta** | 384-385 (`_stop_and_transcribe`) que llama a `set_state()` → `deiconify()` en línea 297 |
| **Descripción** | La píldora Tkinter (`overrideredirect`, `-topmost`) llama a `deiconify()` al cambiar de estado. Esto puede **activar/robar el foco** en Windows justo antes de que `pyautogui.hotkey('ctrl', 'v')` se ejecute (línea 437 original). |
| **Resultado esperado** | Ctrl+V pega el texto en Word/Excel/Navegador donde está el cursor del usuario |
| **Resultado real** | Ctrl+V se envía a la ventana overlay (que ignora el input) o a ninguna ventana. El texto nunca aparece. |
| **Fix aplicado** | 1. Pausa de 350ms antes de inyectar texto para que Windows reasigne el foco<br>2. Uso de `keyboard.write()` (nivel OS, no requiere foco ni portapapeles)<br>3. Todos los cambios de estado del overlay se ejecutan vía `root.after(0, ...)` en el main thread |

---

## BUG #2 [ALTO] — GUI Tkinter manipulada desde hilo daemon (thread-safety)

| Campo | Detalle |
|---|---|
| **Archivo** | `teoigo_client.pyw` |
| **Línea exacta** | 529 — `threading.Thread(target=client.toggle_recording, daemon=True).start()` |
| **Descripción** | Todo `_stop_and_transcribe()` corre en un hilo **daemon**. Las líneas 384, 446, 450, 453 originales modifican la GUI Tkinter (`set_state` → `deiconify()`) desde ese hilo. **Tkinter NO es thread-safe**. |
| **Resultado esperado** | GUI Tkinter se actualiza sin race conditions |
| **Resultado real** | `deiconify()` puede fallar silenciosamente, robar foco en momentos impredecibles, o causar crashes aleatorios. `pyautogui.hotkey()` y `pyperclip.copy()` llamados desde hilo no principal tienen comportamiento errático en Windows (STA/COM). |
| **Fix aplicado** | Implementados métodos `_safe_set_state()`, `_safe_start_fade()`, `_safe_update_volume()` que delegan al main thread vía `root.after(0, fn)` |

---

## BUG #3 [MEDIO] — `pyautogui.hotkey()` compite con hook global de `keyboard`

| Campo | Detalle |
|---|---|
| **Archivo** | `teoigo_client.pyw` |
| **Línea exacta** | 437 original (`pyautogui.hotkey('ctrl', 'v')`) en combinación con 536 (`keyboard.add_hotkey(..., suppress=True)`) |
| **Descripción** | `keyboard.add_hotkey` instala un hook de teclado de bajo nivel (`WH_KEYBOARD_LL`). Aunque solo suprime Ctrl+Right, el hook está activo globalmente y puede interferir con `pyautogui.hotkey('ctrl', 'v')` cuando se llama desde el mismo proceso. |
| **Fix aplicado** | Reemplazado `pyautogui.hotkey('ctrl', 'v')` por `keyboard.write()` (primera opción), que usa `SendInput` a nivel OS sin depender de hooks. |

---

## BUG #4 [BAJO] — `INSTALL_CLIENT.bat` usa `pythonw` sin verificarlo

| Campo | Detalle |
|---|---|
| **Archivo** | `INSTALL_CLIENT.bat` |
| **Línea exacta** | 26 y 31 — `$s.TargetPath = 'pythonw'` |
| **Descripción** | El instalador asume que `pythonw.exe` está en el PATH. Si no lo está (instalación Python solo para el usuario, o venv), el acceso directo no funcionará y TEOIGO nunca arranca. |
| **Fix sugerido** | Resolver la ruta completa de `pythonw.exe` con `where pythonw` o usar la misma ruta que `python --version` |

---

## Fixes Aplicados — Resumen Técnico

### 1. Método `_inject_text()` (nuevo, líneas 385-450)
Reemplaza las líneas 427-449 originales. Implementa **3 estrategias en cascada**:
1. **`keyboard.write(text, delay=0.003)`** — Simula tipeo a nivel OS con `SendInput`. No requiere foco ni portapapeles. Es la más confiable.
2. **`pyautogui.typewrite(text, interval=0.003)`** — Fallback automático.
3. **Clipboard + Ctrl+V** — Último recurso, restaura portapapeles original.

Incluye **pausa de 350ms** pre-inyección para que Windows reasigne el foco a la ventana previamente activa.

### 2. Métodos `_safe_*()` (nuevos, líneas 335-349)
- `_safe_set_state()` — Actualiza estado del overlay en el main thread
- `_safe_start_fade()` — Inicia fade timer en el main thread
- `_safe_update_volume()` — Actualiza volumen en el main thread

Todos usan `self.overlay.root.after(0, fn)` para encolar la operación en el event loop de Tkinter.

### 3. Logging mejorado
Cada intento de inyección emite logs detallados:
```
[TEOIGO] Inyectando texto (42 chars) en aplicacion activa...
[TEOIGO]   -> Probando keyboard.write()...
[TEOIGO]   -> [OK] Texto inyectado via keyboard.write()
```

---

## Verificación Pendiente

- [ ] Ejecutar `python teoigo_client.pyw` desde terminal, dictar, verificar que texto aparece en app objetivo
- [ ] Ejecutar desde acceso directo (`pythonw`), verificar mismo comportamiento
- [ ] Probar con Word, Excel, navegador (Chrome), Notepad
- [ ] Probar con texto en español con acentos y ñ
- [ ] Probar con texto largo (>200 caracteres)
