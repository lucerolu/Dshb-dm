import streamlit as st
import pandas as pd
import pymysql
import plotly.graph_objects as go
import plotly.express as px
import json
import os
import math
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.colors as mcolors
from matplotlib.colors import LinearSegmentedColormap
from datetime import datetime
from datetime import timedelta
import locale
import io
import requests
import itertools
from st_aggrid import AgGrid, GridOptionsBuilder


#==========================================================================================================
# -------------- CONFIGURACION GENERAL --------------------------------------------------------------------
#==========================================================================================================
st.set_page_config(page_title="Dashboard Compras 2025", layout="wide")

with open("config_colores.json", "r", encoding="utf-8") as f:
    config = json.load(f)

colores_sucursales = config["sucursales"]

API_BASE = "https://fastapi-api-454780168370.us-central1.run.app"

def obtener_datos_api():
    url = f"{API_BASE}/datos"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Error al obtener datos de la API: {e}")
        return pd.DataFrame()

def obtener_estado_cuenta_api():
    url = f"{API_BASE}/estado_cuenta"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        # EXTRAER los datos correctamente
        lista_datos = data.get("datos", [])
        fecha_corte = pd.to_datetime(data.get("fecha_corte"))

        df = pd.DataFrame(lista_datos)

        if df.empty:
            return pd.DataFrame(), None

        return df, fecha_corte

    except Exception as e:
        st.error(f"Error al obtener estado de cuenta de la API: {e}")
        return pd.DataFrame(), None


# ----------------------------------------------- OBTENER DATOS -------------------------------------------------------------------------------
df = obtener_datos_api()
if not df.empty:
    df = df.dropna(subset=["sucursal"])

    meses_es = {
        'January': 'Enero', 'February': 'Febrero', 'March': 'Marzo', 'April': 'Abril',
        'May': 'Mayo', 'June': 'Junio', 'July': 'Julio', 'August': 'Agosto',
        'September': 'Septiembre', 'October': 'Octubre', 'November': 'Noviembre', 'December': 'Diciembre'
    }

    df["mes_dt"] = pd.to_datetime(df["mes"])
    df["mes_nombre"] = df["mes_dt"].dt.month_name().map(meses_es) + " " + df["mes_dt"].dt.year.astype(str)
    df["mes_period"] = df["mes_dt"].dt.to_period("M")
    df = df.sort_values("mes_dt")
    # Orden ascendente (para gráficas que van de enero a diciembre)
    orden_meses_asc = (
        df.drop_duplicates(subset="mes_period")
        .sort_values("mes_period", ascending=True)["mes_nombre"]
        .tolist()
    )

    # Orden descendente (para gráficas que van de mes más reciente al más antiguo)
    orden_meses_desc = orden_meses_asc[::-1]
    orden_meses = orden_meses_asc

    # ------------------------------------------ DIVISIONES ----------------------------------------------------
    divisiones = config["divisiones"]
    mapa_codigos = {}
    colores_divisiones = {}
    for division, info in divisiones.items():
        for codigo in info["codigos"]:
            mapa_codigos[codigo] = division
        colores_divisiones[division] = info["color"]

    df["division"] = df["codigo_normalizado"].map(mapa_codigos)
    df_divisiones = df.dropna(subset=["division"])  # descarta cuentas sin división
    df_divisiones["mes_dt"] = pd.to_datetime(df_divisiones["mes"])
    df_divisiones["mes_nombre"] = df_divisiones["mes_dt"].dt.month_name().map(meses_es) + " " + df_divisiones["mes_dt"].dt.year.astype(str)
else:
    st.warning("No hay datos disponibles para mostrar.")


# ------------------- MENU LATERAL -------------------------------------------------
opcion = st.sidebar.selectbox("Selecciona una vista", [
    "Resumen General",
    "Compra por División",
    "Compra por Cuenta",
    "Compra por Sucursal",
    "Vista por Sucursal",
    "Estado de Ligado",
    "Estado de cuenta"
])

# ==========================================================================================================
# ============================= RESUMEN GENERAL ============================================================
# ==========================================================================================================
if opcion == "Resumen General":
    st.title("Resumen General de Compras - 2025")
    #--------------- TARJETAS: total comprado en el año y en el mes corriente  ------------------------------------------
    ahora = datetime.now()
    ahora_pd = pd.Timestamp(ahora)  # Convertir a pandas Timestamp
    mes_actual_period = ahora_pd.to_period("M")
    mes_actual_esp = meses_es.get(ahora.strftime("%B"), "") + " " + str(ahora.year)

    col1, col2 = st.columns(2)

    with col1:
        total_anual = df["monto"].sum()
        st.metric("Total comprado en el año", f"${total_anual:,.2f}")

    with col2:
        total_mes_actual = df[df["mes_period"] == mes_actual_period]["monto"].sum()
        mes_actual_esp = meses_es.get(ahora.strftime("%B"), "") + " " + str(ahora.year)
        st.metric(f"Total comprado en {mes_actual_esp}", f"${total_mes_actual:,.2f}")

    # ------------------------------------ GÁFICA DE LÍNEAS DEL TOTAL GENERAL  -----------------------------------------------------------------------------------------------------------------
    df_total_mes = df.groupby("mes_nombre")["monto"].sum().reindex(orden_meses)
    fig_total = go.Figure()
    fig_total.add_trace(go.Scatter(
        x=df_total_mes.index,
        y=df_total_mes.values,
        mode="lines+markers",
        name="Total",
        line=dict(color="blue"),
        hovertemplate="%{x}<br>Total: $%{y:,.2f}<extra></extra>"  # 👈 muestra el número con comas y sin abreviar
    ))
    fig_total.update_layout(
        title="Evolución mensual del total comprado",
        xaxis_title="Mes",
        yaxis_title="Monto",
        yaxis_tickformat=","  # 👈 muestra ejes con comas en lugar de abreviaturas
    )
    st.plotly_chart(fig_total, use_container_width=True)
  
    # ----------------------------------------- TABLA: TOTAL COMPRADO POR MES --------------------------------------------------------------------------------------------
    st.markdown("### Total comprado por mes")

    # Agrupar y pivotear para una sola fila
    tabla_horizontal = df.groupby("mes_nombre")["monto"].sum().reindex(orden_meses)
    tabla_horizontal_df = pd.DataFrame(tabla_horizontal).T
    tabla_horizontal_df.index = ["Total Comprado"]

    # Agregar columna para que no se pierda el nombre
    tabla_horizontal_df.insert(0, "Descripción", tabla_horizontal_df.index)
    tabla_horizontal_df.reset_index(drop=True, inplace=True)

    # Agregar columna "Total" con suma de todos los meses
    # Sumamos desde la columna 1 (primer mes) hasta la última
    # OJO: aquí asumimos que todas las columnas excepto "Descripción" son meses
    meses_cols = tabla_horizontal_df.columns[1:]  # desde primer mes hasta último
    tabla_horizontal_df["Total"] = tabla_horizontal_df[meses_cols].apply(
        lambda fila: fila.str.replace("[$,]", "", regex=True).astype(float).sum(), axis=1
    )

    # Formatear columnas como texto con formato de moneda (incluyendo Total)
    for col in meses_cols.tolist() + ["Total"]:
        tabla_horizontal_df[col] = tabla_horizontal_df[col].apply(lambda x: f"${x:,.2f}")

    # Configurar AgGrid
    gb = GridOptionsBuilder.from_dataframe(tabla_horizontal_df)
    gb.configure_default_column(resizable=True, filter=True, sortable=True)

    # Fijar la primera columna (Descripción) a la izquierda y con colores
    gb.configure_column(
        "Descripción",
        pinned="left",
        cellStyle={'color': 'white', 'backgroundColor': '#6F079C'},
        minWidth=180,
        maxWidth=300,
        flex=0  # fijo ancho
    )

    # Configurar todas las demás columnas (meses + Total) para distribuirse proporcionalmente
    for col in meses_cols.tolist() + ["Total"]:
        gb.configure_column(
            col,
            minWidth=100,
            maxWidth=250,
            flex=1  # todas con igual peso para distribuir espacio
        )

    altura_dinamica = 35 * (len(tabla_horizontal_df) + 1) + 10

    AgGrid(
        tabla_horizontal_df,
        gridOptions=gb.build(),
        height=altura_dinamica,
        fit_columns_on_grid_load=False,
        theme="streamlit",
        enable_enterprise_modules=False,
        allow_unsafe_jscode=True
    )

