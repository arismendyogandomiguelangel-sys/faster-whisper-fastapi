"""
TEOIGO — Cliente de Dictado por Voz para Windows
=================================================
Herramienta del ecosistema ALiaNeD.

Widget tipo pildora flotante con fondo transparente.
Solo se ven el borde y las ondas reactivas.

Uso:
  Ctrl + Flecha Derecha  = Iniciar / Detener dictado
  Ctrl + Shift + F12     = Salir
"""

import io
import os
import sys
import time
import wave
import math
import threading
import ctypes
import random
import traceback

import keyboard
import sounddevice as sd
import numpy as np
import requests
import pyperclip
import pyautogui

import tkinter as tk

# ============================================================================
# CONFIGURACION
# ============================================================================
WHISPER_URL = os.getenv(
    "TEOIGO_URL",
    "https://teoigo.alianed.com/v2/transcribe"
)
API_KEY = os.getenv(
    "TEOIGO_API_KEY",
    "DIosesmiVozyEscudo_!321"
)

SAMPLE_RATE = 16000
CHANNELS = 1

# ============================================================================
# COLORES ALiaNeD
# ============================================================================
ALIANED_COLORS = [
    "#ff007f",
    "#ff2a6d",
    "#ff5555",
    "#ff8c00",
    "#ffbb33",
    "#aadd00",
    "#40e0d0",
    "#00bfff",
    "#0077ff",
    "#0044ff",
    "#5533ff",
    "#8800ff",
]

# Color exacto que tkinter hara invisible
TRANSPARENT_COLOR = "#010101"

# ============================================================================
# LOG VISIBLE (escribe en consola para debugging)
# ============================================================================
def log(msg):
    print(f"[TEOIGO] {msg}")


# ============================================================================
# WIDGET OVERLAY — Pildora transparente con ondas
# ============================================================================

