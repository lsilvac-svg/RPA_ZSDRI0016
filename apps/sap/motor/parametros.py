from dataclasses import dataclass


@dataclass
class ParametrosConexion:
    conexion_logon: str
    usuario: str
    clave: str
    ruta_saplogon: str
    finalizar_otras_sesiones: bool = True
    tiempo_espera: int = 30
    tiempo_inicio_saplogon: int = 60
