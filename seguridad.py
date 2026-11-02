"""Avisos de ingreso y acceso a los datos solo con sesión."""

from __future__ import annotations

import smtplib
import threading
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import streamlit as st

from supabase_http import create_client

ZONA = ZoneInfo("America/Cordoba")
ALERTA_DESTINO = "grandijuanluis@gmail.com"


def _texto(valor, limite: int = 300) -> str:
    limpio = " ".join(str(valor or "").split())
    if not limpio:
        return "desconocido"
    return limpio[:limite]


def ip_cliente() -> str:
    try:
        ip = st.context.ip_address
        if ip:
            return _texto(ip, 80)
    except Exception:
        pass
    try:
        encabezados = st.context.headers
        reenviada = encabezados.get("X-Forwarded-For") or encabezados.get("x-forwarded-for")
        if reenviada:
            return _texto(reenviada.split(",")[0], 80)
    except Exception:
        pass
    return "desconocida"


def navegador_cliente() -> str:
    try:
        agente = st.context.headers.get("User-Agent") or st.context.headers.get("user-agent")
        return _texto(agente, 400)
    except Exception:
        return "desconocido"


def armar_aviso_intento(usuario: str, ip: str, agente: str, resultado: str, momento: datetime) -> tuple[str, str]:
    cuando = momento.strftime("%d/%m/%Y %H:%M:%S")
    cuerpo = (
        "Intento de ingreso al portal Fremec\n"
        "\n"
        f"Fecha y hora (Córdoba): {cuando}\n"
        f"Usuario escrito: {_texto(usuario, 200)}\n"
        f"Resultado: {_texto(resultado, 80)}\n"
        f"IP: {_texto(ip, 80)}\n"
        f"Navegador: {_texto(agente, 400)}\n"
    )
    return "Fremec: intento de ingreso", cuerpo


def _cliente():
    try:
        url = str(st.secrets["SUPABASE_URL"]).strip()
        key = str(st.secrets["SUPABASE_KEY"]).strip()
        if not url or not key:
            return None
        return create_client(url, key)
    except Exception:
        return None


def _smtp():
    try:
        secreto = st.secrets
        usuario = str(secreto.get("SMTP_USER", "")).strip()
        clave = str(secreto.get("SMTP_PASSWORD", "")).strip()
        if not usuario or not clave:
            return None
        return {
            "host": str(secreto.get("SMTP_HOST", "smtp.gmail.com")).strip() or "smtp.gmail.com",
            "port": int(secreto.get("SMTP_PORT", 587)),
            "user": usuario,
            "password": clave,
            "destino": str(secreto.get("ALERT_EMAIL", ALERTA_DESTINO)).strip() or ALERTA_DESTINO,
        }
    except Exception:
        return None


def _enviar_correo(asunto: str, cuerpo: str, smtp: dict) -> None:
    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = smtp["user"]
    mensaje["To"] = smtp["destino"]
    mensaje.set_content(cuerpo)
    with smtplib.SMTP(smtp["host"], smtp["port"], timeout=8) as servidor:
        servidor.starttls()
        servidor.login(smtp["user"], smtp["password"])
        servidor.send_message(mensaje)


def notificar_intento(usuario: str, exito: bool, resultado: str) -> None:
    """Guarda el intento y avisa por correo. Nunca incluye la contraseña."""
    momento = datetime.now(ZONA)
    ip = ip_cliente()
    agente = navegador_cliente()
    asunto, cuerpo = armar_aviso_intento(usuario, ip, agente, resultado, momento)
    smtp = _smtp()
    cliente = _cliente()

    avisar = True
    if cliente is not None:
        try:
            respuesta = cliente.rpc(
                "fremec_registrar_intento",
                {
                    "p_usuario": _texto(usuario, 200),
                    "p_ip": ip,
                    "p_agente": agente,
                    "p_exito": bool(exito),
                },
            )
            if isinstance(respuesta, dict) and respuesta.get("avisar") is False:
                avisar = False
        except Exception as error:
            print(f"No se pudo guardar el intento de ingreso: {error}")

    if not avisar or smtp is None:
        return

    def _enviar() -> None:
        try:
            _enviar_correo(asunto, cuerpo, smtp)
        except Exception as error:
            print(f"No se pudo enviar el aviso de ingreso: {error}")

    hilo = threading.Thread(target=_enviar, daemon=True)
    hilo.start()
    hilo.join(timeout=4)


def token_sesion() -> str:
    return str(st.session_state.get("sesion_token") or "")


def iniciar_sesion(usuario: str, clave: str):
    cliente = _cliente()
    if cliente is None:
        raise RuntimeError("No hay conexión con la base.")
    return cliente.rpc(
        "fremec_iniciar_sesion",
        {"p_usuario": usuario or "", "p_clave": clave or ""},
    )


def cerrar_sesion() -> None:
    cliente = _cliente()
    token = token_sesion()
    if cliente is None or not token:
        return
    try:
        cliente.rpc("fremec_cerrar_sesion", {"p_token": token})
    except Exception as error:
        print(f"No se pudo cerrar la sesión en la base: {error}")


def perfil_actual():
    cliente = _cliente()
    token = token_sesion()
    if cliente is None or not token:
        return None
    datos = cliente.rpc("fremec_yo", {"p_token": token})
    if isinstance(datos, dict) and datos.get("nombre"):
        return datos
    return None


def auditar(tabla: str, accion: str, detalle: str) -> None:
    cliente = _cliente()
    token = token_sesion()
    if cliente is None or not token:
        return
    try:
        cliente.rpc(
            "fremec_auditar",
            {
                "p_token": token,
                "p_tabla": tabla,
                "p_accion": accion,
                "p_detalle": detalle,
            },
        )
    except Exception as error:
        print(f"Error escribiendo en auditoría: {error}")


def _rpc(nombre: str, params: dict):
    cliente = _cliente()
    if cliente is None:
        raise RuntimeError("No hay conexión con la base.")
    params = dict(params)
    params["p_token"] = token_sesion()
    return cliente.rpc(nombre, params)


def listar_usuarios():
    datos = _rpc("fremec_listar_usuarios", {})
    return datos if isinstance(datos, list) else []


def crear_usuario(datos: dict) -> None:
    _rpc("fremec_crear_usuario", {"p_datos": datos})


def actualizar_usuario(usuario_id: int, datos: dict) -> None:
    _rpc("fremec_actualizar_usuario", {"p_id": int(usuario_id), "p_datos": datos})


def eliminar_usuario(usuario_id: int) -> None:
    _rpc("fremec_eliminar_usuario", {"p_id": int(usuario_id)})


def nombres_excluidos():
    datos = _rpc("fremec_nombres_excluidos", {})
    return datos if isinstance(datos, list) else []


def listar_registros():
    datos = _rpc("fremec_listar_registros", {})
    return datos if isinstance(datos, list) else []


def crear_registro(datos: dict) -> None:
    _rpc("fremec_crear_registro", {"p_datos": datos})


def actualizar_registro(registro_id: int, datos: dict) -> None:
    _rpc("fremec_actualizar_registro", {"p_id": int(registro_id), "p_datos": datos})


def eliminar_registro(registro_id: int) -> None:
    _rpc("fremec_eliminar_registro", {"p_id": int(registro_id)})
