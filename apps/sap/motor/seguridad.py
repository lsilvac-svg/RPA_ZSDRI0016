"""Respuesta automática a la ventana de Windows "Seguridad SAP GUI"."""
import ctypes
import threading

from .windows import pywintypes, win32con, win32gui

TITULO_SEGURIDAD = "Seguridad SAP GUI"


class VigilanteSeguridad(threading.Thread):
    """Responde la ventana "Seguridad SAP GUI" mientras el robot trabaja.

    Esa ventana es de Windows (no de SAP) y bloquea el scripting hasta que
    alguien la responde. Para archivos dentro de las carpetas autorizadas
    marca "Recordar mi decisión" y pulsa "Permitir": SAP guarda la regla y
    no vuelve a preguntar. Cualquier otro acceso se rechaza.

    Uso:
        with VigilanteSeguridad([carpeta], permitir_abrir=True, log=log):
            ...
    """

    def __init__(self, carpetas, permitir_abrir, log):
        super().__init__(daemon=True)
        self._carpetas = [str(c).rstrip("\\/").lower() for c in carpetas if c]
        self._permitir_abrir = permitir_abrir
        self._log = log
        self._fin = threading.Event()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self._fin.set()
        self.join(timeout=5)
        return False

    def run(self):
        while not self._fin.wait(0.5):
            try:
                ventana = win32gui.FindWindow("#32770", TITULO_SEGURIDAD)
                if ventana:
                    self._responder(ventana)
            except pywintypes.error:
                pass  # la ventana se cerró mientras se leía

    def _responder(self, ventana):
        texto, botones = _leer_dialogo(ventana)
        texto_min = texto.lower()
        resumen = " ".join(texto.split())

        es_apertura = "ejecutar" in texto_min or "execute" in texto_min
        en_carpeta = any(c in texto_min for c in self._carpetas)
        autorizado = en_carpeta and (not es_apertura or self._permitir_abrir)

        recordar = _boton(botones, "remember", "recordar")
        permitir = _boton(botones, "allow", "permitir")
        rechazar = _boton(botones, "deny", "rechazar")

        if autorizado and permitir:
            if recordar and win32gui.SendMessage(
                recordar, win32con.BM_GETCHECK, 0, 0
            ) != win32con.BST_CHECKED:
                win32gui.SendMessage(recordar, win32con.BM_CLICK, 0, 0)
            win32gui.SendMessage(permitir, win32con.BM_CLICK, 0, 0)
            self._log.info("Seguridad SAP GUI: permitido -> %s", resumen)
        elif rechazar:
            win32gui.SendMessage(rechazar, win32con.BM_CLICK, 0, 0)
            self._log.warning("Seguridad SAP GUI: rechazado -> %s", resumen)
        self._fin.wait(1)


def _leer_dialogo(ventana):
    texto = ""
    botones = {}

    def recorrer(control, _):
        nonlocal texto
        clase = win32gui.GetClassName(control)
        if clase == "Edit":
            texto = leer_texto_control(control)
        elif clase == "Button":
            botones[win32gui.GetWindowText(control).lower()] = control

    win32gui.EnumChildWindows(ventana, recorrer, None)
    return texto, botones


def _boton(botones, *nombres):
    for etiqueta, control in botones.items():
        if any(n in etiqueta for n in nombres):
            return control
    return None


def leer_texto_control(control):
    # WM_GETTEXT: GetWindowText no lee controles de otro proceso
    largo = win32gui.SendMessage(control, win32con.WM_GETTEXTLENGTH, 0, 0) + 1
    buffer = ctypes.create_unicode_buffer(largo)
    ctypes.windll.user32.SendMessageW(control, win32con.WM_GETTEXT, largo, buffer)
    return buffer.value
