"""Lectura de Excel y actualización incremental (upsert) de una tabla histórica."""
from dataclasses import dataclass, field
from datetime import date, datetime

COLUMNA_ACTUALIZACION = "Actualizado RPA"


def leer_excel(ruta):
    """(cabecera, filas) de la primera hoja, con valores aptos para Sheets."""
    from openpyxl import load_workbook

    libro = load_workbook(ruta, read_only=True, data_only=True)
    try:
        filas = [
            [valor_celda(v) for v in fila]
            for fila in libro.worksheets[0].iter_rows(values_only=True)
        ]
    finally:
        libro.close()

    filas = [f for f in filas if any(v != "" for v in f)]
    if not filas:
        return [], []
    cabecera = [str(v).strip() for v in filas[0]]
    while cabecera and cabecera[-1] == "":
        cabecera.pop()
    ancho = len(cabecera)
    return cabecera, [(f + [""] * ancho)[:ancho] for f in filas[1:]]


def valor_celda(valor):
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        if (valor.hour, valor.minute, valor.second) == (0, 0, 0):
            return valor.date().isoformat()
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, str):
        return valor.strip()
    return valor


def _texto(valor):
    return str(valor_celda(valor))


def _nombres_unicos(cabecera):
    """Distingue columnas repetidas (p. ej. 'Proveedor' aparece dos veces)."""
    vistos = {}
    unicos = []
    for nombre in cabecera:
        vistos[nombre] = vistos.get(nombre, 0) + 1
        unicos.append((nombre, vistos[nombre]))
    return unicos


@dataclass
class ResultadoFusion:
    filas: list = field(default_factory=list)  # cabecera + datos, listo para escribir
    nuevas: int = 0
    actualizadas: int = 0
    sin_cambios: int = 0
    sin_clave: int = 0
    conservadas: int = 0  # históricas que no vinieron en el archivo
    columnas_nuevas: list = field(default_factory=list)


def fusionar(existentes, cabecera, filas, columnas_clave, marca_tiempo):
    """Actualiza la tabla `existentes` (cabecera incluida) con `filas`.

    - Fila con la misma clave: se reemplaza si cambió algún valor.
    - Clave nueva: se agrega al final.
    - Filas históricas que no vienen en `filas`: se conservan.
    La última columna registra cuándo el robot creó o cambió cada fila.
    """
    resultado = ResultadoFusion()
    nuevos_nombres = _nombres_unicos(cabecera)

    faltan = [c for c in columnas_clave if c not in cabecera]
    if faltan:
        raise ValueError(f"El Excel no tiene las columnas clave: {', '.join(faltan)}")

    # Cabecera final: la existente (sin la columna del robot) + columnas nuevas
    if existentes and existentes[0]:
        previa = [str(v) for v in existentes[0]]
        if previa and previa[-1] == COLUMNA_ACTUALIZACION:
            previa = previa[:-1]
        nombres = _nombres_unicos(previa)
        for nombre in nuevos_nombres:
            if nombre not in nombres:
                nombres.append(nombre)
                resultado.columnas_nuevas.append(nombre[0])
        cuerpo_previo = existentes[1:]
        ancho_previo = len(previa)
    else:
        nombres = list(nuevos_nombres)
        cuerpo_previo = []
        ancho_previo = 0

    ancho = len(nombres)
    posicion = {nombre: i for i, nombre in enumerate(nombres)}
    indices_clave = [posicion[(c, 1)] for c in columnas_clave]

    def clave(fila):
        return tuple(_texto(fila[i]) for i in indices_clave)

    tabla = []
    indice = {}
    for fila in cuerpo_previo:
        datos = (list(fila[:ancho_previo]) + [""] * ancho)[:ancho]
        marca = fila[ancho_previo] if len(fila) > ancho_previo else ""
        indice.setdefault(clave(datos), len(tabla))
        tabla.append([datos, marca])

    vistas = set()
    for fila in filas:
        datos = [""] * ancho
        for nombre, valor in zip(nuevos_nombres, fila):
            datos[posicion[nombre]] = valor
        k = clave(datos)
        if all(v == "" for v in k):
            resultado.sin_clave += 1
            continue
        vistas.add(k)
        if k in indice:
            actual = tabla[indice[k]]
            if [_texto(v) for v in actual[0]] != [_texto(v) for v in datos]:
                tabla[indice[k]] = [datos, marca_tiempo]
                resultado.actualizadas += 1
            else:
                resultado.sin_cambios += 1
        else:
            indice[k] = len(tabla)
            tabla.append([datos, marca_tiempo])
            resultado.nuevas += 1

    resultado.conservadas = sum(1 for datos, _ in tabla if clave(datos) not in vistas)
    resultado.filas = [[n for n, _ in nombres] + [COLUMNA_ACTUALIZACION]] + [
        datos + [marca] for datos, marca in tabla
    ]
    return resultado
