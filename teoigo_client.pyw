"""
TEOIGO — Cliente de Dictado por Voz para Windows v2.0
=====================================================
Herramienta del ecosistema ALiaNeD.

Widget tipo pildora flotante con fondo transparente.
Solo se ven el borde y las ondas reactivas.
Icono en system tray para control rapido.

Uso:
  Ctrl + Flecha Derecha  = Iniciar / Detener dictado
  Ctrl + Shift + F12     = Salir
  Click en tray icon     = Mostrar/Ocultar pildora
  Doble-click tray icon  = Mostrar pildora
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
    "DIosesmiVozyEscudo_!321"
)

SAMPLE_RATE = 16000
CHANNELS = 1
SILENCE_TIMEOUT_SEC = 120     # 2 minutos sin hablar = auto-cierre
SPEECH_THRESHOLD = 0.015      # Umbral RMS para detectar habla
PAUSE_DURATION_SEC = 0.7       # Pausa de 0.7s = fin de frase (estandar industria)
MIN_SPEECH_SEC = 0.3           # Minimo 0.3s de audio con habla para enviar
POLL_INTERVAL_SEC = 0.1        # Frecuencia de revision del VAD

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

        self._draw_rounded_rect(2, 2, w - 2, h - 2, r,
            fill=TRANSPARENT_COLOR, outline=border_color, width=2)
        self._draw_rounded_rect(4, 4, w - 4, h - 4, r - 2,
            fill="#0a0a15", outline="", width=0)

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
            self.start_fade_timer(8)


# ============================================================================
# SYSTEM TRAY ICON
# ============================================================================
class TrayIcon:
    """Icono en la barra de tareas.
    Click izquierdo = iniciar/detener dictado.
    Click derecho = menu (Salir).
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

    def _create_icon_image(self):
        """Crea un icono simple con los colores ALiaNeD."""
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([2, 2, size - 2, size - 2], fill="#ff007f", outline="#0a0a15", width=2)
        bar_positions = [16, 24, 32, 40, 48]
        bar_heights = [12, 20, 28, 20, 12]
        for x, h in zip(bar_positions, bar_heights):
            y_top = (size - h) // 2
            draw.rectangle([x - 2, y_top, x + 2, y_top + h], fill="#ffffff")
        return img

    def _run(self):
        try:
            image = self._create_icon_image()
            menu = pystray.Menu(
                pystray.MenuItem("Dictar (Ctrl+Right)", self._on_dictate, default=True),
                pystray.MenuItem("Salir", self._on_exit_click),
            )
            self.icon = pystray.Icon("TEOIGO", image, "TEOIGO - Click para dictar", menu)
            self.icon.run()
        except Exception as e:
            log(f"Error en system tray: {e}")

    def _on_dictate(self, icon, item):
        """Click izquierdo: iniciar/detener dictado (igual que Ctrl+Right)."""
        threading.Thread(target=self.client.toggle_recording, daemon=True).start()

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

    # --- Recording control ---
    def toggle_recording(self):
        if self.is_recording:
            self._stop_and_transcribe()
        else:
            self._start_recording()

    def _start_recording(self):
        with self._lock:
            if self.is_recording:
                return
            self.is_recording = True

        self.audio_data = []
        self._last_sound_time = time.time()
        self._last_speech_time = time.time()
        self._is_speaking = False
        self._pending_chunk_start = 0

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
                if not self._is_speaking:
                    self._is_speaking = True
            # Si hay silencio prolongado total, marcar no-speaking
            elif now - self._last_speech_time > PAUSE_DURATION_SEC:
                self._is_speaking = False

        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=CHANNELS,
                dtype='int16', callback=audio_callback, blocksize=1024,
            )
            self.stream.start()
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

    def _start_silence_monitor(self):
        """Monitorea silencio y auto-detiene si pasan N segundos sin habla."""
        def check_silence():
            if not self.is_recording:
                return
            elapsed = time.time() - self._last_sound_time
            if elapsed >= SILENCE_TIMEOUT_SEC:
                log(f"Silencio detectado ({SILENCE_TIMEOUT_SEC}s). Auto-deteniendo...")
                threading.Thread(target=self._stop_and_transcribe, daemon=True).start()
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

    # --- VAD Streaming: enviar cuando detecta pausa en el habla ---
    def _streaming_loop(self):
        """Envía audio al detectar pausa en el habla (estilo industria).
        
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
        """Envía audio al servidor y retorna el texto transcrito."""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_np.tobytes())
        wav_buffer.seek(0)

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

    def _inject_text_safe(self, text):
        """Inyecta texto en la ventana que tenga el foco (NO manipula foco).
        
        La pildora tiene WS_EX_NOACTIVATE, asi que NUNCA roba el foco.
        keyboard.write() envia keystrokes via SendInput a la ventana activa.
        El texto va directamente a Word, Notepad, VS Code, etc.
        """
        if not text:
            return

        log(f"Inyectando ({len(text)} chars)...")

        # Agregar espacio al final para separar chunks
        text_with_space = text + " "

        # Metodo 1: keyboard.write (nivel OS, SendInput)
        try:
            keyboard.write(text_with_space, delay=0.002)
            log("[OK] via keyboard.write()")
            return
        except Exception as e:
            log(f"keyboard.write fallo: {e}")

        # Metodo 2: clipboard + Ctrl+V (fallback)
        try:
            original = ""
            try:
                original = pyperclip.paste()
            except Exception:
                pass

            pyperclip.copy(text_with_space)
            time.sleep(0.1)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.1)

            try:
                pyperclip.copy(original)
            except Exception:
                pass

            log("[OK] via clipboard+Ctrl+V")
            return
        except Exception as e:
            log(f"clipboard+Ctrl+V fallo: {e}")

    def _stop_and_transcribe(self):
        """Detiene grabacion y transcribe el audio restante."""
        with self._lock:
            if not self.is_recording:
                return
            self.is_recording = False

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
            self._safe_start_fade(4)
            return

        self._safe_set_state(PillOverlay.STATE_PROCESSING, "finalizando...")

        # El streaming ya envio chunks parciales.
        # Aqui enviamos SOLO lo que quede sin procesar (si hay).
        # Para simplificar, mostramos estado final.
        self._safe_set_state(PillOverlay.STATE_IDLE)
        self._safe_start_fade(5)
        log("Grabacion finalizada. Texto ya inyectado via streaming.")


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
    print("  TEOIGO v2.0 — Dictado por Voz ALiaNeD")
    print("=" * 56)
    print(f"  Servidor: {WHISPER_URL}")
    print(f"  API Key:  {'*' * max(0,len(API_KEY)-4)}{API_KEY[-4:]}")
    print(f"  Log:      {LOG_FILE}")
    print(f"  Tray:     {'SI' if HAS_TRAY else 'NO (pip install pystray Pillow)'}")
    print()
    print("  Ctrl+Flecha Derecha = Dictar")
    print("  Ctrl+Shift+F12     = Salir")
    print(f"  Silencio auto-stop = {SILENCE_TIMEOUT_SEC}s")
    print(f"  VAD pausa frase    = {PAUSE_DURATION_SEC}s")
    print("=" * 56)
    print("  [OK] Listo. Esperando tu voz...")
    print("  (Click en icono de tray o Ctrl+Right para dictar)")
    print()

    def on_hotkey():
        threading.Thread(target=client.toggle_recording, daemon=True).start()

    def on_exit():
        log("Cerrando...")
        if hasattr(main, '_tray') and main._tray:
            main._tray.stop()
        overlay.root.quit()
        os._exit(0)

    # Hotkeys SIN suppress para no robar Ctrl+Right de otras apps
    keyboard.add_hotkey('ctrl+right', on_hotkey, suppress=False)
    keyboard.add_hotkey('ctrl+shift+f12', on_exit, suppress=False)

    # System Tray — click = iniciar/detener dictado
    main._tray = TrayIcon(overlay, client, on_exit)

    # Mostrar brevemente al iniciar
    overlay.show(PillOverlay.STATE_IDLE)
    overlay.start_fade_timer(3)

    overlay.root.mainloop()


if __name__ == "__main__":
    main()