# ---------------------------- GRÁFICA: Total comprado por mes ------------------------------------------------------------------------------
    #st.markdown("### Gráfica de Total comprado por mes")
    # Agrupar de nuevo (en bruto, sin formato)
    df_mensual = df.groupby("mes_nombre", as_index=False)["monto"].sum()
    df_mensual["mes_nombre"] = pd.Categorical(df_mensual["mes_nombre"], categories=orden_meses, ordered=True)
    df_mensual = df_mensual.sort_values("mes_nombre")

    # Formato de texto
    df_mensual["texto_monto"] = df_mensual["monto"].apply(lambda x: f"${x:,.2f}")

    # Crear gráfica
    fig = go.Figure()

    fig.add_trace(go.Bar(
        y=df_mensual["mes_nombre"],
        x=df_mensual["monto"],
        orientation='h',
        marker_color="#1f77b4",  # azul default
        text=df_mensual["texto_monto"],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y}<br>Total: %{text}<extra></extra>"
    ))

    # Ajustes visuales
    altura_total = max(400, len(df_mensual) * 40)

    fig.update_layout(
        xaxis_title="Monto de compra (MXN)",
        yaxis_title="Mes",
        xaxis_tickformat=",",
        height=altura_total,
        margin=dict(r=70),
        bargap=0.25
    )

    st.plotly_chart(fig, use_container_width=True)
    st.markdown("<br><br>", unsafe_allow_html=True)

    #------------------------------------------ COMPARATIVO: MES VS MES ANTERIOR ---------------------------------------------------------------------------------------------------------
    st.markdown("### Comparativo de compras mensuales")
    st.markdown("#### Compra vs mes anterior")  # Subtítulo

    # Agrupar y ordenar por mes
    df_mensual = df.groupby("mes_nombre", as_index=False)["monto"].sum()
    df_mensual["mes_nombre"] = pd.Categorical(df_mensual["mes_nombre"], categories=orden_meses, ordered=True)
    df_mensual = df_mensual.sort_values("mes_nombre").reset_index(drop=True)

    # Calcular diferencia y variación
    df_mensual["diferencia"] = df_mensual["monto"].diff().fillna(0)
    df_mensual["variacion_pct"] = df_mensual["monto"].pct_change().fillna(0) * 100

    # Función con flechas negras en HTML
    def formatear_flecha_html(dif, pct):
        if dif > 0:
            return f"⬆ +${dif:,.2f}", f"⬆ +{pct:.1f}%"
        elif dif < 0:
            return f"⬇ ${dif:,.2f}", f"⬇ {pct:.1f}%"
        else:
            return "➖ $0", "➖ 0.0%"

    df_mensual[["diferencia_str", "variacion_str"]] = df_mensual.apply(
        lambda row: pd.Series(formatear_flecha_html(row["diferencia"], row["variacion_pct"])),
        axis=1
    )

    # Formato del monto
    df_mensual["monto_str"] = df_mensual["monto"].apply(lambda x: f"${x:,.2f}")

    # Tabla final
    df_comp = df_mensual[["mes_nombre", "monto_str", "diferencia_str", "variacion_str"]]
    df_comp.columns = ["Mes", "Total Comprado", "Diferencia ($)", "Variación (%)"]

    # Resaltar con bordes
    def resaltar_con_bordes(row):
        estilos = []
        if "⬇" in row["Diferencia ($)"]:
            estilos = ['border: 1px solid black; background-color: #184E08'] * len(row)
        elif "⬆" in row["Diferencia ($)"]:
            estilos = ['border: 1px solid black; background-color: #7D1F08'] * len(row)
        else:
            estilos = [''] * len(row)
        return estilos

    # Mostrar tabla
    st.dataframe(
        df_comp.style
            .apply(resaltar_con_bordes, axis=1)
            .set_properties(**{"text-align": "center"}),
        use_container_width=True,
        hide_index=True
    )
    st.markdown("<br><br>", unsafe_allow_html=True)

    # --------------------------------------- GRÁFICA DE DIFERENCIAS MENSUALES --------------------------------------------------------------------------------------------
    st.markdown("### Variación de compras respecto al mes anterior")

    # Agrupar y ordenar por mes
    df_mensual = df.groupby("mes_nombre", as_index=False)["monto"].sum()
    df_mensual["mes_nombre"] = pd.Categorical(df_mensual["mes_nombre"], categories=orden_meses, ordered=True)
    df_mensual = df_mensual.sort_values("mes_nombre").reset_index(drop=True)

    # Calcular diferencias
    df_mensual["diferencia"] = df_mensual["monto"].diff().fillna(0)
    df_mensual["color"] = df_mensual["diferencia"].apply(lambda x: "#f81515" if x >= 0 else "#33FF00")
    df_mensual["texto"] = df_mensual["diferencia"].apply(lambda x: f"${x:,.2f}")

    # Crear gráfica
    fig_dif = go.Figure()

    fig_dif.add_trace(go.Bar(
        x=df_mensual["mes_nombre"],
        y=df_mensual["diferencia"],
        marker_color=df_mensual["color"],
        text=df_mensual["texto"],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{x}<br>Diferencia: %{text}<extra></extra>"
    ))

    # Ajustes visuales
    fig_dif.update_layout(
        title="Diferencia mensual de compras vs mes anterior",
        xaxis_title="Mes",
        yaxis_title="Diferencia en monto (MXN)",
        yaxis=dict(zeroline=True, zerolinecolor="black"),
        height=450,
        margin=dict(r=70)
    )

    st.plotly_chart(fig_dif, use_container_width=True)


