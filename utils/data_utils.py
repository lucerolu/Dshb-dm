import pandas as pd
from datetime import datetime
import streamlit as st

@st.cache_data
def filtrar_por_periodo(df, periodo, año):
    df["fecha"] = pd.to_datetime(df["mes"])
    
    if periodo == "Año Natural":
        return df[df["fecha"].dt.year == año], f"{año}"
    
    elif periodo == "Año Fiscal":
        inicio_fiscal = pd.Timestamp(año-1, 11, 1)
        fin_fiscal = pd.Timestamp(año, 10, 31)
        return df[(df["fecha"] >= inicio_fiscal) & (df["fecha"] <= fin_fiscal)], f"Fiscal {año}"

@st.cache_data
def preparar_comparativo_mensual(df_filtrado, orden_meses):
    """Prepara los datos para el comparativo mensual y la variación."""
    df_mensual = df_filtrado.groupby("mes_nombre", as_index=False)["monto"].sum()
    df_mensual["mes_nombre"] = pd.Categorical(df_mensual["mes_nombre"], categories=orden_meses, ordered=True)
    df_mensual = df_mensual.sort_values("mes_nombre").reset_index(drop=True)

    # Calcular diferencia y variación
    df_mensual["diferencia"] = df_mensual["monto"].diff().fillna(0)
    df_mensual["variacion_pct"] = df_mensual["monto"].pct_change().fillna(0) * 100

    # Versiones en string con flechas
    df_mensual["monto_str"] = df_mensual["monto"].apply(lambda x: f"${x:,.2f}")
    df_mensual["diferencia_str"] = df_mensual["diferencia"].apply(
        lambda x: f"${x:,.2f} ⬆" if x > 0 else f"${x:,.2f} ⬇" if x < 0 else "$0 ➖"
    )
    df_mensual["variacion_str"] = df_mensual["variacion_pct"].apply(
        lambda x: f"{x:.1f}% ⬆" if x > 0 else f"{x:.1f}% ⬇" if x < 0 else "0.0% ➖"
    )

    return df_mensual