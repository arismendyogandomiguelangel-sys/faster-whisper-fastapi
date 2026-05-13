"""
TEOIGO — Cliente de Dictado por Voz para Windows
=================================================
Herramienta del ecosistema ALiaNeD.

Widget visual tipo "pildora" flotante, semitransparente y arrastrable.
Las ondas reaccionan en tiempo real a tu voz.

Uso:
  1. Doble clic en este archivo (o: python teoigo_client.pyw)
  2. Presiona Ctrl + Flecha Derecha para activar/desactivar
  3. Habla y el texto se pega donde esta tu cursor
  4. Ctrl + Shift + F12 para salir

Requisitos:
  pip install -r client_requirements.txt
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

import keyboard
import sounddevice as sd
import numpy as np
import requests
import pyperclip
import pyautogui

# Tkinter para el overlay visual
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
    "CHANGE_ME_PUT_YOUR_API_KEY_HERE"
)

SAMPLE_RATE = 16000
CHANNELS = 1

# ============================================================================
# COLORES ALiaNeD
# ============================================================================
ALIANED_COLORS = [
    "#ff007f",  # Rosa fuerte
    "#ff2a6d",
    "#ff5555",
    "#ff8c00",  # Naranja
    "#ffbb33",
    "#aadd00",
    "#40e0d0",  # Turquesa
    "#00bfff",
    "#0077ff",
    "#0044ff",  # Azul profundo
    "#5533ff",
    "#8800ff",  # Violeta
]

# Color que se marcara como transparente (un negro muy especifico)
TRANSPARENT_COLOR = "#010101"

# ============================================================================
# WIDGET OVERLAY (Pildora flotante con ondas)
# ============================================================================

class PillOverlay:
    """
    Overlay tipo pildora semitransparente con ondas reactivas.
    - Siempre encima de todas las ventanas
    - Arrastrable
    - Ondas que reaccionan al volumen del microfono
    """

    # Dimensiones de la pildora
    WIDTH = 220
    HEIGHT = 52
    CORNER_RADIUS = 26
    NUM_BARS = 28

    # Estados visuales
    STATE_HIDDEN = "hidden"
    STATE_IDLE = "idle"         # Visible pero sin hablar
    STATE_LISTENING = "listening"  # Grabando, ondas activas
    STATE_PROCESSING = "processing"  # Enviando a Whisper

    def __init__(self):
        self.state = self.STATE_HIDDEN
        self.volume_level = 0.0  # 0.0 a 1.0
        self.drag_data = {"x": 0, "y": 0}
        self._fade_timer = None
        self._fade_seconds = 0

        # --- Crear ventana ---
        self.root = tk.Tk()
        self.root.title("TEOIGO")
        self.root.overrideredirect(True)  # Sin barra de titulo
        self.root.attributes("-topmost", True)  # Siempre encima
        self.root.attributes("-alpha", 0.92)  # Ligera transparencia global
        self.root.configure(bg=TRANSPARENT_COLOR)
        self.root.wm_attributes("-transparentcolor", TRANSPARENT_COLOR)

        # Posicionar arriba-centro de la pantalla
        screen_w = self.root.winfo_screenwidth()
        x_pos = (screen_w - self.WIDTH) // 2
        y_pos = 12
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x_pos}+{y_pos}")

        # --- Canvas para dibujar ---
        self.canvas = tk.Canvas(
            self.root,
            width=self.WIDTH,
            height=self.HEIGHT,
            bg=TRANSPARENT_COLOR,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack()

        # --- Eventos de arrastre ---
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_move)

        # Estado inicial: oculto
        self.root.withdraw()

        # Precalcular colores de las barras (gradiente ALiaNeD)
        self.bar_colors = []
        for i in range(self.NUM_BARS):
            idx = int(i / self.NUM_BARS * len(ALIANED_COLORS))
            idx = min(idx, len(ALIANED_COLORS) - 1)
            self.bar_colors.append(ALIANED_COLORS[idx])

        # Alturas objetivo y actuales para animacion suave
        self.target_heights = [2.0] * self.NUM_BARS
        self.current_heights = [2.0] * self.NUM_BARS

        # Iniciar loop de animacion
        self._animate()

    # ------------------------------------------------------------------
    # DIBUJO
    # ------------------------------------------------------------------

    def _draw_frame(self):
        """Redibuja un frame completo del overlay."""
        self.canvas.delete("all")

        w, h = self.WIDTH, self.HEIGHT
        r = self.CORNER_RADIUS

        # --- Fondo de pildora con bordes redondeados ---
        if self.state == self.STATE_PROCESSING:
            bg_fill = "#1a1a2e"
            bg_outline = "#ffbb33"
        elif self.state == self.STATE_LISTENING:
            bg_fill = "#0d0d1a"
            bg_outline = "#ff007f"
        else:
            bg_fill = "#1a1a2e"
            bg_outline = "#333355"

        # Dibujar pildora (rectangulo redondeado)
        self._draw_rounded_rect(2, 2, w - 2, h - 2, r, fill=bg_fill, outline=bg_outline, width=1.5)

        # --- Barras de audio ---
        bar_area_x = 10
        bar_area_w = w - 20
        bar_spacing = bar_area_w / self.NUM_BARS
        bar_width = max(3, bar_spacing - 2)
        max_bar_h = h - 16

        center_y = h / 2

        for i in range(self.NUM_BARS):
            bh = self.current_heights[i]
            x = bar_area_x + i * bar_spacing + (bar_spacing - bar_width) / 2
            half_h = bh / 2

            color = self.bar_colors[i]

            if self.state == self.STATE_IDLE:
                color = self._dim_color(color, 0.3)
            elif self.state == self.STATE_PROCESSING:
                color = self._dim_color(color, 0.6)

            self.canvas.create_rectangle(
                x, center_y - half_h,
                x + bar_width, center_y + half_h,
                fill=color,
                outline="",
                width=0,
            )

        # --- Indicador de estado ---
        if self.state == self.STATE_PROCESSING:
            self.canvas.create_text(
                w / 2, h / 2,
                text="transcribiendo...",
                fill="#ffbb33",
                font=("Segoe UI", 7, "bold"),
                anchor="center",
            )

    def _draw_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        """Dibuja un rectangulo con esquinas redondeadas en el canvas."""
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1, x2, y1 + r,
            x2, y2 - r,
            x2, y2, x2 - r, y2,
            x1 + r, y2,
            x1, y2, x1, y2 - r,
            x1, y1 + r,
            x1, y1, x1 + r, y1,
        ]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    @staticmethod
    def _dim_color(hex_color, factor):
        """Oscurece un color hex por un factor (0.0 = negro, 1.0 = original)."""
        hex_color = hex_color.lstrip("#")
        r = int(int(hex_color[0:2], 16) * factor)
        g = int(int(hex_color[2:4], 16) * factor)
        b = int(int(hex_color[4:6], 16) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"

    # ------------------------------------------------------------------
    # ANIMACION
    # ------------------------------------------------------------------

    def _animate(self):
        """Loop de animacion a ~30 FPS."""
        self._update_heights()
        self._draw_frame()
        self.root.after(33, self._animate)

    def _update_heights(self):
        """Actualiza las alturas de las barras suavemente."""
        max_h = self.HEIGHT - 16

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
                self.target_heights[i] = 4 + wave_val * max_h * 0.35

        elif self.state == self.STATE_IDLE:
            t = time.time() * 1.5
            for i in range(self.NUM_BARS):
                breath = math.sin(t + i * 0.2) * 1.5 + 3
                self.target_heights[i] = breath

        else:
            for i in range(self.NUM_BARS):
                self.target_heights[i] = 2.0

        # Interpolar suavemente
        ease = 0.25
        for i in range(self.NUM_BARS):
            self.current_heights[i] += (self.target_heights[i] - self.current_heights[i]) * ease

    # ------------------------------------------------------------------
    # ARRASTRE
    # ------------------------------------------------------------------

    def _on_drag_start(self, event):
        self.drag_data["x"] = event.x
        self.drag_data["y"] = event.y

    def _on_drag_move(self, event):
        dx = event.x - self.drag_data["x"]
        dy = event.y - self.drag_data["y"]
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------
    # CONTROL DE ESTADO
    # ------------------------------------------------------------------

    def show(self, state=None):
        if state:
            self.state = state
        elif self.state == self.STATE_HIDDEN:
            self.state = self.STATE_IDLE
        self.root.deiconify()
        self._cancel_fade()

    def hide(self):
        self.state = self.STATE_HIDDEN
        self.root.withdraw()
        self._cancel_fade()

    def set_state(self, state):
        self.state = state
        if state == self.STATE_HIDDEN:
            self.hide()
        else:
            self.show()

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
        if level > 0.05 and self.state == self.STATE_IDLE:
            self._cancel_fade()


# ============================================================================
# CLIENTE DE DICTADO
# ============================================================================

class TeoigoClient:
    """Cliente de dictado que graba, envia a Whisper y pega el texto."""

    def __init__(self, overlay: PillOverlay):
        self.overlay = overlay
        self.is_recording = False
        self.audio_data = []
        self.stream = None
        self._lock = threading.Lock()

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
            self.overlay.update_volume(normalized)

        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype='int16',
                callback=audio_callback,
                blocksize=512,
            )
            self.stream.start()
            self.overlay.set_state(PillOverlay.STATE_LISTENING)
        except Exception as e:
            self.is_recording = False
            print(f"[TEOIGO] Error microfono: {e}")

    def _stop_and_transcribe(self):
        self.is_recording = False

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        if not self.audio_data:
            self.overlay.set_state(PillOverlay.STATE_IDLE)
            self.overlay.start_fade_timer(4)
            return

        self.overlay.set_state(PillOverlay.STATE_PROCESSING)
        self.overlay.update_volume(0.0)

        audio_np = np.concatenate(self.audio_data, axis=0)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_np.tobytes())
        wav_buffer.seek(0)

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
                timeout=60,
            )

            if response.status_code == 200:
                text = response.json()
                if text and text.strip():
                    original_clipboard = ""
                    try:
                        original_clipboard = pyperclip.paste()
                    except Exception:
                        pass

                    pyperclip.copy(text.strip())
                    time.sleep(0.05)
                    pyautogui.hotkey('ctrl', 'v')
                    time.sleep(0.1)

                    try:
                        pyperclip.copy(original_clipboard)
                    except Exception:
                        pass

                    print(f"[TEOIGO] Transcrito: {text.strip()[:80]}")
                else:
                    print("[TEOIGO] No se detecto habla.")
            elif response.status_code == 401:
                print("[TEOIGO] ERROR: API KEY invalida.")
            else:
                print(f"[TEOIGO] Error servidor: {response.status_code}")
        except requests.exceptions.ConnectionError:
            print("[TEOIGO] ERROR: No hay conexion a teoigo.alianed.com")
        except requests.exceptions.Timeout:
            print("[TEOIGO] ERROR: Timeout del servidor")
        except Exception as e:
            print(f"[TEOIGO] Error: {e}")

        self.overlay.set_state(PillOverlay.STATE_IDLE)
        self.overlay.start_fade_timer(6)


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

def main():
    overlay = PillOverlay()
    client = TeoigoClient(overlay)

    print("=" * 60)
    print("  TEOIGO \u2014 Dictado por Voz ALiaNeD")
    print("=" * 60)
    print(f"  Servidor:  {WHISPER_URL}")
    print(f"  API Key:   {'*' * max(0, len(API_KEY) - 4)}{API_KEY[-4:]}")
    print()
    print("  Ctrl + Flecha Derecha  =  Iniciar / Detener dictado")
    print("  Ctrl + Shift + F12    =  Cerrar TEOIGO")
    print("=" * 60)
    print("  [Listo] Esperando tu voz...")
    print()

    def on_hotkey():
        threading.Thread(target=client.toggle_recording, daemon=True).start()

    def on_exit():
        print("[TEOIGO] Cerrando...")
        overlay.root.quit()
        os._exit(0)

    keyboard.add_hotkey('ctrl+right', on_hotkey, suppress=True)
    keyboard.add_hotkey('ctrl+shift+f12', on_exit, suppress=True)

    overlay.show(PillOverlay.STATE_IDLE)
    overlay.start_fade_timer(4)

    overlay.root.mainloop()


if __name__ == "__main__":
    main()