# ================================================================================================================================
# ============================= COMPRA POR DIVISION =======================================
# ================================================================================================================================
elif opcion == "Compra por División":
    st.title("Distribución de Compras por División - 2025")
    st.markdown("<br><br>", unsafe_allow_html=True)

    #------------------------- GRÁFICO DE PASTEL ---------------------------------------------------------
    df_agrupado = df_divisiones.groupby("division")["monto"].sum().reset_index()
    df_agrupado["texto"] = df_agrupado.apply(
        lambda row: f"{row['division']}<br>${row['monto']:,.2f}", axis=1
    )

    fig_pie = px.pie(
        df_agrupado,
        values="monto",
        names="division",
        color="division",
        color_discrete_map=colores_divisiones,
       hole=0.4
    )
    fig_pie.update_traces(textinfo="percent+label", textposition="inside")

    fig_pie.update_layout(
        title=dict(text="Distribución del total anual comprado por División", x=0.5, xanchor="center", y=1.0),
        height=500,
        legend=dict(
            orientation="h",  # horizontal
            yanchor="top",
            y=-0.2,           # un poco debajo del gráfico
            xanchor="center",
            x=0.5
        )
    )

    st.plotly_chart(fig_pie, use_container_width=True)
    st.markdown("<br><br>", unsafe_allow_html=True)



    # ------------------------- TARJETAS: TOTAL COMPRADO POR DIVISIÓN ------------------------------
    col1, col2, col3 = st.columns(3)
    divs = df_agrupado.set_index("division")

    with col1:
        monto = divs.loc["Agrícola", "monto"]
        st.metric("Agrícola", f"${monto:,.2f}")

    with col2:
        monto = divs.loc["Construcción", "monto"]
        st.metric("Construcción", f"${monto:,.2f}")

    with col3:
        monto = divs.loc["Jardinería y Golf", "monto"]
        st.metric("Jardinería y Golf", f"${monto:,.2f}")
    st.markdown("<br><br>", unsafe_allow_html=True)

    # --------------- GRÁFICO DE BARRAS DEL TOTAL ANUAL COMPRADO POR DIVISIÓN ----------------------------------------------
    df_agrupado["porcentaje"] = df_agrupado["monto"] / df_agrupado["monto"].sum() * 100
    df_agrupado["texto_barra"] = df_agrupado.apply(
        lambda row: f"${row['monto']:,.0f}<br>{row['porcentaje']:.1f}%", axis=1
    )

    fig_bar = px.bar(
        df_agrupado,
        x="division",
        y="monto",
        color="division",
        text="texto_barra",
        color_discrete_map=colores_divisiones,
        labels={"monto": "Monto Comprado", "division": "División"}
    )
    fig_bar.update_traces(textposition="inside", texttemplate="%{text}")
    fig_bar.update_layout(
        title=dict(text="Monto total anual por División", x=0.5, xanchor="center", y=1.0),
        showlegend=False
    )
    st.plotly_chart(fig_bar, use_container_width=True)
    st.markdown("<br><br>", unsafe_allow_html=True)

    # ---------------- TABLA: TOTAL MENSUAL COMPRADO POR DIVISIÓN ---------------------------------------------------------------------------
    tabla_pivot = df_divisiones.pivot_table(
        index="division",
        columns="mes_nombre",
        values="monto",
        aggfunc="sum",
        fill_value=0  # ya reemplaza nulls por 0
    )

    # Renombrar índice (nombre de la columna del índice)
    tabla_pivot.index.rename("División", inplace=True)

    # Mostrar la tabla formateada
    st.dataframe(
        tabla_pivot.style.format("${:,.2f}"),
        use_container_width=True
    )
    st.markdown("<br><br>", unsafe_allow_html=True)

    # ------------ GRÁFICA DE BARRAS AGRUPADAS: EVOLUCIÓN MENSUAL COMPRADO POR DIVISIÓN ------------------------------------------------------------
    df_mes_div = df_divisiones.groupby(["mes_nombre", "division"])["monto"].sum().reset_index()
    df_mes_div["mes_nombre"] = pd.Categorical(df_mes_div["mes_nombre"], categories=orden_meses, ordered=True)
    df_mes_div = df_mes_div.sort_values("mes_nombre")

    fig_mes_div = px.bar(
        df_mes_div,
        x="mes_nombre",
        y="monto",
        color="division",
        text="monto",
        color_discrete_map=colores_divisiones,
        labels={"mes_nombre": "Mes", "monto": "Total Comprado", "division": "División"}
    )
    fig_mes_div.update_traces(texttemplate="$%{text:,.0f}", textposition="inside")
    fig_mes_div.update_layout(
        title=dict(text="Evolución mensual de compras por División", x=0.5, xanchor="center", y=1.0),
        barmode="stack",
        xaxis=dict(tickangle=-45),
        margin=dict(t=60, b=100),  # Aumenta margen superior e inferior
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.6,
            xanchor="center",
            x=0.5
        )
    )
    st.plotly_chart(
        fig_mes_div, 
        use_container_width=True,
        config={
            "modeBarButtonsToRemove": [
                "pan2d",
                "select2d",
                "lasso2d",
                "zoomIn2d",
                "zoomOut2d",
                "resetScale2d",
                "hoverClosestCartesian",
                "hoverCompareCartesian"
            ],
            "displaylogo": False
        }
    )
    st.markdown("<br><br>", unsafe_allow_html=True)


    #----------------- GRÁFICA DE BARRAS AGRUPADAS: COMPRA POR SUCURSAL Y DIVISIÓN ------------------------------------------------------------
    df_suc_div = df_divisiones.groupby(["sucursal", "division"])["monto"].sum().reset_index()

    fig_suc_div = px.bar(
        df_suc_div,
        x="sucursal",
        y="monto",
        color="division",
        text="monto",
        color_discrete_map=colores_divisiones,
        labels={
            "sucursal": "Sucursal",
            "monto": "Total Comprado",
            "division": "División"},
    )

    fig_suc_div.update_traces(texttemplate="$%{text:,.0f}", textposition="inside")
    fig_suc_div.update_layout(
        title=dict(text="Compra anual por Sucursal y División", x=0.5, xanchor="center", y=1.0),
        barmode="stack",
        xaxis_tickangle=-45,
        margin=dict(t=60, b=100),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.6,
            xanchor="center",
            x=0.5
        )
    )
    st.plotly_chart(fig_suc_div, use_container_width=True)
    st.markdown("<br><br>", unsafe_allow_html=True)


    #----------------------- Tabla de compra por division y sucursal ----------------------------------
    tabla_sucursal_division = pd.pivot_table(
        df_divisiones,
        values="monto",
        index="division",       # Filas
        columns="sucursal",     # Columnas
        aggfunc="sum",
        margins=True,           # Agrega totales
        margins_name="Total",   # Nombre para los totales
    )

    # Renombrar índice
    tabla_sucursal_division.index.rename("División", inplace=True)

    # Reemplazar NaN por 0 para que no salga "null"
    tabla_formateada = tabla_sucursal_division.fillna(0).applymap(lambda x: f"${x:,.0f}")

    st.subheader("Monto anual comprado por sucursal y división")
    st.dataframe(tabla_formateada, use_container_width=True)
    st.markdown("<br><br>", unsafe_allow_html=True)

    #----------- Graficos de columnas de compra mensual por división y sucursal -------------
    with open("config_colores.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    colores_divisiones = {k: v["color"] for k, v in config["divisiones"].items()}

    # Agrupar datos
    df_smd = df.groupby(["sucursal", "mes_nombre", "division"], as_index=False)["monto"].sum()
    df_smd["sucursal"] = df_smd["sucursal"].astype(str)
    df_smd["mes_nombre"] = df_smd["mes_nombre"].astype(str)
    df_smd["division"] = df_smd["division"].astype(str)

    sucursales = df_smd["sucursal"].unique()
    num_sucursales = len(sucursales)
    
    # Lista en español (la mantienes como está)
    orden_meses_con_anio = [
        "Enero 2025", "Febrero 2025", "Marzo 2025", "Abril 2025", "Mayo 2025", "Junio 2025",
        "Julio 2025", "Agosto 2025", "Septiembre 2025", "Octubre 2025", "Noviembre 2025", "Diciembre 2025"
    ]

    # Mapeo Español → Inglés (solo para conversión interna)
    meses_es_en = {
        'Enero': 'January', 'Febrero': 'February', 'Marzo': 'March', 'Abril': 'April',
        'Mayo': 'May', 'Junio': 'June', 'Julio': 'July', 'Agosto': 'August',
        'Septiembre': 'September', 'Octubre': 'October', 'Noviembre': 'November', 'Diciembre': 'December'
    }

    # Crear columna temporal para conversión
    df_smd["mes_nombre_en"] = df_smd["mes_nombre"].str.extract(r"(\w+)\s+(\d{4})").apply(
        lambda row: f"{meses_es_en.get(row[0], row[0])} {row[1]}", axis=1
    )

    # Convertir la columna en inglés a datetime
    df_smd["fecha_mes"] = pd.to_datetime(df_smd["mes_nombre_en"], format="%B %Y")

    # Obtener el mes más reciente con datos
    max_fecha = df_smd["fecha_mes"].max()

    # También convertir la lista `orden_meses_con_anio` a fechas para comparar con max_fecha
    orden_meses_fecha = [
        pd.to_datetime(f"{meses_es_en[m.split()[0]]} {m.split()[1]}", format="%B %Y")
        for m in orden_meses_con_anio
    ]

    # Filtrar los que estén antes o igual a max_fecha
    meses_hasta_max = [
        orden_meses_con_anio[i] for i, fecha in enumerate(orden_meses_fecha) if fecha <= max_fecha
    ]

    # Re-categorizar `mes_nombre` para ordenarlo visualmente
    df_smd["mes_nombre"] = pd.Categorical(df_smd["mes_nombre"], categories=meses_hasta_max, ordered=True)

    # Orden final
    df_smd = df_smd.sort_values(["sucursal", "mes_nombre"])

    # (Opcional) limpiar columna temporal
    df_smd.drop(columns=["mes_nombre_en"], inplace=True)


    st.title("Evolución de compras por sucursal")

    # Opción para columnas: 1 o 2, para simular responsive
    num_columnas = st.radio("Número de columnas de gráficos por fila:", options=[1, 2], index=1)
    num_filas = math.ceil(num_sucursales / num_columnas)

    # Ordenar divisiones para colores
    divisiones_ordenadas = sorted(df_smd["division"].unique())
    palette = [colores_divisiones.get(div, "#777777") for div in divisiones_ordenadas]

    for i in range(0, num_sucursales, num_columnas):
        cols = st.columns(num_columnas)

        for j in range(num_columnas):
           if i + j < num_sucursales:
                suc = sucursales[i + j]
                df_filtrado = df_smd[df_smd["sucursal"] == suc]

                fig, ax = plt.subplots(figsize=(8, 4))
                fig.patch.set_facecolor('#121212')  # fondo figura negro
                ax.set_facecolor('#121212')          # fondo eje negro

                # Gráfico de barras horizontal con paleta personalizada
                sns.barplot(
                    data=df_filtrado,
                    x="monto",
                    y="mes_nombre",
                    hue="division",
                    palette=palette,
                    ax=ax,
                    orient="h"
                )
                # Aquí agregas las etiquetas con formato moneda y separador de miles
                for container in ax.containers:
                    ax.bar_label(container, labels=[f"${x:,.0f}" for x in container.datavalues], padding=3, color='white', fontsize=9)

                # Formatear el eje X con signo $ y comas
                ax.xaxis.set_major_formatter(mtick.StrMethodFormatter('${x:,.0f}'))
                # Colores textos para fondo oscuro
                ax.set_title(f"{suc} - Evolución de Compras", color="white")
                ax.set_xlabel("Monto", color="white")
                ax.set_ylabel("Mes", color="white")

                ax.tick_params(colors="white")      # ticks color blanco
                ax.legend(title="División", bbox_to_anchor=(1.05, 1), loc='upper left', facecolor='#121212', edgecolor='white', labelcolor='white')

                # Cambiar color textos de leyenda
                leg = ax.get_legend()
                for text in leg.get_texts():
                    text.set_color("white")

                cols[j].pyplot(fig)


# ==========================================================================================================
# ===================== COMPRA POR CUENTA ======================================
# ==========================================================================================================
#---------------------- GRÁFICO DE BARRAS: COMPRA ANUAL POR CUENTA -------------------------------------------------------
elif opcion == "Compra por Cuenta":
    st.title("Compra Total Anual por Cuenta (2025)")

    # Agrupar monto total por cuenta y sucursal
    df_cta = df_divisiones.groupby(["codigo_normalizado", "sucursal", "division"], as_index=False)["monto"].sum()

    # Crear etiqueta tipo "1234 - Monterrey"
    df_cta["cuenta_sucursal"] = df_cta["codigo_normalizado"] + " - " + df_cta["sucursal"]

    # Ordenar de mayor a menor monto
    df_cta = df_cta.sort_values("monto", ascending=False)

    # Aplicar color por división
    df_cta["color_div"] = df_cta["division"].map(colores_divisiones).fillna("#777777")  # gris por si falta

    fig = px.bar(
        df_cta,
        x="monto",
        y="cuenta_sucursal",
        color="division",
        color_discrete_map=colores_divisiones,
        orientation="h",
        labels={"monto": "Monto", "cuenta_sucursal": "Cuenta - Sucursal", "division": "División"},
        title="Monto Total por Cuenta en 2025",
        text_auto=',.2f'  # añade el monto automáticamente con formato abreviado (puedes usar ',.0f' si prefieres exacto)
    )
    # Ajustes visuales
    fig.update_layout(
        xaxis_title="Monto (MXN)",
        yaxis_title="Cuenta - Sucursal",
        margin=dict(r=70),  # margen derecho suficiente
        template="plotly_dark",
        yaxis={'categoryorder': 'total ascending'},
        height=800,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.15,
            xanchor="center",
            x=0.5
        )
    )
    # Formatear etiquetas de valor
    fig.update_traces(
        text=df_cta["monto"].apply(lambda x: f"${x:,.2f}"),
        textposition="outside", 
        cliponaxis=False  # <-- evita que se recorte el texto
    )

    st.plotly_chart(fig, use_container_width=True)

    #------------------------------ TABLA: COMPRA MENSUAL POR CUENTA: 2025 ---------------------------------------------------
    st.title("Compra mensual por Cuenta (2025)")

    # Agrupar monto total por cuenta y sucursal (no se usa directamente aquí pero puede servir)
    df_cta = df_divisiones.groupby(["codigo_normalizado", "sucursal", "division"], as_index=False)["monto"].sum()

    # Crear cuenta_sucursal en df
    df["cuenta_sucursal"] = df["codigo_normalizado"] + " - " + df["sucursal"]

    # Crear mes_anio y orden_mes en df
    df["mes_anio"] = df["mes_dt"].dt.strftime('%b %Y').str.capitalize()
    df["orden_mes"] = df["mes_dt"].dt.to_period("M")

    # Crear tabla pivote con fill_value para completar con ceros
    tabla_compras = df.pivot_table(
        index="cuenta_sucursal",
        columns="mes_anio",
        values="monto",
        aggfunc="sum",
        fill_value=0
    )

    # Ordenar columnas según orden_mes
    orden_columnas = df.drop_duplicates("mes_anio").sort_values("orden_mes")["mes_anio"].tolist()
    tabla_compras = tabla_compras[orden_columnas]

    # Agregar totales
    tabla_compras["Total Cuenta"] = tabla_compras.sum(axis=1)
    tabla_compras.loc["Total General"] = tabla_compras.sum(axis=0)

    # Cambiar nombre del índice para que se vea mejor el encabezado
    tabla_compras = tabla_compras.rename_axis("Cuenta - Sucursal")

    # Formatear números con comas y dos decimales
    tabla_compras_formateada = tabla_compras.style.format("{:,.2f}")

    # Mostrar tabla con scroll y encabezado fijo (st.dataframe lo maneja)
    st.dataframe(tabla_compras_formateada, use_container_width=True)

    # Crear archivo Excel en memoria para descarga (sin formateo visual, solo valores)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        tabla_compras.to_excel(writer, sheet_name='Compras')
    processed_data = output.getvalue()

    # Botón para descargar Excel
    st.download_button(
        label="📥 Descargar tabla en Excel",
        data=processed_data,
        file_name="compras_por_mes_por_cuenta.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


    #-------------------- GRÁFICO DE LÍNEAS: COMPRAS MENSUALES POR CUENTA --------------------------------------------------------------------------
    # Asegúrate de que la columna mes_dt existe
    if "mes_dt" not in df_divisiones.columns:
        df_divisiones["mes_dt"] = pd.to_datetime(df_divisiones["fecha"]).dt.to_period("M").dt.to_timestamp()

    # ✅ Crear columna mes_anio directamente con nombres completos en español (sin usar abreviaturas)
    df_divisiones["mes_nombre"] = df_divisiones["mes_dt"].dt.month_name().map(meses_es)
    df_divisiones["mes_anio"] = df_divisiones["mes_nombre"] + " " + df_divisiones["mes_dt"].dt.year.astype(str)

    # Crear columna cuenta_sucursal si no existe
    if "cuenta_sucursal" not in df_divisiones.columns:
        df_divisiones["cuenta_sucursal"] = df_divisiones["codigo_normalizado"] + " - " + df_divisiones["sucursal"]

    # Preparar los datos para plotly (long-form)
    df_grafico = df_divisiones.groupby(["mes_anio", "cuenta_sucursal"], as_index=False)["monto"].sum()

    # Definir el orden de los meses en español
    orden_meses = df_divisiones.drop_duplicates("mes_anio").sort_values("mes_dt")["mes_anio"].tolist()

    # Obtener lista de cuentas únicas
    cuentas = df_grafico["cuenta_sucursal"].unique()

    # Crear todas las combinaciones posibles mes-cuenta
    combinaciones = pd.DataFrame(list(itertools.product(orden_meses, cuentas)), columns=["mes_anio", "cuenta_sucursal"])

    # Merge para tener todas las combinaciones y completar montos faltantes con cero
    df_grafico = combinaciones.merge(df_grafico, on=["mes_anio", "cuenta_sucursal"], how="left")
    df_grafico["monto"] = df_grafico["monto"].fillna(0)

    # Convertir mes_anio en categoría ordenada
    df_grafico["mes_anio"] = pd.Categorical(df_grafico["mes_anio"], categories=orden_meses, ordered=True)

    # Ordenar el DataFrame por mes_anio
    df_grafico = df_grafico.sort_values("mes_anio")

    # 🟡 Selector de cuentas
    cuentas_disponibles = sorted(df_grafico["cuenta_sucursal"].unique())
    cuentas_seleccionadas = st.multiselect("Selecciona cuentas a mostrar:", cuentas_disponibles, default=cuentas_disponibles)

    # Filtrar el DataFrame según selección
    df_filtrado = df_grafico[df_grafico["cuenta_sucursal"].isin(cuentas_seleccionadas)]

    # ✅ Mostrar algunos datos si no se ve nada
    if df_filtrado.empty:
        st.warning("No hay datos para mostrar con las cuentas seleccionadas.")
        st.dataframe(df_grafico.head(10))  # Para depuración
    else:
        # Crear gráfico de líneas
        fig = px.line(
            df_filtrado,
            x="mes_anio",
            y="monto",
            color="cuenta_sucursal",
            markers=True,
            title="Compras mensuales por cuenta"
        )

        fig.update_layout(
            xaxis_title="Mes",
            yaxis_title="Monto (MXN)",
            yaxis_tickformat=",",  # Formato con comas
            legend_title="Cuenta - Sucursal"
        )

        config = {
            "scrollZoom": True,
            "modeBarButtonsToKeep": [
                "toImage", "zoom2d", "autoScale2d", "toggleFullscreen"
            ],
            "displaylogo": False
        }

        st.plotly_chart(fig, use_container_width=True, config=config)

    #---------------- GRAFICAS DE BARRAS: COMPRA POR CUENTA POR MES POR SUCURSAL ------------------------------------------------------------------------------
    st.header("Evolución mensual de compras por cuenta")
    if df_divisiones.empty:
        st.warning("No hay datos disponibles.")
    else:
        if "cuenta_sucursal" not in df_divisiones.columns:
            df_divisiones["cuenta_sucursal"] = df_divisiones["codigo_normalizado"] + " - " + df_divisiones["sucursal"]

        df_divisiones["sucursal_nombre"] = df_divisiones["cuenta_sucursal"].str.split(" - ").str[-1]

        # Crear columna mes_nombre en español
        df_divisiones["mes_nombre"] = df_divisiones["mes_dt"].dt.month_name().map(meses_es) + " " + df_divisiones["mes_dt"].dt.year.astype(str)

        # Agrupar por mes_nombre y cuenta_sucursal
        df_barras = df_divisiones.groupby(["mes_nombre", "cuenta_sucursal"], as_index=False)["monto"].sum()

        # Obtener todas las cuentas y meses para asegurar combinaciones completas
        orden_meses = [m for m in orden_meses_desc if pd.notna(m)]
        todas_cuentas = df_divisiones["cuenta_sucursal"].unique()

        # Crear todas las combinaciones posibles mes-cuenta
        idx = pd.MultiIndex.from_product([orden_meses, todas_cuentas], names=["mes_nombre", "cuenta_sucursal"])

        # Reindexar para completar combinaciones faltantes y rellenar con 0
        df_barras = df_barras.set_index(["mes_nombre", "cuenta_sucursal"]).reindex(idx, fill_value=0).reset_index()

        # Agregar columna sucursal_nombre
        df_sucursales = df_divisiones.drop_duplicates("cuenta_sucursal")[["cuenta_sucursal", "sucursal_nombre"]]
        df_barras = df_barras.merge(df_sucursales, on="cuenta_sucursal", how="left")

        # Categorizar mes_nombre para orden correcto
        df_barras["mes_nombre"] = pd.Categorical(df_barras["mes_nombre"], categories=orden_meses, ordered=True)

        for mes in orden_meses:
            df_mes = df_barras[df_barras["mes_nombre"] == mes].copy()

            if df_mes.empty:
                continue

            df_mes = df_mes.sort_values("monto", ascending=False)
            df_mes["cuenta_sucursal"] = pd.Categorical(df_mes["cuenta_sucursal"], categories=df_mes["cuenta_sucursal"], ordered=True)
            df_mes["texto_monto"] = df_mes["monto"].apply(lambda x: f"${x:,.2f}")

            fig = go.Figure()

            for i, row in df_mes.iterrows():
                fig.add_trace(go.Bar(
                    y=[row["cuenta_sucursal"]],
                    x=[row["monto"]],
                    orientation='h',
                    name=row["sucursal_nombre"],
                    marker_color=colores_sucursales.get(row["sucursal_nombre"], "#CCCCCC"),
                    text=row["texto_monto"],
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate=f"{row['cuenta_sucursal']}<br>Monto: $%{{x:,.2f}}<extra></extra>"
                ))

            altura_por_barra = 40
            numero_barras = len(df_mes)
            altura_total = max(600, numero_barras * altura_por_barra)

            fig.update_layout(
                title=f"Compras por Cuenta - {mes}",
                xaxis_title="Monto de compra (MXN)",
                yaxis_title="Cuenta",
                xaxis_tickformat=",",
                legend_title="Sucursal",
                barmode="stack",
                margin=dict(r=70),
                showlegend=False,
                height=altura_total,
                bargap=0.15,
                bargroupgap=0.1
            )

            st.plotly_chart(fig, use_container_width=True)

# ==========================================================================================================
# =========================== COMPRA POR SUCURSAL ======================================
#==========================================================================================================
elif opcion == "Compra por Sucursal":
    st.title("Total de Compras por Mes y Sucursal - 2025")

    #------------------------------------ GRÁFICA DE BARRAS AGRUPADA ---------------------------------------------------------------------------------------
    df_pivot = df.pivot_table(index="mes_nombre", columns="sucursal", values="monto", aggfunc="sum").fillna(0)
    df_pivot = df_pivot.reindex(orden_meses)
    df_percent = df_pivot.div(df_pivot.sum(axis=1), axis=0) * 100

    fig = go.Figure()
    for sucursal in sorted(df_pivot.columns):
        fig.add_trace(go.Bar(
            y=df_percent.index,
            x=df_percent[sucursal],
            orientation='h',
            name=sucursal,
            marker=dict(color=colores_sucursales.get(sucursal)),
            customdata=df_pivot[sucursal],
            text=[
                f"{df_percent.loc[mes, sucursal]:.1f}%<br>${df_pivot.loc[mes, sucursal]:,.0f}"
                if df_pivot.loc[mes, sucursal] > 0 else ""
                for mes in df_percent.index
            ],
            hovertemplate="<b>%{fullData.name}</b><br>%{x:.1f}%<br>$%{customdata:,.0f}<extra></extra>",
            textposition='inside'
        ))
    fig.update_layout(
        barmode='stack',
        title='Distribución porcentual de compras por sucursal (2025)',
        xaxis=dict(title='Porcentaje', ticksuffix='%'),
        yaxis=dict(title='Mes'),
        legend=dict(orientation='h', yanchor='top', y=-0.25, xanchor='center', x=0.5),
        height=650, margin=dict(t=100)
    )
    # Configuración personalizada para scroll + barra de herramientas limpia
    config = {
        "scrollZoom": True,
        "modeBarButtonsToKeep": [
            "toImage",
            "zoom2d",
            "autoScale2d",
            "toggleFullscreen"
        ],
        "displaylogo": False
    }

    # Mostrar gráfica con zoom y opciones de barra
    st.plotly_chart(fig, use_container_width=True, config=config)


    #------------------------------- TABLA: RESUMEN TOTAL POR MES Y SUCURSAL ------------------------------------
    st.markdown("### Resumen total por mes y sucursal")
    tabla = df.pivot_table(
        index="mes_nombre",
        columns="sucursal",
        values="monto",
        aggfunc="sum",
        margins=True,
        margins_name="Total"
    ).fillna(0)

    tabla = tabla.reindex(orden_meses + ["Total"])
    # Cambiar el nombre del índice
    tabla.index.name = "Mes"
    # Formatear valores
    tabla_formateada = tabla.applymap(lambda x: f"{x:,.0f}")
    st.dataframe(tabla_formateada, use_container_width=True)


    # ------------------------- GRÁFICO DE LÍNEAS: EVOLUCIÓN DE COMPRAS POR MES Y SUCURSAL -------------------------------------
    fig_lineas = go.Figure()
    for sucursal in df_pivot.columns:
        fig_lineas.add_trace(go.Scatter(
            x=df_pivot.index,
            y=df_pivot[sucursal],
            mode='lines+markers',
            name=sucursal,
            line=dict(color=colores_sucursales.get(sucursal))
        ))
    fig_lineas.update_layout(
        title="Evolución de Compras por Mes y Sucursal (2025)",
        xaxis_title="Mes",
        yaxis_title="Total Comprado",
        xaxis=dict(tickangle=-45),
        height=500,
        margin=dict(t=60)
    )
    st.plotly_chart(
        fig_lineas,
        use_container_width=True,
        config={
            "scrollZoom": True,
            "modeBarButtonsToKeep": [
                "toImage",
                "zoom2d",
                "autoScale2d",
                "toggleFullscreen"
            ],
            "displaylogo": False
        }
    )

    #------------------------- GRÁFICAS DE BARRAS: COMPRAS POR SUCURSAL, MES A MES  -----------------------------------------------------
    # Obtener mes actual
    mes_actual = datetime.today().month

    # Reordenar los meses empezando por el anterior al mes actual
    mes_inicio = (mes_actual - 1) % 12
    orden_meses_reversa = orden_meses[mes_inicio::-1] + orden_meses[:mes_inicio][::-1]

    st.markdown("### Compras por Sucursal, mes a mes")

    for mes in orden_meses_reversa:
        df_mes = df[df["mes_nombre"] == mes].copy()
        
        # Agrupar solo por sucursal, sumando los montos de todas las divisiones
        df_mes = df_mes.groupby("sucursal", as_index=False).agg({"monto": "sum"})
        
        # Saltar si el mes no tiene compras
        if df_mes["monto"].sum() == 0:
            continue

        total_mes = df_mes["monto"].sum()
        df_mes["porcentaje"] = df_mes["monto"] / total_mes * 100

        df_mes["texto"] = df_mes.apply(
            lambda row: f"${row['monto']:,.0f}<br>({row['porcentaje']:.1f}%)", axis=1
        )

        fig_mes = px.bar(
            df_mes,
            x="sucursal",
            y="monto",
            title=f"Compras en {mes}",
            labels={"monto": "Total Comprado", "sucursal": "Sucursal"},
            color="sucursal",
            color_discrete_map=colores_sucursales,
            text="texto"
        )
        fig_mes.update_traces(
            textposition='inside',
            texttemplate='%{text}',
            hovertemplate=None
        )
        fig_mes.update_layout(showlegend=False)
        st.plotly_chart(fig_mes, use_container_width=True, key=f"bar_{mes}")


# ==========================================================================================================
# ================================ VISTA POR SUCURSAL ====================================
# ==========================================================================================================
elif opcion == "Vista por Sucursal":
    st.title("Vista detallada por Sucursal")

    # Recalcular df_pivot
    df_pivot = df.pivot_table(index="mes_nombre", columns="sucursal", values="monto", aggfunc="sum").fillna(0)
    df_pivot = df_pivot.reindex(orden_meses)

    # ------------------------------- SELECTOR DE SUCURSALES ----------------------------------------------------------------------------------------------------
    sucursales_disponibles = sorted(df["sucursal"].unique())
    sucursales_seleccionadas = st.multiselect("Selecciona una o varias sucursales", options=sucursales_disponibles, default=sucursales_disponibles)
    st.markdown("<br><br>", unsafe_allow_html=True)
    # ----------------------------- TARJETAS: TOTAL ACUMULADO ANUAL Y MES ACTUAL ------------------------------------------------------------------------------------------------------------------
    if sucursales_seleccionadas:  # si hay selección
        df_filtrado = df[df["sucursal"].isin(sucursales_seleccionadas)]
    else:
        df_filtrado = df.copy()  # o un df vacío si quieres no mostrar nada

    total_anual = df_filtrado["monto"].sum()

    ultimo_mes = df_filtrado["mes_dt"].max()

    # Validar si ultimo_mes es NaT
    if pd.isna(ultimo_mes):
        texto_mes = "Sin datos"
        total_mensual = 0
    else:
        mes_en_ingles = ultimo_mes.strftime('%B')
        mes_en_espanol = meses_es.get(mes_en_ingles, mes_en_ingles)
        texto_mes = f"{mes_en_espanol} {ultimo_mes.year}"
        total_mensual = df_filtrado[df_filtrado["mes_dt"] == ultimo_mes]["monto"].sum()


    col1, col2 = st.columns(2)
    col1.metric(label="Total Acumulado Anual (2025)", value=f"${total_anual:,.2f}")
    col2.metric(label=f"Total Acumulado {texto_mes}", value=f"${total_mensual:,.2f}")

    st.title("Evolución mensual de compras por sucursal")
    
    # --------------------------- GRÁFICA DE LÍNEAS (evolución mensual) ------------------------------------------------------------------------------------------------------------------------------
    fig_lineas = go.Figure()
    for sucursal in sucursales_seleccionadas:
        if sucursal in df_pivot.columns:
            fig_lineas.add_trace(go.Scatter(
                x=df_pivot.index,
                y=df_pivot[sucursal],
                mode='lines+markers',
                name=sucursal,
                line=dict(color=colores_sucursales.get(sucursal))
            ))
    fig_lineas.update_layout(
        title="Evolución mensual por sucursal",
        xaxis_title="Mes",
        yaxis_title="Total Comprado"
    )
    st.plotly_chart(
        fig_lineas,
        use_container_width=True,
        config={
            "scrollZoom": True,
            "modeBarButtonsToKeep": [
                "toImage",
                "zoom2d",
                "autoScale2d",
                "toggleFullscreen"
            ],
            "displaylogo": False
        }
    )


    #------------------------------ GRÁFICA DE BARRAS: COMPRAS ACUMULADAS POR CUENTA --------------------------------------------------------------------------------------
    df_filtrado = df[df["sucursal"].isin(sucursales_seleccionadas)]

    # Agrupar por cuenta y sucursal
    df_cta = df_filtrado.groupby(["codigo_normalizado", "sucursal"], as_index=False)["monto"].sum()

    # Crear etiqueta tipo "1234 - Monterrey"
    df_cta["cuenta_sucursal"] = df_cta["codigo_normalizado"] + " - " + df_cta["sucursal"]

    # Ordenar por monto ascendente (para que en horizontal vayan de abajo hacia arriba)
    df_cta = df_cta.sort_values("monto", ascending=True)

    # Abreviar los nombres de sucursales a 3 letras solo para la leyenda
    df_cta["sucursal_abrev"] = df_cta["sucursal"].apply(lambda x: x[:3].capitalize())

    if not df_cta.empty:
        st.markdown("### Compras acumuladas por cuenta (anual)")

        fig = px.bar(
            df_cta,
            x="monto",
            y="cuenta_sucursal",
            orientation="h",
            color="sucursal_abrev",  # 👈 usamos el campo abreviado
            color_discrete_map={k[:3].capitalize(): v for k, v in colores_sucursales.items()},
            labels={
                "monto": "Monto (MXN)",
                "cuenta_sucursal": "Cuenta - Sucursal",
                "sucursal_abrev": "Sucursal"
            },
            text=df_cta["monto"].apply(lambda x: f"${x:,.2f}")
        )
        altura_grafica = max(300, min(50 * len(df_cta), 1000))

        fig.update_traces(
            textposition="outside",
            cliponaxis=False
        )

        fig.update_layout(
            xaxis_title="Monto (MXN)",
            yaxis_title="Cuenta - Sucursal",
            yaxis={"categoryorder": "total ascending"},
            height=altura_grafica,
            margin=dict(r=70, b=30),  # 👈 margen inferior más reducido
            showlegend=False  # 👈 quita la leyenda de colores
        )
        st.plotly_chart(fig, use_container_width=True)

    
    #=================== GRAFICA DE BARRAS DE MONTO POR MES Y CUENTA ========================

    # Validar selección
    if not sucursales_seleccionadas:
        st.warning("Selecciona al menos una sucursal para ver esta gráfica.")
    else:
        # Filtrar por sucursales seleccionadas
        df_filtrado = df[df["sucursal"].isin(sucursales_seleccionadas)].copy()

        # Crear etiqueta cuenta_sucursal
        df_filtrado["cuenta_sucursal"] = df_filtrado["codigo_normalizado"] + " - " + df_filtrado["sucursal"]

        # Agrupar por mes y cuenta_sucursal, sumando monto
        df_mes_cta = df_filtrado.groupby(["mes_nombre", "cuenta_sucursal", "sucursal", "division"])["monto"].sum().reset_index()

        # Ordenar meses según orden_meses
        df_mes_cta["mes_nombre"] = pd.Categorical(df_mes_cta["mes_nombre"], categories=orden_meses, ordered=True)
        df_mes_cta = df_mes_cta.sort_values("mes_nombre")

        # Mostrar texto solo si seleccionó menos sucursales que las disponibles
        mostrar_texto = len(sucursales_seleccionadas) < len(sucursales_disponibles)

        # Definir colores y variable de color según cantidad de sucursales seleccionadas
        if len(sucursales_seleccionadas) == 1:
            # Colorear según división
            color_columna = "division"
            color_mapa = colores_divisiones  # asumo que tienes este dict definido con colores por división
        else:
            # Colorear según sucursal
            color_columna = "sucursal"
            color_mapa = colores_sucursales

        def es_color_claro(hex_color):
            """Devuelve True si el color es claro, False si es oscuro."""
            try:
                r, g, b = mcolors.to_rgb(hex_color)
                brillo = (r * 299 + g * 587 + b * 114) / 1000
                return brillo > 0.6
            except Exception:
                return False  # color inválido, lo tratamos como oscuro

        # Calcular porcentaje y texto
        df_mes_cta["total_mes"] = df_mes_cta.groupby("mes_nombre")["monto"].transform("sum")
        df_mes_cta["porcentaje"] = df_mes_cta["monto"] / df_mes_cta["total_mes"] * 100
        df_mes_cta["texto_monto"] = df_mes_cta.apply(lambda row: f"${row['monto']:,.0f} ({row['porcentaje']:.1f}%)", axis=1)

        fig = go.Figure()

        # Crear trazas para cada grupo (sucursal o división)
        for valor in df_mes_cta[color_columna].unique():
            df_grupo = df_mes_cta[df_mes_cta[color_columna] == valor]
            fig.add_trace(go.Bar(
                x=df_grupo["monto"],
                y=df_grupo["mes_nombre"],
                orientation="h",
                name=valor,
                marker=dict(color=color_mapa.get(valor, "#999999")),
                text=df_grupo["texto_monto"] if mostrar_texto else None,
                textposition="inside" if mostrar_texto else "none",
                insidetextanchor="start",
                hovertemplate="<b>%{customdata[0]}</b><br>Monto: $%{x:,.2f}<br>Porcentaje: %{customdata[1]:.1f}%<extra></extra>",
                customdata=df_grupo[["cuenta_sucursal", "porcentaje"]]
            ))

        # Layout
        fig.update_layout(
            barmode="stack",
            height=max(300, min(70 * len(df_mes_cta["mes_nombre"].unique()), 800)),
            xaxis_title="Monto (MXN)",
            yaxis_title="Mes",
            xaxis_tickformat=",",  # ← importante también para ejes
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.3,
                xanchor="center",
                x=0.5,
                title=None
            )
        )


        if mostrar_texto:
            colores_barras = df_mes_cta[color_columna].map(color_mapa).fillna("#666666")
            colores_texto = colores_barras.apply(lambda c: "black" if es_color_claro(c) else "white")
            df_mes_cta["color_texto"] = colores_texto.values

            for trace in fig.data:
                barras_colores_texto = df_mes_cta[df_mes_cta[color_columna] == trace.name]["color_texto"].tolist()
                trace.textfont = dict(color=barras_colores_texto)
                trace.textposition = "inside"
                trace.insidetextanchor = "middle"
                trace.marker.line.width = 1
                trace.marker.line.color = "black"
        else:
            for trace in fig.data:
                trace.text = None
                trace.marker.line.width = 1
                trace.marker.line.color = "black"

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "scrollZoom": True,
                "modeBarButtonsToKeep": [
                    "zoom2d",        # Zoom con caja
                    "zoomIn2d",      # Zoom +
                    "zoomOut2d",     # Zoom -
                    "autoScale2d",   # Reset zoom
                    "pan2d",         # Pan (mover)
                    "toImage",       # Descargar imagen
                    "toggleSpikelines", # Líneas guía al pasar mouse (opcional)
                    "toggleFullscreen"
                ],
                "displaylogo": False
            }
        )

    # ============================== GRÁFICA DE BARRAS POR SUCURSAL ==============================================================================================
    if len(sucursales_seleccionadas) == 1:
        sucursal = sucursales_seleccionadas[0]
        df_suc = df[df["sucursal"] == sucursal].copy()
        df_suc = df_suc.groupby(["mes_nombre", "mes_dt"], as_index=False).agg({"monto": "sum"})
        df_suc = df_suc.sort_values("mes_dt", ascending=False)  # orden descendente
        df_suc["texto"] = df_suc["monto"].apply(lambda x: f"${x:,.0f}")

        fig_barras = px.bar(
            df_suc,
            x="mes_nombre",
            y="monto",
            text="texto",
            color_discrete_sequence=[colores_sucursales.get(sucursal, "#636EFA")],
            title=f"Compras mensuales de {sucursal} en 2025"
        )
        fig_barras.update_traces(textposition='inside', texttemplate='%{text}')
        fig_barras.update_layout(showlegend=False, xaxis_title="Mes", yaxis_title="Total Comprado")
        st.plotly_chart(fig_barras, use_container_width=True)
    else:
        st.markdown("### Compras por Sucursal, mes a mes")
        for mes in orden_meses_desc:  # <- aquí el cambio para orden descendente
            df_mes = df[df["mes_nombre"] == mes]
            df_mes = df_mes[df_mes["sucursal"].isin(sucursales_seleccionadas)].copy()
            df_mes = df_mes.groupby("sucursal", as_index=False).agg({"monto": "sum"})
            total_mes = df_mes["monto"].sum()
            if total_mes == 0:
                continue
            df_mes["porcentaje"] = df_mes["monto"] / total_mes * 100
            df_mes["texto"] = df_mes.apply(lambda row: f"${row['monto']:,.0f}<br>({row['porcentaje']:.1f}%)", axis=1)
            df_mes = df_mes.sort_values("monto", ascending=False)
            df_mes["sucursal"] = pd.Categorical(df_mes["sucursal"], categories=df_mes["sucursal"], ordered=True)

            fig_mes = px.bar(
                df_mes,
                x="sucursal",
                y="monto",
                text="texto",
                color="sucursal",
                color_discrete_map=colores_sucursales,
                title=f"Compras en {mes}"
            )
            fig_mes.update_traces(textposition='inside', texttemplate='%{text}')
            fig_mes.update_layout(showlegend=False)
            st.plotly_chart(fig_mes, use_container_width=True, key=f"mes_{mes}")



