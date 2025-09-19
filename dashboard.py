import streamlit as st
import pandas as pd
from datetime import datetime
import streamlit_authenticator as stauth

# ------------------- IMPORTS PROPIOS -------------------
from config import cargar_config
from utils.api_utils import obtener_datos_api, mostrar_fecha_actualizacion
from helpers import meses_es

# Configuración de la página
st.set_page_config(page_title="Dashboard Compras 2025", layout="wide")

# ------------------- AUTENTICACIÓN -------------------
auth_config = dict(st.secrets["auth"])
credentials = {k: dict(v) if isinstance(v, dict) else v for k, v in auth_config["credentials"].items()}

authenticator = stauth.Authenticate(
    credentials,
    auth_config["cookie"]["name"],
    auth_config["cookie"]["key"],
    auth_config["cookie"]["expiry_days"],
    auth_config.get("preauthorized", {}).get("emails", [])
)

name, authentication_status, username = authenticator.login("Iniciar Sesión", "main")

# =============================== MAIN ===============================
if authentication_status:
    st.session_state["user_name"] = name
    config = cargar_config()
    df = obtener_datos_api()

    if not df.empty:
        df = df.dropna(subset=["sucursal"])
        df["mes_dt"] = pd.to_datetime(df["mes"])
        df["mes_nombre"] = df["mes_dt"].dt.month_name().map(meses_es) + " " + df["mes_dt"].dt.year.astype(str)
        df["mes_period"] = df["mes_dt"].dt.to_period("M")
        df = df.sort_values("mes_dt")

        # ------------------- DIVISIONES Y COLORES -------------------
        divisiones = config["divisiones"]
        mapa_codigos = {}
        colores_divisiones = {}
        codigo_division_map = {}
        for division, datos in divisiones.items():
            colores_divisiones[division] = datos["color"]
            for cod in datos["codigos"]:
                mapa_codigos[cod] = division
                codigo_division_map[cod] = {
                    "color": datos["color"],
                    "abreviatura": datos["abreviatura"],
                    "division": division
                }

        df["division"] = df["codigo_normalizado"].map(mapa_codigos)
        df_divisiones = df.dropna(subset=["division"]).copy()
        df_divisiones["mes_dt"] = pd.to_datetime(df_divisiones["mes"])
        df_divisiones["mes_nombre"] = (
            df_divisiones["mes_dt"].dt.month_name().map(meses_es)
            + " "
            + df_divisiones["mes_dt"].dt.year.astype(str)
        )
        colores_sucursales_map = {suc: data["color"] for suc, data in config["sucursales"].items()}

    # ------------------- SIDEBAR -------------------
    with st.sidebar:
        st.markdown(f"👋 **Bienvenido {st.session_state['user_name']}**")
        opcion = st.selectbox("Selecciona una vista", [
            "Estado de cuenta",
            "Resumen General",
            "Compra por División",
            "Compra por Cuenta",
            "Compra por Sucursal",
            "Vista por Sucursal",
            "Estado de Ligado",
        ])
        authenticator.logout("Cerrar sesión", "sidebar")
        st.markdown("---")

        # ------------------- MÉTRICAS DE TOTALES -------------------
        if "fecha" not in df.columns:
            df["fecha"] = pd.to_datetime(df["mes"])

        ahora = datetime.now()
        ahora_pd = pd.Timestamp(ahora)
        mes_actual_period = ahora_pd.to_period("M")
        mes_actual_esp = meses_es.get(ahora.strftime("%B"), "") + " " + str(ahora.year)

        df_natural = df[df["fecha"].dt.year == 2025]
        total_anual_natural = df_natural["monto"].sum()
        total_mes_actual = df_natural[df_natural["mes_period"] == mes_actual_period]["monto"].sum()

        inicio_fiscal = pd.Timestamp(2024, 11, 1)
        fin_fiscal = pd.Timestamp(2025, 10, 31)
        df_fiscal = df[(df["fecha"] >= inicio_fiscal) & (df["fecha"] <= fin_fiscal)]
        total_anual_fiscal = df_fiscal["monto"].sum()

        st.markdown(f"""
        <div style="margin-bottom:15px;">
            <div style="font-size:12px; color:white;">Año Natural 2025</div>
            <div style="font-size:20px; font-weight:bold;">${total_anual_natural:,.2f}</div>
        </div>
        <div style="margin-bottom:15px;">
            <div style="font-size:12px; color:white;">Año Fiscal 2025</div>
            <div style="font-size:20px; font-weight:bold;">${total_anual_fiscal:,.2f}</div>
        </div>
        <div style="margin-bottom:15px;">
            <div style="font-size:12px; color:white;">Mes Actual ({mes_actual_esp})</div>
            <div style="font-size:20px; font-weight:bold;">${total_mes_actual:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        mostrar_fecha_actualizacion()

    # ------------------- RENDERIZADO DINÁMICO -------------------
    from secciones import (
        estado_cuenta,
        resumen_general,
        compra_division,
        compra_cuenta,
        compra_sucursal,
        vista_sucursal,
        estado_ligado,
    )

    if opcion == "Estado de cuenta":
        estado_cuenta.mostrar()   # ✅ autosuficiente
    elif opcion == "Resumen General":
        resumen_general.mostrar(df, config)
    elif opcion == "Compra por División":
        compra_division.mostrar(df, config)
    elif opcion == "Compra por Cuenta":
        compra_cuenta.mostrar(df, config)
    elif opcion == "Compra por Sucursal":
        compra_sucursal.mostrar(df, config)
    elif opcion == "Vista por Sucursal":
        vista_sucursal.mostrar(df, config)
    elif opcion == "Estado de Ligado":
        estado_ligado.mostrar(df, config)