class PillOverlay:
    # Mas estrecho: 180px ancho x 46px alto
    WIDTH = 180
    HEIGHT = 46
    CORNER_RADIUS = 23
    NUM_BARS = 22

    STATE_HIDDEN = "hidden"
    STATE_IDLE = "idle"
    STATE_LISTENING = "listening"
    STATE_PROCESSING = "processing"
    STATE_ERROR = "error"

    def __init__(self):
        self.state = self.STATE_HIDDEN
        self.volume_level = 0.0
        self.drag_data = {"x": 0, "y": 0}
        self._fade_timer = None
        self._fade_seconds = 0
        self.status_text = ""

        # --- Ventana ---
        self.root = tk.Tk()
        self.root.title("TEOIGO")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        self.root.configure(bg=TRANSPARENT_COLOR)
        self.root.wm_attributes("-transparentcolor", TRANSPARENT_COLOR)

        # Posicionar arriba-centro
        screen_w = self.root.winfo_screenwidth()
        x_pos = (screen_w - self.WIDTH) // 2
        y_pos = 8
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x_pos}+{y_pos}")

        # Canvas
        self.canvas = tk.Canvas(
            self.root,
            width=self.WIDTH,
            height=self.HEIGHT,
            bg=TRANSPARENT_COLOR,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack()

        # Arrastre
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_move)

        # Oculto al inicio
        self.root.withdraw()

        # Colores de barras
        self.bar_colors = []
        for i in range(self.NUM_BARS):
            idx = int(i / self.NUM_BARS * len(ALIANED_COLORS))
            idx = min(idx, len(ALIANED_COLORS) - 1)
            self.bar_colors.append(ALIANED_COLORS[idx])

        self.target_heights = [2.0] * self.NUM_BARS
        self.current_heights = [2.0] * self.NUM_BARS

        self._animate()

    def _draw_frame(self):
        self.canvas.delete("all")
        w, h = self.WIDTH, self.HEIGHT
        r = self.CORNER_RADIUS

        # FONDO = TRANSPARENTE (solo borde visible)
        if self.state == self.STATE_PROCESSING:
            border_color = "#ffbb33"
        elif self.state == self.STATE_LISTENING:
            border_color = "#ff007f"
        elif self.state == self.STATE_ERROR:
            border_color = "#ff3333"
        else:
            border_color = "#444466"

        # Pildora con fondo transparente, solo borde
        self._draw_rounded_rect(
            2, 2, w - 2, h - 2, r,
            fill=TRANSPARENT_COLOR,  # Fondo invisible
            outline=border_color,
            width=2,
        )

        # Sombra sutil interior para dar profundidad (rectangulo oscuro semi-visible)
        self._draw_rounded_rect(
            4, 4, w - 4, h - 4, r - 2,
            fill="#0a0a15",  # Apenas visible, muy oscuro
            outline="",
            width=0,
        )

        # --- Barras de audio ---
        bar_area_x = 12
        bar_area_w = w - 24
        bar_spacing = bar_area_w / self.NUM_BARS
        bar_width = max(3, bar_spacing - 2)
        center_y = h / 2

        for i in range(self.NUM_BARS):
            bh = self.current_heights[i]
            x = bar_area_x + i * bar_spacing + (bar_spacing - bar_width) / 2
            half_h = bh / 2
            color = self.bar_colors[i]

            if self.state == self.STATE_IDLE:
                color = self._dim_color(color, 0.25)
            elif self.state == self.STATE_PROCESSING:
                color = self._dim_color(color, 0.5)
            elif self.state == self.STATE_ERROR:
                color = "#ff3333"

            self.canvas.create_rectangle(
                x, center_y - half_h,
                x + bar_width, center_y + half_h,
                fill=color, outline="", width=0,
            )

        # Texto de estado si hay
        if self.status_text:
            self.canvas.create_text(
                w / 2, h / 2,
                text=self.status_text,
                fill="#ffffff" if self.state != self.STATE_ERROR else "#ff6666",
                font=("Segoe UI", 7, "bold"),
                anchor="center",
            )

    def _draw_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1,
            x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2,
            x1 + r, y2, x1, y2, x1, y2 - r,
            x1, y1 + r, x1, y1, x1 + r, y1,
        ]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    @staticmethod
    def _dim_color(hex_color, factor):
        hex_color = hex_color.lstrip("#")
        r = int(int(hex_color[0:2], 16) * factor)
        g = int(int(hex_color[2:4], 16) * factor)
        b = int(int(hex_color[4:6], 16) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _animate(self):
        self._update_heights()
        self._draw_frame()
        self.root.after(33, self._animate)

    def _update_heights(self):
        max_h = self.HEIGHT - 14

        if self.state == self.STATE_LISTENING:
            vol = min(self.volume_level, 1.0)
            for i in range(self.NUM_BARS):
                noise = random.uniform(0.5, 1.3)
                center_factor = 1.0 - abs(i - self.NUM_BARS / 2) / (self.NUM_BARS / 2) * 0.4
                target = max(3, vol * max_h * noise * center_factor)
                self.target_heights[i] = min(target, max_h)
        elif self.state == self.STATE_PROCESSING:
            t = time.time() * 3
            for i in range(self.NUM_BARS):
                wave_val = math.sin(t + i * 0.4) * 0.5 + 0.5
                self.target_heights[i] = 4 + wave_val * max_h * 0.3
        elif self.state == self.STATE_IDLE:
            t = time.time() * 1.5
            for i in range(self.NUM_BARS):
                breath = math.sin(t + i * 0.2) * 1.5 + 3
                self.target_heights[i] = breath
        else:
            for i in range(self.NUM_BARS):
                self.target_heights[i] = 2.0

        ease = 0.25
        for i in range(self.NUM_BARS):
            self.current_heights[i] += (self.target_heights[i] - self.current_heights[i]) * ease

    def _on_drag_start(self, event):
        self.drag_data["x"] = event.x
        self.drag_data["y"] = event.y

    def _on_drag_move(self, event):
        dx = event.x - self.drag_data["x"]
        dy = event.y - self.drag_data["y"]
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")

    def show(self, state=None):
        if state:
            self.state = state
        elif self.state == self.STATE_HIDDEN:
            self.state = self.STATE_IDLE
        self.status_text = ""
        self.root.deiconify()
        self._cancel_fade()

    def hide(self):
        self.state = self.STATE_HIDDEN
        self.status_text = ""
        self.root.withdraw()
        self._cancel_fade()

    def set_state(self, state, text=""):
        self.state = state
        self.status_text = text
        if state == self.STATE_HIDDEN:
            self.hide()
        else:
            self.root.deiconify()
            self._cancel_fade()

    def start_fade_timer(self, seconds=6):
        self._cancel_fade()
        self._fade_seconds = seconds
        self._fade_tick()

    def _fade_tick(self):
        if self._fade_seconds <= 0:
            self.hide()
            return
        if self.state == self.STATE_LISTENING:
            return
        self._fade_seconds -= 1
        self._fade_timer = self.root.after(1000, self._fade_tick)

    def _cancel_fade(self):
        if self._fade_timer:
            self.root.after_cancel(self._fade_timer)
            self._fade_timer = None

    def update_volume(self, level):
        self.volume_level = level


# ============================================================================
# CLIENTE DE DICTADO
# ============================================================================

class TeoigoClient:
    def __init__(self, overlay: PillOverlay):
        self.overlay = overlay
        self.is_recording = False
        self.audio_data = []
        self.stream = None
        self._lock = threading.Lock()

    def _run_on_ui_thread(self, fn):
        """Ejecuta una funcion en el hilo principal de Tkinter (thread-safe)."""
        self.overlay.root.after(0, fn)

    def _safe_set_state(self, state, text=""):
        """Actualiza el estado del overlay desde cualquier hilo (thread-safe)."""
        self._run_on_ui_thread(lambda: self.overlay.set_state(state, text))

    def _safe_start_fade(self, seconds=5):
        """Inicia fade timer desde cualquier hilo (thread-safe)."""
        self._run_on_ui_thread(lambda: self.overlay.start_fade_timer(seconds))

    def _safe_update_volume(self, level):
        """Actualiza volumen desde cualquier hilo (thread-safe)."""
        self._run_on_ui_thread(lambda: self.overlay.update_volume(level))

    def toggle_recording(self):
        with self._lock:
            if self.is_recording:
                self._stop_and_transcribe()
            else:
                self._start_recording()

    def _start_recording(self):
        self.audio_data = []
        self.is_recording = True

        def audio_callback(indata, frames, time_info, status):
            self.audio_data.append(indata.copy())
            rms = np.sqrt(np.mean(indata.astype(np.float32) ** 2))
            normalized = min(rms / 4000.0, 1.0)
            self._safe_update_volume(normalized)

        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype='int16',
                callback=audio_callback,
                blocksize=512,
            )
            self.stream.start()
            self._safe_set_state(PillOverlay.STATE_LISTENING)
            log("Grabando... Habla ahora.")
        except Exception as e:
            self.is_recording = False
            log(f"ERROR microfono: {e}")
            self._safe_set_state(PillOverlay.STATE_ERROR, "mic error")
            self._safe_start_fade(5)

    def _inject_text(self, text: str) -> bool:
        """
        Inyecta el texto transcrito en la aplicacion activa donde esta el cursor.
        
        Estrategia (en orden de preferencia):
        1. keyboard.write() — tipado a nivel OS, no depende del foco ni portapapeles
        2. pyautogui.typewrite() — fallback si keyboard falla
        3. pyperclip + Ctrl+V — ultimo recurso
        
        Retorna True si se inyecto correctamente, False en caso contrario.
        """
        if not text or not text.strip():
            return False

        clean_text = text.strip()
        log(f"Inyectando texto ({len(clean_text)} chars) en aplicacion activa...")

        # --- BREVE PAUSA para que la app objetivo recupere el foco ---
        # La ventana overlay (overrideredirect) puede haber perturbado el foco.
        # 300ms es suficiente para que Windows reasigne el foco a la ventana
        # previamente activa antes de que el overlay se mostrara.
        time.sleep(0.35)

        # --- Metodo 1: keyboard.write (nivel OS, mas confiable) ---
        try:
            log("  -> Probando keyboard.write()...")
            keyboard.write(clean_text, delay=0.003)
            log("  -> [OK] Texto inyectado via keyboard.write()")
            return True
        except Exception as e:
            log(f"  -> keyboard.write fallo: {e}")

        # --- Metodo 2: pyautogui.typewrite ---
        try:
            log("  -> Probando pyautogui.typewrite()...")
            pyautogui.typewrite(clean_text, interval=0.003)
            log("  -> [OK] Texto inyectado via pyautogui.typewrite()")
            return True
        except Exception as e:
            log(f"  -> pyautogui.typewrite fallo: {e}")

        # --- Metodo 3: Clipboard + Ctrl+V (ultimo recurso) ---
        try:
            log("  -> Probando clipboard + Ctrl+V...")
            original_clipboard = ""
            try:
                original_clipboard = pyperclip.paste()
            except Exception:
                pass

            pyperclip.copy(clean_text)
            time.sleep(0.15)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.15)

            # Restaurar portapapeles
            try:
                pyperclip.copy(original_clipboard)
            except Exception:
                pass

            log("  -> [OK] Texto inyectado via clipboard + Ctrl+V")
            return True
        except Exception as e:
            log(f"  -> Clipboard + Ctrl+V fallo: {e}")
            return False

    def _stop_and_transcribe(self):
        self.is_recording = False
        log("Deteniendo grabacion...")

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        if not self.audio_data:
            log("No se grabo audio.")
            self._safe_set_state(PillOverlay.STATE_IDLE)
            self._safe_start_fade(4)
            return

        self._safe_set_state(PillOverlay.STATE_PROCESSING, "transcribiendo...")
        self._safe_update_volume(0.0)

        # Concatenar audio
        audio_np = np.concatenate(self.audio_data, axis=0)
        duration = len(audio_np) / SAMPLE_RATE
        log(f"Audio grabado: {duration:.1f} segundos")

        # Convertir a WAV
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_np.tobytes())
        wav_buffer.seek(0)
        wav_size = wav_buffer.getbuffer().nbytes
        log(f"WAV generado: {wav_size / 1024:.0f} KB")

        # Enviar a Whisper
        log(f"Enviando a {WHISPER_URL} ...")
        try:
            response = requests.post(
                WHISPER_URL,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "accept": "application/json",
                },
                files={
                    "audio": ("dictado.wav", wav_buffer, "audio/wav"),
                },
                timeout=120,
                verify=True,
            )

            log(f"Respuesta: HTTP {response.status_code}")

            if response.status_code == 200:
                text = response.json()
                if text and str(text).strip():
                    clean_text = str(text).strip()
                    log(f"TRANSCRITO: \"{clean_text[:100]}\"")

                    # Inyectar texto en la aplicacion activa
                    injected = self._inject_text(clean_text)
                    if injected:
                        self._safe_set_state(PillOverlay.STATE_IDLE)
                        self._safe_start_fade(5)
                    else:
                        log("ERROR: No se pudo inyectar el texto en ninguna aplicacion.")
                        self._safe_set_state(PillOverlay.STATE_ERROR, "no pegado")
                        self._safe_start_fade(5)
                else:
                    log("Whisper no detecto habla en el audio.")
                    self._safe_set_state(PillOverlay.STATE_ERROR, "sin habla")
                    self._safe_start_fade(4)
            elif response.status_code == 401:
                log("ERROR: API KEY invalida!")
                self._safe_set_state(PillOverlay.STATE_ERROR, "api key!")
                self._safe_start_fade(5)
            else:
                log(f"ERROR servidor: {response.status_code} - {response.text[:200]}")
                self._safe_set_state(PillOverlay.STATE_ERROR, f"error {response.status_code}")
                self._safe_start_fade(5)

        except requests.exceptions.SSLError as e:
            log(f"ERROR SSL: {e}")
            # Reintentar sin verificacion SSL (para certificados auto-firmados)
            log("Reintentando sin verificacion SSL...")
            try:
                response = requests.post(
                    WHISPER_URL,
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                        "accept": "application/json",
                    },
                    files={
                        "audio": ("dictado.wav", io.BytesIO(audio_np.tobytes()), "audio/wav"),
                    },
                    timeout=120,
                    verify=False,
                )
                if response.status_code == 200:
                    text = str(response.json()).strip()
                    if text:
                        log(f"TRANSCRITO (SSL skip): \"{text[:80]}\"")
                        injected = self._inject_text(text)
                        if injected:
                            self._safe_set_state(PillOverlay.STATE_IDLE)
                        else:
                            log("ERROR: No se pudo inyectar el texto (SSL path).")
                            self._safe_set_state(PillOverlay.STATE_ERROR, "no pegado")
                        self._safe_start_fade(5)
                        return
            except Exception:
                pass
            self._safe_set_state(PillOverlay.STATE_ERROR, "SSL error")
            self._safe_start_fade(5)

        except requests.exceptions.ConnectionError:
            log("ERROR: No hay conexion a teoigo.alianed.com")
            self._safe_set_state(PillOverlay.STATE_ERROR, "sin conexion")
            self._safe_start_fade(5)
        except requests.exceptions.Timeout:
            log("ERROR: Timeout")
            self._safe_set_state(PillOverlay.STATE_ERROR, "timeout")
            self._safe_start_fade(5)
        except Exception as e:
            log(f"ERROR inesperado: {e}")
            traceback.print_exc()
            self._safe_set_state(PillOverlay.STATE_ERROR, "error")
            self._safe_start_fade(5)


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

def main():
    overlay = PillOverlay()
    client = TeoigoClient(overlay)

    print("=" * 56)
    print("  TEOIGO — Dictado por Voz ALiaNeD")
    print("=" * 56)
    print(f"  Servidor: {WHISPER_URL}")
    print(f"  API Key:  {'*' * max(0,len(API_KEY)-4)}{API_KEY[-4:]}")
    print()
    print("  Ctrl+Flecha Derecha = Dictar")
    print("  Ctrl+Shift+F12     = Salir")
    print("=" * 56)
    print("  [OK] Listo. Esperando tu voz...")
    print()

    def on_hotkey():
        threading.Thread(target=client.toggle_recording, daemon=True).start()

    def on_exit():
        log("Cerrando...")
        overlay.root.quit()
        os._exit(0)

    keyboard.add_hotkey('ctrl+right', on_hotkey, suppress=True)
    keyboard.add_hotkey('ctrl+shift+f12', on_exit, suppress=True)

    # Mostrar brevemente al iniciar
    overlay.show(PillOverlay.STATE_IDLE)
    overlay.start_fade_timer(3)

    overlay.root.mainloop()


if __name__ == "__main__":
    main()