# ==========================================================================================================
# ================================ ESTADO DE LIGADO ========================================
# ==========================================================================================================
elif opcion == "Estado de Ligado":
    st.title("Estado de Ligado de Facturas")
    # ----------- Información General - Estado de Ligado  (TARJETAS) -----------
    st.markdown("### Información general")
    # Filtramos el dataframe para obtener totales según el ligado_sistema
    monto_ligado = df[df["ligado_sistema"] == 1]["monto"].sum()
    monto_pendiente = df[df["ligado_sistema"] == 0]["monto"].sum()
    # Mostramos en tarjetas
    col1, col2 = st.columns(2)

    with col1:
        st.metric("✅ Total ligado en sistema", f"${monto_ligado:,.2f}")

    with col2:
        st.metric("🕒 Pendiente de ligar", f"${monto_pendiente:,.2f}")

    # ---------------- FILTRAR FACTURAS NO LIGADAS (GRAFICO DE LÍNEAS) ---------------------------------------------
    df_no_ligado = df[df["ligado_sistema"] == 0]

    # Agrupar por mes
    monto_mensual_no_ligado = df_no_ligado.groupby("mes_nombre")["monto"].sum().reindex(orden_meses)

    # --- GRÁFICO ---
    st.subheader("Monto mensual sin ligar")
    fig = px.line(
        monto_mensual_no_ligado,
        x=monto_mensual_no_ligado.index,
        y=monto_mensual_no_ligado.values,
        labels={"x": "Mes", "y": "Monto sin ligar"},
        markers=True,
    )
    fig.update_layout(xaxis_title="Mes", yaxis_title="Monto sin ligar", title="Tendencia mensual de facturas no ligadas")
    st.plotly_chart(fig, use_container_width=True)

    # --- ---------CANTIDAD SIN LIGAR MENSUAL POR SUCURSAL (GRAFICO DE BARRAS APILADAS) -----------------------------------------------
    # Filtrar solo facturas sin ligar
    df_no_ligado = df[df["ligado_sistema"] == 0].copy()

    # Asegurarnos que mes_dt exista y sea datetime
    if "mes_dt" not in df_no_ligado.columns:
        df_no_ligado["mes_dt"] = pd.to_datetime(df_no_ligado["mes"].astype(str))

    # Obtener el mes actual (en formato periodo M)
    mes_actual = pd.to_datetime("today").to_period("M")

    # Agrupar monto por mes_nombre, sucursal y mes_dt (fecha)
    monto_por_mes_sucursal = df_no_ligado.groupby(
        ["mes_nombre", "sucursal", "mes_dt"]
    )["monto"].sum().reset_index()

    # Filtrar para excluir mes actual y posteriores
    monto_por_mes_sucursal = monto_por_mes_sucursal[
        monto_por_mes_sucursal["mes_dt"].dt.to_period("M") < mes_actual
    ]

    # Crear orden correcto solo con los meses filtrados
    meses_filtrados = [m for m in orden_meses if m in monto_por_mes_sucursal["mes_nombre"].unique()]
    monto_por_mes_sucursal["mes_nombre"] = pd.Categorical(
        monto_por_mes_sucursal["mes_nombre"],
        categories=meses_filtrados,
        ordered=True
    )

    # Ordenar DataFrame por fecha para que Plotly respete el orden cronológico
    monto_por_mes_sucursal = monto_por_mes_sucursal.sort_values("mes_dt")

    # Crear gráfico de barras apiladas horizontales
    fig = px.bar(
        monto_por_mes_sucursal,
        x="monto",
        y="mes_nombre",
        color="sucursal",
        orientation="h",
        title="Distribución mensual del monto sin ligar por sucursal",
        labels={"monto": "Monto sin ligar", "mes_nombre": "Mes"},
        category_orders={"mes_nombre": meses_filtrados}  # <- esto fuerza el orden
    )


    fig.update_layout(
        barmode="stack",
        xaxis_title="Monto sin ligar",
        yaxis_title="Mes"
    )

    #fig.update_traces(marker_line_width=1, marker_line_color='white')

    st.plotly_chart(fig, use_container_width=True)

    #------------- TABLA ------------------------------
    tabla_resumen = monto_por_mes_sucursal.pivot_table(
        index="mes_nombre",
        columns="sucursal",
        values="monto",
        aggfunc="sum",
        fill_value=0
    )

    # Ordenar los meses correctamente
    tabla_resumen = tabla_resumen.reindex(meses_filtrados)

    # Función para aplicar estilo condicional: pintar rojo si el valor es distinto de 0
    def resaltar_valores(val):
        color = 'background-color: #BC13FE' if val != 0 else ''
        return color

    # Mostrar en Streamlit con estilo
    st.subheader("Tabla resumen del monto sin ligar por mes y sucursal")
    st.dataframe(tabla_resumen.style
        .applymap(resaltar_valores)
        .format("${:,.2f}")
    )


