# -*- coding: utf-8 -*-
"""
TEOIGO — Cliente de Dictado por Voz para Windows v2.1
=====================================================
Herramienta del ecosistema ALiaNeD.

Widget tipo pildora flotante con fondo transparente.
Solo se ven el borde y las ondas reactivas.
Icono personalizado en system tray para control rapido.

Uso:
  Ctrl + Flecha Derecha  = Encender microfono (iniciar dictado)
  Ctrl + Flecha Izquierda = Apagar microfono (detener dictado)
  Ctrl + Shift + F12     = Salir
  Doble-click en icono   = Mostrar/Ocultar pildora
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
import tempfile
import logging

import keyboard
import sounddevice as sd
import numpy as np
import requests
import pyperclip
import pyautogui

import tkinter as tk

# Intentar importar pystray para system tray
try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# ============================================================================
# LOGGING — Archivo + consola (funciona con pythonw tambien)
# ============================================================================
LOG_FILE = os.path.join(tempfile.gettempdir(), "teoigo.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TEOIGO] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("teoigo")

def log(msg):
    logger.info(msg)

# ============================================================================
# MUTEX — Instancia unica (evita 2 pildoras)
# ============================================================================
_mutex_handle = None

def acquire_single_instance():
    """Intenta adquirir un mutex con nombre. Retorna True si es la unica instancia."""
    global _mutex_handle
    try:
        _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, True, "TEOIGO_SINGLE_INSTANCE_MUTEX")
        last_error = ctypes.windll.kernel32.GetLastError()
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            log("OTRA INSTANCIA DE TEOIGO YA ESTA CORRIENDO. Cerrando esta.")
            ctypes.windll.kernel32.CloseHandle(_mutex_handle)
            return False
        return True
    except Exception as e:
        log(f"Error al adquirir mutex: {e}")
        return True  # En caso de error, permitir ejecucion

# ============================================================================
# CONFIGURACION
# ============================================================================
WHISPER_URL = os.getenv(
    "TEOIGO_URL",
    "https://teoigo.alianed.com/v2/transcribe"
)
API_KEY = os.getenv(
    "TEOIGO_API_KEY",
    "DIosesmiVozyEscudoM321"
)

# API Keys de Groq (Predeterminado y Fallback)
GROQ_API_KEY_1 = os.getenv("GROQ_API_KEY", "")
GROQ_API_KEY_2 = os.getenv("GROQ_API_KEY_FALLBACK", "")

SAMPLE_RATE = 16000
CHANNELS = 1
SPEECH_THRESHOLD = 0.025      # Umbral RMS para detectar habla (mas alto para ignorar estatica)
PAUSE_DURATION_SEC = 0.7       # Pausa de 0.7s = fin de frase (estandar industria)
MIN_SPEECH_SEC = 0.3           # Minimo 0.3s de audio con habla para enviar
POLL_INTERVAL_SEC = 0.1        # Frecuencia de revision del VAD

# === Timeouts UX (requeridos por usuario) ===
HIDE_PILL_AFTER_SILENCE_SEC = 180   # 3 min sin hablar -> ocultar pildora (sigue grabando)
AUTO_MINIMIZE_UI_SEC = 300           # 5 min sin uso de UI -> minimizar pildora
AUTO_SHUTDOWN_SEC = 600              # 10 min sin uso -> apagar app entera
ACTIVITY_CHECK_INTERVAL_MS = 15000   # Revisar cada 15s

# Ruta del icono personalizado
ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Icono-Teoigo.png")

# ============================================================================
# COLORES ALiaNeD
# ============================================================================
ALIANED_COLORS = [
    "#ff007f", "#ff2a6d", "#ff5555", "#ff8c00", "#ffbb33", "#aadd00",
    "#40e0d0", "#00bfff", "#0077ff", "#0044ff", "#5533ff", "#8800ff",
]

TRANSPARENT_COLOR = "#010101"

# ============================================================================
# WIN32 — Hacer que la ventana overlay NUNCA robe foco
# ============================================================================
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080

def make_window_no_activate(tk_root):
    """Aplica WS_EX_NOACTIVATE para que la ventana NUNCA robe el foco."""
    try:
        tk_root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(tk_root.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        # NOACTIVATE = no roba foco, TOOLWINDOW = no aparece en taskbar
        new_style = (style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
        log(f"WS_EX_NOACTIVATE aplicado al overlay (hwnd={hwnd})")
    except Exception as e:
        log(f"WARN: No se pudo aplicar WS_EX_NOACTIVATE: {e}")

# ============================================================================
# WIDGET OVERLAY — Pildora transparente con ondas
# ============================================================================
class PillOverlay:
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

        self.root = tk.Tk()
        self.root.title("TEOIGO")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        self.root.configure(bg=TRANSPARENT_COLOR)
        self.root.wm_attributes("-transparentcolor", TRANSPARENT_COLOR)

        # CRITICO: Evitar que la ventana overlay robe el foco
        make_window_no_activate(self.root)

        screen_w = self.root.winfo_screenwidth()
        x_pos = (screen_w - self.WIDTH) // 2
        y_pos = 8
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x_pos}+{y_pos}")

        self.canvas = tk.Canvas(
            self.root, width=self.WIDTH, height=self.HEIGHT,
            bg=TRANSPARENT_COLOR, highlightthickness=0, bd=0,
        )
        self.canvas.pack()

        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_move)

        self.root.withdraw()

        self.bar_colors = []
        for i in range(self.NUM_BARS):
            idx = min(int(i / self.NUM_BARS * len(ALIANED_COLORS)), len(ALIANED_COLORS) - 1)
            self.bar_colors.append(ALIANED_COLORS[idx])

        self.target_heights = [2.0] * self.NUM_BARS
        self.current_heights = [2.0] * self.NUM_BARS
        self._animate()

    def _draw_frame(self):
        self.canvas.delete("all")
        w, h = self.WIDTH, self.HEIGHT
        r = self.CORNER_RADIUS

        if self.state == self.STATE_PROCESSING:
            border_color = "#ffbb33"
        elif self.state == self.STATE_LISTENING:
            border_color = "#ff007f"
        elif self.state == self.STATE_ERROR:
            border_color = "#ff3333"
        else:
            border_color = "#444466"

        # Fondo oscuro semi-opaco (NO usar TRANSPARENT_COLOR aqui,
        # porque eso hace que los clics pasen a traves y no se pueda arrastrar)
        BG_FILL = "#0a0a0a"

        self._draw_rounded_rect(2, 2, w - 2, h - 2, r,
            fill=BG_FILL, outline=border_color, width=2)

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
                x, center_y - half_h, x + bar_width, center_y + half_h,
                fill=color, outline="", width=0,
            )

        if self.status_text:
            self.canvas.create_text(
                w / 2, h / 2, text=self.status_text,
                fill="#ffffff" if self.state != self.STATE_ERROR else "#ff6666",
                font=("Segoe UI", 7, "bold"), anchor="center",
            )

    def _draw_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
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

    def is_visible(self):
        try:
            return self.root.state() != "withdrawn"
        except Exception:
            return False

    def toggle_visibility(self):
        if self.is_visible():
            self.hide()
        else:
            self.show(self.STATE_IDLE)
            self.start_fade_timer(180)


# ============================================================================
# SYSTEM TRAY ICON — Usa el icono personalizado de TEOIGO
# ============================================================================
class TrayIcon:
    """Icono en la barra de tareas.
    Doble-click = mostrar/ocultar pildora.
    Click derecho = menu (Salir).
    Usa el icono personalizado Icono-Teoigo.png.
    """

    def __init__(self, overlay, client, on_exit_callback):
        self.overlay = overlay
        self.client = client
        self.on_exit = on_exit_callback
        self.icon = None
        self._thread = None

        if not HAS_TRAY:
            log("pystray no disponible. Sin icono en system tray.")
            log("Instala con: pip install pystray Pillow")
            return

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _load_icon_image(self):
        """Carga el icono personalizado desde PNG. Si no existe, genera fallback."""
        try:
            if os.path.exists(ICON_PATH):
                img = Image.open(ICON_PATH).convert("RGBA")
                # Redimensionar a tamano adecuado para tray icon
                img = img.resize((64, 64), Image.LANCZOS)
                log(f"Icono personalizado cargado desde {ICON_PATH}")
                return img
        except Exception as e:
            log(f"WARN: No se pudo cargar icono personalizado: {e}")

        # Fallback: icono dibujado a mano
        return self._create_fallback_icon()

    def _create_fallback_icon(self):
        """Crea un icono con forma de microfono como fallback."""
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        color = "#00bfff"
        bg_color = "#111111"

        draw.ellipse([4, 4, 60, 60], fill=bg_color, outline=color, width=2)
        draw.rounded_rectangle([24, 16, 40, 38], radius=8, fill=color)
        draw.arc([16, 20, 48, 46], start=0, end=180, fill=color, width=4)
        draw.line([32, 46, 32, 54], fill=color, width=4)
        draw.line([22, 54, 42, 54], fill=color, width=4)

        return img

    def _run(self):
        try:
            image = self._load_icon_image()
            menu = pystray.Menu(
                pystray.MenuItem("Mostrar/Ocultar Pildora", self._on_toggle, default=True),
                pystray.MenuItem("Dictar (Ctrl+Right)", self._on_dictate),
                pystray.MenuItem("Salir", self._on_exit_click),
            )
            self.icon = pystray.Icon("TEOIGO", image, "TEOIGO - Doble-click para dictar", menu)
            self.icon.run()
        except Exception as e:
            log(f"Error en system tray: {e}")

    def _on_toggle(self, icon, item):
        """Doble-click en tray: muestra/oculta la pildora."""
        self.client.mark_activity()
        self.overlay.toggle_visibility()

    def _on_dictate(self, icon, item):
        """Inicia dictado desde menu."""
        self.client.mark_activity()
        if not self.client.is_recording:
            threading.Thread(target=self.client._start_recording, daemon=True).start()

    def _on_exit_click(self, icon, item):
        """Menu Salir: cierra la aplicacion."""
        if self.icon:
            self.icon.stop()
        self.on_exit()

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass


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
        self._last_sound_time = time.time()
        self._silence_timer = None
        self._streaming_active = False
        self._streaming_thread = None
        self._last_activity_time = time.time()  # Tracker para auto-minimize/shutdown
        self._activity_timer = None

    # --- Thread-safe UI methods ---
    def _run_on_ui(self, fn):
        self.overlay.root.after(0, fn)

    def _safe_set_state(self, state, text=""):
        self._run_on_ui(lambda: self.overlay.set_state(state, text))

    def _safe_start_fade(self, seconds=5):
        self._run_on_ui(lambda: self.overlay.start_fade_timer(seconds))

    def _safe_update_volume(self, level):
        self._run_on_ui(lambda: self.overlay.update_volume(level))

    def _safe_hide(self):
        self._run_on_ui(lambda: self.overlay.hide())

    def _safe_show(self, state=None):
        self._run_on_ui(lambda: self.overlay.show(state))

    def mark_activity(self):
        """Marca que hubo actividad del usuario (hotkey, clic tray, voz)."""
        self._last_activity_time = time.time()

    # --- Recording control ---
    def _start_recording(self):
        """Enciende el microfono (idempotente: si ya graba, no hace nada)."""
        with self._lock:
            if self.is_recording:
                return
            self.is_recording = True

        self.audio_data = []
        self._last_sound_time = time.time()
        self._last_speech_time = time.time()
        self._is_speaking = False
        self._pending_chunk_start = 0
        self.mark_activity()

        def audio_callback(indata, frames, time_info, status):
            if not self.is_recording:
                return
            self.audio_data.append(indata.copy())
            rms = np.sqrt(np.mean(indata.astype(np.float32) ** 2))
            normalized = min(rms / 4000.0, 1.0)
            self._safe_update_volume(normalized)

            # VAD: detectar habla vs silencio
            now = time.time()
            if normalized > SPEECH_THRESHOLD:
                self._last_sound_time = now
                self._last_speech_time = now
                self._last_activity_time = now  # voz = actividad
                if not self._is_speaking:
                    self._is_speaking = True
                # Re-mostrar pildora si estaba oculta por silencio pero sigue grabando
                if self.is_recording and not self.overlay.is_visible():
                    self._safe_show(PillOverlay.STATE_LISTENING)
            # Si hay silencio prolongado total, marcar no-speaking
            elif now - self._last_speech_time > PAUSE_DURATION_SEC:
                self._is_speaking = False

        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=CHANNELS,
                dtype='int16', callback=audio_callback, blocksize=1024,
            )
            self.stream.start()
            # Mostrar la pildora al empezar a grabar (si estaba oculta)
            self._safe_show(PillOverlay.STATE_LISTENING)
            self._safe_set_state(PillOverlay.STATE_LISTENING)
            log("Grabando... Habla ahora.")

            # Iniciar detector de silencio
            self._start_silence_monitor()

            # Iniciar semi-streaming
            self._streaming_active = True
            self._streaming_thread = threading.Thread(
                target=self._streaming_loop, daemon=True
            )
            self._streaming_thread.start()

        except Exception as e:
            self.is_recording = False
            log(f"ERROR microfono: {e}")
            self._safe_set_state(PillOverlay.STATE_ERROR, "mic error")
            self._safe_start_fade(5)

    def _stop_and_transcribe(self):
        """Apaga el microfono (idempotente: si no graba, no hace nada)."""
        with self._lock:
            if not self.is_recording:
                return
            self.is_recording = False
        self.mark_activity()

        # Detener streaming y silencio
        self._streaming_active = False
        self._run_on_ui(self._stop_silence_monitor)

        log("Deteniendo grabacion...")

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        if not self.audio_data:
            log("No se grabo audio.")
            self._safe_set_state(PillOverlay.STATE_IDLE)
            self._safe_start_fade(3)
            return

        self._safe_set_state(PillOverlay.STATE_PROCESSING, "finalizando...")

        # El streaming ya envio chunks parciales.
        # Aqui enviamos SOLO lo que quede sin procesar (si hay).
        # Para simplificar, mostramos estado final.
        self._safe_set_state(PillOverlay.STATE_IDLE)
        self._safe_start_fade(3)  # 3s y se oculta sola tras finalizar
        log("Grabacion finalizada. Texto ya inyectado via streaming.")

    def _start_silence_monitor(self):
        """Monitorea silencio durante grabacion.
        Si pasan HIDE_PILL_AFTER_SILENCE_SEC sin habla -> oculta la pildora
        pero la grabacion sigue activa (no detiene transcripcion).
        """
        def check_silence():
            if not self.is_recording:
                return
            elapsed = time.time() - self._last_sound_time
            if elapsed >= HIDE_PILL_AFTER_SILENCE_SEC:
                log(f"Silencio detectado ({HIDE_PILL_AFTER_SILENCE_SEC}s). Ocultando pildora (grabacion sigue activa).")
                self._safe_hide()
                # No detener grabacion — solo ocultar UI
                return
            # Revisar cada 2 segundos
            self._silence_timer = self.overlay.root.after(2000, check_silence)

        self._silence_timer = self.overlay.root.after(2000, check_silence)

    def _stop_silence_monitor(self):
        if self._silence_timer:
            try:
                self.overlay.root.after_cancel(self._silence_timer)
            except Exception:
                pass
            self._silence_timer = None

    def start_activity_monitor(self):
        """Monitorea inactividad para auto-minimizar y auto-shutdown."""
        def check():
            try:
                now = time.time()
                idle = now - self._last_activity_time

                # 1) Auto-minimizar pildora si esta visible y sin grabar
                if (not self.is_recording
                        and self.overlay.is_visible()
                        and idle >= AUTO_MINIMIZE_UI_SEC):
                    log(f"Auto-minimize: {idle:.0f}s sin actividad de UI")
                    self._safe_hide()

                # 2) Auto-shutdown completo
                if (not self.is_recording
                        and idle >= AUTO_SHUTDOWN_SEC):
                    log(f"Auto-shutdown: {idle:.0f}s sin uso. Cerrando TEOIGO.")
                    if hasattr(main, '_tray') and main._tray:
                        main._tray.stop()
                    self.overlay.root.quit()
                    os._exit(0)
            except Exception as e:
                log(f"activity_monitor error: {e}")

            self._activity_timer = self.overlay.root.after(
                ACTIVITY_CHECK_INTERVAL_MS, check
            )

        self._activity_timer = self.overlay.root.after(
            ACTIVITY_CHECK_INTERVAL_MS, check
        )

    # --- VAD Streaming: enviar cuando detecta pausa en el habla ---
    def _streaming_loop(self):
        """Envia audio al detectar pausa en el habla (estilo industria).

        En vez de timer fijo, monitorea el VAD:
        - Cuando detecta habla, acumula audio
        - Cuando detecta pausa de ~0.7s, envia el chunk acumulado
        - Resultado: texto aparece al terminar cada frase naturalmente
        """
        last_chunk_index = 0
        was_speaking = False

        while self._streaming_active and self.is_recording:
            time.sleep(POLL_INTERVAL_SEC)
            if not self.is_recording or not self._streaming_active:
                break

            current_len = len(self.audio_data)
            if current_len <= last_chunk_index:
                continue

            # Logica VAD: enviar cuando termina una frase
            # (estaba hablando Y ahora hay pausa)
            now_speaking = self._is_speaking
            should_send = False

            if was_speaking and not now_speaking:
                # Pausa detectada despues de habla = fin de frase
                should_send = True

            was_speaking = now_speaking

            if not should_send:
                # Fallback de seguridad: si la frase dura mas de 4 segundos,
                # enviar de todos modos para que el texto aparezca fluido
                # incluso si hay ruido de fondo constante.
                chunk_duration_temp = (current_len - last_chunk_index) * 1024 / SAMPLE_RATE
                if chunk_duration_temp >= 4.0:
                    should_send = True

            if not should_send:
                continue

            # Tomar todo el audio desde el ultimo envio
            chunk_data = self.audio_data[last_chunk_index:current_len]
            last_chunk_index = current_len

            if not chunk_data:
                continue

            chunk_np = np.concatenate(chunk_data, axis=0)
            chunk_duration = len(chunk_np) / SAMPLE_RATE
            if chunk_duration < MIN_SPEECH_SEC:
                continue

            # Transcribir y enviar
            try:
                text = self._transcribe_audio(chunk_np)
                if text and text.strip():
                    log(f"[VAD] Frase ({chunk_duration:.1f}s): \"{text.strip()[:80]}\"")
                    self._inject_text_safe(text.strip())
            except Exception as e:
                log(f"[VAD] Error: {e}")

    def _transcribe_audio(self, audio_np):
        """Envia audio a Groq (predeterminado) o al servidor de respaldo y retorna el texto."""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_np.tobytes())

        # Intentar Groq con las claves configuradas
        groq_keys = [k for k in [GROQ_API_KEY_1, GROQ_API_KEY_2] if k]
        for idx, groq_key in enumerate(groq_keys, start=1):
            try:
                wav_buffer.seek(0)
                groq_response = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    files={"file": ("dictado.wav", wav_buffer, "audio/wav")},
                    data={"model": "whisper-large-v3-turbo"},
                    timeout=5,
                )
                if groq_response.status_code == 200:
                    result = groq_response.json()
                    text = result.get("text", "").strip()
                    if text:
                        return text
                else:
                    log(f"Groq Key {idx} fallo ({groq_response.status_code}): {groq_response.text[:100]}.")
            except Exception as e:
                log(f"Error conectando a Groq API con Key {idx}: {e}.")
                
        if groq_keys:
            log("Todas las claves de Groq fallaron. Usando servidor local de respaldo...")

        # Fallback al servidor Faster-Whisper
        wav_buffer.seek(0)
        try:
            response = requests.post(
                WHISPER_URL,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "accept": "application/json",
                },
                files={"audio": ("dictado.wav", wav_buffer, "audio/wav")},
                timeout=30,
            )

            if response.status_code == 200:
                result = response.json()
                if isinstance(result, str):
                    return result.strip()
                elif isinstance(result, dict):
                    return str(result.get("response", result.get("text", ""))).strip()
                else:
                    return str(result).strip()
            elif response.status_code == 401:
                log("ERROR: API KEY invalida!")
                return None
            else:
                log(f"ERROR servidor: {response.status_code}")
                return None
        except Exception as e:
            log(f"ERROR de conexion con servidor: {e}")
            return None

    def _inject_text_safe(self, text):
        """Inyecta texto en la ventana que tenga el foco (NO manipula foco).

        La pildora tiene WS_EX_NOACTIVATE, asi que NUNCA roba el foco.
        keyboard.write() envia keystrokes via SendInput a la ventana activa.
        El texto va directamente a Word, Notepad, VS Code, etc.
        """
        if not text:
            return

        # Filtrar alucinaciones comunes de Whisper (ruido blanco / silencio)
        lower_text = text.strip().lower()
        alucinaciones = [
            "gracias", "gracias.", "gracias!", "gracias...", "muchas gracias.", "muchas gracias",
            "thank you.", "thank you", "suscribete", "subtitulos por la comunidad de amara.org",
            "gracias por ver el video.", "gracias por ver el video", "gracias por ver el video.", "gracias por ver el video",
            "gracias por ver.", "suscribete al canal", "suscribete al canal.", "suscribanse al canal",
            "i'm so tired", "i'm so tired.", "i am so tired", "i am so tired.", "i'm so tired.",
            "ご視聴ありがとうございました。", "ご視聴ありがとうございました"
        ]

        # Verificar coincidencias exactas
        if lower_text in alucinaciones:
            log(f"Ruido filtrado (alucinacion de Whisper): '{text}'")
            return

        # Filtrar si la frase es solo repeticiones (ej. "I'm so tired. I'm so tired.")
        for aluc in alucinaciones:
            if len(aluc) > 5 and lower_text.replace(aluc, "").strip() == "":
                log(f"Ruido repetitivo filtrado: '{text}'")
                return

        log(f"Inyectando ({len(text)} chars)...")

        # Agregar espacio al final para separar chunks
        text_with_space = text + " "

        # Metodo 1: clipboard + Ctrl+V (Mejor compatibilidad para Word, Notepad, etc.)
        try:
            original = ""
            try:
                original = pyperclip.paste()
            except Exception:
                pass

            pyperclip.copy(text_with_space)
            time.sleep(0.05)
            # pyautogui aveces necesita un mini delay adicional en Windows
            pyautogui.hotkey('ctrl', 'v')
            # 300ms de delay para apps Electron/Web (como Antigravity) que leen el clipboard asincronamente
            time.sleep(0.3)

            try:
                pyperclip.copy(original)
            except Exception:
                pass

            log("[OK] via clipboard+Ctrl+V")
            return
        except Exception as e:
            log(f"clipboard+Ctrl+V fallo: {e}")

        # Metodo 2: keyboard.write (Fallback a nivel OS)
        try:
            keyboard.write(text_with_space, delay=0.002)
            log("[OK] via keyboard.write()")
            return
        except Exception as e:
            log(f"keyboard.write fallo: {e}")


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================
def main():
    # Verificar instancia unica
    if not acquire_single_instance():
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                "TEOIGO ya esta corriendo.\nRevisa el icono en la barra de tareas.",
                "TEOIGO",
                0x40,  # MB_ICONINFORMATION
            )
        except Exception:
            pass
        sys.exit(0)

    overlay = PillOverlay()
    client = TeoigoClient(overlay)

    print("=" * 56)
    print("  TEOIGO v2.1 — Dictado por Voz ALiaNeD")
    print("=" * 56)
    print(f"  Servidor: {WHISPER_URL}")
    print(f"  API Key:  {'*' * max(0,len(API_KEY)-4)}{API_KEY[-4:]}")
    print(f"  Log:      {LOG_FILE}")
    print(f"  Tray:     {'SI' if HAS_TRAY else 'NO (pip install pystray Pillow)'}")
    print()
    print("  Ctrl+Flecha Derecha  = Encender microfono")
    print("  Ctrl+Flecha Izquierda = Apagar microfono")
    print("  Ctrl+Shift+F12       = Salir")
    print(f"  Ocultar por silencio = {HIDE_PILL_AFTER_SILENCE_SEC}s")
    print(f"  Auto-minimize UI     = {AUTO_MINIMIZE_UI_SEC}s")
    print(f"  Auto-shutdown        = {AUTO_SHUTDOWN_SEC}s")
    print("=" * 56)
    print("  [OK] Listo. Esperando tu voz...")
    print("  (Doble-click en icono de tray o Ctrl+Right para dictar)")
    print()

    def on_hotkey_start():
        """Ctrl+Right = encender microfono (idempotente)."""
        client.mark_activity()
        if not client.is_recording:
            threading.Thread(target=client._start_recording, daemon=True).start()

    def on_hotkey_stop():
        """Ctrl+Left = apagar microfono (idempotente)."""
        client.mark_activity()
        if client.is_recording:
            threading.Thread(target=client._stop_and_transcribe, daemon=True).start()

    def on_exit():
        log("Cerrando...")
        if hasattr(main, '_tray') and main._tray:
            main._tray.stop()
        overlay.root.quit()
        os._exit(0)

    # Hotkeys SIN suppress para no robar combinaciones de otras apps
    keyboard.add_hotkey('ctrl+right', on_hotkey_start, suppress=False)
    keyboard.add_hotkey('ctrl+left', on_hotkey_stop, suppress=False)
    keyboard.add_hotkey('ctrl+shift+f12', on_exit, suppress=False)

    # System Tray — doble-click = mostrar/ocultar pildora
    main._tray = TrayIcon(overlay, client, on_exit)

    # Arranque silencioso: TEOIGO queda en bandeja, listo para dictar.
    # El usuario hace doble-click en el icono de bandeja para mostrar la pildora,
    # o presiona Ctrl+Right para empezar a dictar directamente.
    log("TEOIGO listo en bandeja. Ctrl+Right=dictar, Ctrl+Left=parar.")

    # Monitor de inactividad (auto-minimize + auto-shutdown)
    client.start_activity_monitor()

    overlay.root.mainloop()


if __name__ == "__main__":
    main()
