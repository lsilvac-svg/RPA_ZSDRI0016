"""Declaración de parámetros configurables de un robot.

Cada robot declara sus parámetros y la interfaz genera los formularios a
partir de ellos: agregar un parámetro no requiere tocar plantillas.
"""
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any

from django import forms


class Tipo(str, Enum):
    TEXTO = "texto"
    ENTERO = "entero"
    BOOLEANO = "booleano"
    FECHA = "fecha"
    CARPETA = "carpeta"
    OPCION = "opcion"


@dataclass(frozen=True)
class Parametro:
    nombre: str
    etiqueta: str
    tipo: Tipo = Tipo.TEXTO
    defecto: Any = None
    requerido: bool = False
    ayuda: str = ""
    minimo: int | None = None
    # Solo Tipo.OPCION: ((valor, texto), ...)
    opciones: tuple = ()

    def texto(self, valor):
        """Valor legible para mostrar en pantallas (p. ej. el texto de una opción)."""
        if self.tipo == Tipo.OPCION:
            return dict(self.opciones).get(valor, valor)
        return valor

    def campo(self):
        comunes = {
            "label": self.etiqueta,
            "required": self.requerido,
            "help_text": self.ayuda,
        }
        match self.tipo:
            case Tipo.ENTERO:
                return forms.IntegerField(min_value=self.minimo, **comunes)
            case Tipo.BOOLEANO:
                return forms.BooleanField(**{**comunes, "required": False})
            case Tipo.FECHA:
                return forms.DateField(
                    widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                    **comunes,
                )
            case Tipo.OPCION:
                return forms.ChoiceField(choices=self.opciones, **comunes)
            case _:
                return forms.CharField(max_length=255, **comunes)

    def a_json(self, valor):
        if isinstance(valor, date):
            return valor.isoformat()
        if self.tipo == Tipo.TEXTO and isinstance(valor, str):
            return valor.strip()
        return valor

    def desde_json(self, valor):
        if valor in (None, ""):
            return self.defecto
        if self.tipo == Tipo.FECHA and isinstance(valor, str):
            return date.fromisoformat(valor)
        if self.tipo == Tipo.ENTERO:
            return int(valor)
        return valor


def construir_formulario(parametros, *, data=None, valores=None, prefix=None):
    """Formulario Django con un campo por parámetro."""
    from apps.core.forms import BootstrapFormMixin

    campos = {p.nombre: p.campo() for p in parametros}
    clase = type("FormularioParametros", (BootstrapFormMixin, forms.Form), campos)
    inicial = {p.nombre: p.desde_json((valores or {}).get(p.nombre)) for p in parametros}
    return clase(data=data, initial=inicial, prefix=prefix)


def serializar(parametros, datos_limpios):
    return {p.nombre: p.a_json(datos_limpios.get(p.nombre)) for p in parametros}


def legibles(parametros, guardados, vacio="Por defecto"):
    """[(etiqueta, texto)] de los valores guardados, para mostrar en pantallas."""
    filas = []
    for p in parametros:
        valor = (guardados or {}).get(p.nombre)
        if valor in (None, ""):
            valor = p.defecto
        filas.append((p.etiqueta, vacio if valor in (None, "") else p.texto(valor)))
    return filas


def resolver(parametros, guardados):
    """Valores efectivos: lo guardado o, si falta, el valor por defecto."""
    return {p.nombre: p.desde_json((guardados or {}).get(p.nombre)) for p in parametros}