# ==========================================================================================================
# ============================== ESTADO DE CUENTA ==========================================
# ==========================================================================================================
elif opcion == "Estado de cuenta":
    st.title("Cuadro de estado de cuenta")
    
    df_estado_cuenta, fecha_corte = obtener_estado_cuenta_api()
    if df_estado_cuenta.empty or fecha_corte is None:
        st.warning("No hay datos de estado de cuenta.")
    else:
        st.markdown(f"### Estado de cuenta actualizado a {fecha_corte.strftime('%d/%m/%Y')}")
        #----------------------------------------- TARJETAS -------------------------------------------------------------------
        df_estado_cuenta["fecha_exigibilidad"] = pd.to_datetime(df_estado_cuenta["fecha_exigibilidad"])
        hoy = pd.to_datetime(datetime.today().date())
        
        total_vencido = df_estado_cuenta[df_estado_cuenta["fecha_exigibilidad"] < hoy]["total"].sum()
        por_vencer_30 = df_estado_cuenta[
            (df_estado_cuenta["fecha_exigibilidad"] >= hoy) &
            (df_estado_cuenta["fecha_exigibilidad"] <= hoy + timedelta(days=30))
        ]["total"].sum()
        por_vencer_90 = df_estado_cuenta[
            df_estado_cuenta["fecha_exigibilidad"] > hoy + timedelta(days=90)
        ]["total"].sum()
        
        col1, col2, col3 = st.columns(3)
        col1.metric("🔴 Total vencido", f"${total_vencido:,.2f}")
        col2.metric("🟡 Por vencer en 30 días", f"${por_vencer_30:,.2f}")
        col3.metric("🟢 Por vencer >90 días", f"${por_vencer_90:,.2f}")

        #------------------------------------------ TABLA -----------------------------------------------------------------------
        df_estado_cuenta["fecha_exigibilidad"] = pd.to_datetime(df_estado_cuenta["fecha_exigibilidad"])
        df_estado_cuenta["fecha_exigibilidad_str"] = df_estado_cuenta["fecha_exigibilidad"].dt.strftime("%d/%m/%Y")
        
        df_pivot = df_estado_cuenta.pivot_table(
            index=["sucursal", "codigo_6digitos"],
            columns="fecha_exigibilidad_str",
            values="total",
            aggfunc="sum",
            fill_value=0,
            margins=True,
            margins_name="Total"
        )
        # Ordenar columnas por fecha real (aunque están en formato string)
        cols_ordenadas = sorted(
            [col for col in df_pivot.columns if col != "Total"],
            key=lambda x: datetime.strptime(x, "%d/%m/%Y")
        )

        # Añadir la columna 'Total' al final
        if "Total" in df_pivot.columns:
            cols_ordenadas.append("Total")

        # Reordenar columnas del pivot
        df_pivot = df_pivot[cols_ordenadas]
        df_pivot.index = df_pivot.index.set_names(["sucursal", "codigo"])
        df_pivot_reset = df_pivot.reset_index()
        numeric_cols = df_pivot_reset.select_dtypes(include="number").columns.tolist()
        # Asegura que todas las columnas excepto el índice sean numéricas
        #cols_to_format = df_pivot.columns
        #df_pivot[cols_to_format] = df_pivot[cols_to_format].apply(pd.to_numeric, errors='coerce')
        df_pivot_reset[numeric_cols] = df_pivot_reset[numeric_cols].applymap(lambda x: f"{x:,.2f}")

        # Mostrar con formato correcto
        st.data_editor(
            df_pivot_reset,
            use_container_width=True,
            hide_index=True,
            disabled=True,  # ❌ Desactiva edición y ordenamiento
            column_config={
                "sucursal": st.column_config.Column(label="Sucursal", width="small", pinned="left"),
                "codigo": st.column_config.Column(label="Código", width="small", pinned="left"),
            },
            column_order=["sucursal", "codigo"] + cols_ordenadas  # Asegura orden correcto
        )


        #--------------------- BOTON DE DESCARGA --------------------------------------
        def to_excel(df):
            import io
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='EstadoCuenta')
            return output.getvalue()
        
        excel_data = to_excel(df_pivot)
        st.download_button(
            label="Descargar tabla en Excel",
            data=excel_data,
            file_name=f"estado_cuenta_{fecha_corte.strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        #------------------------------------------------------------------------------------------------------------
        

# =============================
