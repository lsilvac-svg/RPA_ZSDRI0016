"""Envoltorio de una sesión de SAP GUI con esperas y validaciones."""
import time

from .errores import ErrorSAP
from .windows import pywintypes

BARRA_ESTADO = "wnd[0]/sbar"
CAMPO_COMANDO = "wnd[0]/tbar[0]/okcd"


class SesionSAP:
    """Operaciones seguras sobre una sesión SAP GUI.

    Cada acceso a un elemento espera a que exista (SAP puede tardar en
    mostrar ventanas) en vez de fallar al primer intento.
    """

    def __init__(self, session, tiempo_espera=30):
        self.com = session
        self.tiempo_espera = tiempo_espera

    # --- Esperas -------------------------------------------------------

    def esperar(self, segundos=None):
        limite = time.monotonic() + (segundos or self.tiempo_espera)
        while self.com.Busy:
            if time.monotonic() > limite:
                raise ErrorSAP("Tiempo de espera agotado: SAP sigue ocupado")
            time.sleep(0.2)

    def existe(self, id_elemento):
        return self.com.findById(id_elemento, False) is not None

    def elemento(self, id_elemento, segundos=None):
        limite = time.monotonic() + (segundos or self.tiempo_espera)
        while True:
            encontrado = self.com.findById(id_elemento, False)
            if encontrado is not None:
                return encontrado
            if time.monotonic() > limite:
                raise ErrorSAP(f"No apareció el elemento SAP '{id_elemento}'")
            time.sleep(0.5)

    # --- Acciones ------------------------------------------------------

    def escribir(self, id_campo, texto):
        self.elemento(id_campo).text = texto

    def leer(self, id_campo):
        return self.elemento(id_campo).text

    def presionar(self, id_boton):
        self.elemento(id_boton).press()

    def seleccionar_menu(self, id_menu):
        self.elemento(id_menu).select()

    def tecla(self, codigo, ventana="wnd[0]"):
        """Envía una tecla virtual (0 = Enter, 8 = F8, 12 = Cancelar)."""
        self.elemento(ventana).sendVKey(codigo)

    def comando(self, texto):
        """Escribe en el campo de comandos (p. ej. '/nVA03') y pulsa Enter."""
        self.escribir(CAMPO_COMANDO, texto)
        self.tecla(0)
        self.esperar()

    def maximizar(self):
        self.elemento("wnd[0]").maximize()

    # --- Lectura de estado ---------------------------------------------

    def barra_estado(self):
        """(tipo, texto) del mensaje actual: tipo S, I, W, E o A."""
        barra = self.com.findById(BARRA_ESTADO)
        return barra.MessageType, barra.Text

    def verificar_barra_estado(self):
        tipo, texto = self.barra_estado()
        if tipo in ("E", "A"):
            raise ErrorSAP(f"SAP respondió: {texto}")

    def texto_ventana(self, ventana="wnd[1]"):
        """Título y textos de una ventana emergente, para el log."""
        wnd = self.com.findById(ventana, False)
        if wnd is None:
            return ""

        textos = [wnd.Text]
        usr = self.com.findById(f"{ventana}/usr", False)
        if usr is not None:
            for i in range(usr.Children.Count):
                texto = getattr(usr.Children.ElementAt(i), "Text", "")
                if texto and texto.strip():
                    textos.append(texto.strip())
        return " | ".join(textos)

    @property
    def usuario(self):
        return self.com.Info.User

    @property
    def sistema(self):
        return self.com.Info.SystemName

    def captura(self, ruta):
        """Guarda una imagen PNG de la ventana activa. Devuelve True si pudo."""
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            self.com.ActiveWindow.HardCopy(str(ruta), 2)
            return True
        except (pywintypes.com_error, AttributeError):
            return False
