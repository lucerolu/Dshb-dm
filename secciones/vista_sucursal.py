import streamlit as st
import plotly.express as px
import json
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import io
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
from utils.api_utils import obtener_datos_api
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.colors as mcolors
from matplotlib.colors import LinearSegmentedColormap

def mostrar(df_filtrado, config):
    st.title("Vista por Sucursal")
    
    if df_filtrado.empty:
        st.warning("No hay datos para mostrar.")
        return
    
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
    
    with open("config_colores.json", "r", encoding="utf-8") as f:
        config = json.load(f)
    colores_divisiones = {k: v["color"] for k, v in config["divisiones"].items()}
    colores_sucursales = config["sucursales"]

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

    # Asignar división
    df_filtrado["division"] = df_filtrado["codigo_normalizado"].map(mapa_codigos)

    # Filtrar válidos
    df_divisiones = df_filtrado.dropna(subset=["division"]).copy()

    # Agregar columnas de fecha/mes
    df_divisiones["mes_dt"] = pd.to_datetime(df_divisiones["mes"])
    df_divisiones["mes_nombre"] = (
        df_divisiones["mes_dt"].dt.month_name().map(meses_es)
        + " "
        + df_divisiones["mes_dt"].dt.year.astype(str)
    )

    # Diccionario plano solo con colores por sucursal
    colores_sucursales_map = {
        suc: data["color"] for suc, data in colores_sucursales.items()
    }
    
    # Tabla detallada por sucursal
    st.dataframe(df_filtrado.sort_values(["sucursal", "mes_dt"]))

    st.title("Vista detallada por Sucursal")

    # ----------------- Selector de periodo compacto -----------------
    opciones_periodo = ["Año Natural", "Año Fiscal"]
    periodo = st.radio("Selecciona periodo", opciones_periodo, horizontal=True)

    # Detectar años disponibles
    df_filtrado["fecha"] = pd.to_datetime(df_filtrado["mes"])  # asegúrate de tener columna 'mes' en formato fecha
    años_disponibles = sorted(df_filtrado["fecha"].dt.year.unique())
    año_seleccionado = st.selectbox("Selecciona el año", años_disponibles, index=len(años_disponibles)-1)

    # Filtrar por periodo
    if periodo == "Año Natural":
        df_filtrado = df_filtrado[df_filtrado["fecha"].dt.year == año_seleccionado]
        titulo_periodo = f"{año_seleccionado}"

    elif periodo == "Año Fiscal":
        # Año fiscal: 1 nov (año_seleccionado-1) -> 31 oct (año_seleccionado)
        inicio_fiscal = pd.Timestamp(año_seleccionado-1, 11, 1)
        fin_fiscal = pd.Timestamp(año_seleccionado, 10, 31)
        df_filtrado = df_filtrado[(df_filtrado["fecha"] >= inicio_fiscal) & (df_filtrado["fecha"] <= fin_fiscal)]
        titulo_periodo = f"Fiscal {año_seleccionado}"
    st.markdown("<br><br>", unsafe_allow_html=True)
    # Usar df_filtrado en lugar del df original
    df_divisiones_filtrado = df_filtrado.dropna(subset=["division"])

    # Recalcular df_pivot
    df_pivot = df_filtrado.pivot_table(index="mes_nombre", columns="sucursal", values="monto", aggfunc="sum").fillna(0)
    df_pivot = df_pivot.reindex(orden_meses)

    # ------------------------------- SELECTOR DE SUCURSALES ----------------------------------------------------------------------------------------------------
    sucursales_disponibles = sorted(df["sucursal"].unique())

    # Agregar opción "Todas" al inicio
    opciones_multiselect = ["Todas"] + sucursales_disponibles

    sucursales_seleccionadas = st.multiselect(
        "Selecciona una o varias sucursales",
        options=opciones_multiselect,
        default=["Todas"]
    )

    # Si selecciona "Todas", reemplazar por todas las sucursales reales
    if "Todas" in sucursales_seleccionadas:
        sucursales_seleccionadas = sucursales_disponibles
    st.markdown("<br><br>", unsafe_allow_html=True)    
    # ----------------------------- TARJETAS: TOTAL ACUMULADO ANUAL Y MES ACTUAL ------------------------------------------------------------------------------------------------------------------
    if sucursales_seleccionadas:  # si hay selección
        df_filtrado = df_filtrado[df_filtrado["sucursal"].isin(sucursales_seleccionadas)]
    else:
        df_filtrado = df_filtrado.copy()  # o un df vacío si quieres no mostrar nada

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
    
    # Crear pivot table solo con df_filtrado (periodo + sucursales)
    df_pivot = df_filtrado.pivot_table(
        index="mes_nombre",
        columns="sucursal",
        values="monto",
        aggfunc="sum"
    ).fillna(0)

    # Reordenar los meses según orden_meses pero solo los que existen en df_pivot
    meses_existentes = [m for m in orden_meses if m in df_pivot.index]
    df_pivot = df_pivot.reindex(meses_existentes)

    # Crear gráfico
    fig_lineas = go.Figure()

    for sucursal in sucursales_seleccionadas:
        if sucursal in df_pivot.columns:
            # Crear customdata con mes y sucursal para cada punto
            customdata = list(zip(df_pivot.index.astype(str), [sucursal]*len(df_pivot)))
            
            fig_lineas.add_trace(go.Scatter(
                x=df_pivot.index,
                y=df_pivot[sucursal],
                mode='lines+markers',
                name=sucursal,
                line=dict(color=colores_sucursales_map.get(sucursal, "#CCC")),
                customdata=customdata,
                hovertemplate=(
                    "<b>Sucursal:</b> %{customdata[1]}<br>" +
                    "<b>Mes:</b> %{customdata[0]}<br>" +
                    "<b>Monto:</b> $%{y:,.2f}<extra></extra>"
                )
            ))

    # Layout
    fig_lineas.update_layout(
        title=f"Evolución mensual por sucursal ({titulo_periodo})",
        xaxis_title="Mes",
        yaxis_title="Total Comprado",
        height=600,
        margin=dict(t=100)
    )

    # Mostrar gráfico
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
    # Filtrar df_filtrado también por sucursales seleccionadas
    df_cta_filtrado = df_filtrado[df_filtrado["sucursal"].isin(sucursales_seleccionadas)].copy()

    # Función para obtener abreviatura
    def obtener_abreviatura(codigo):
        codigo_str = str(codigo).strip()
        for division, info in divisiones.items():
            if codigo_str in info["codigos"]:
                return info["abreviatura"]
        return ""

    df_cta_filtrado["abreviatura"] = df_cta_filtrado["codigo_normalizado"].apply(obtener_abreviatura)

    # Agrupar por cuenta y sucursal
    df_cta = df_cta_filtrado.groupby(
        ["codigo_normalizado", "sucursal", "abreviatura"], as_index=False
    )["monto"].sum()

    # Crear etiqueta con abreviatura incluida
    df_cta["cuenta_sucursal"] = (
        df_cta["codigo_normalizado"].astype(str) + " (" +
        df_cta["abreviatura"] + ") - " +
        df_cta["sucursal"]
    )

    # Ordenar
    df_cta = df_cta.sort_values("monto", ascending=True)

    # Abreviar sucursal para leyenda
    df_cta["sucursal_abrev"] = df_cta["sucursal"].apply(lambda x: x[:3].capitalize())
    color_discrete_map = {k[:3].capitalize(): v for k, v in colores_sucursales_map.items()}

    # 2️⃣ Crear gráfico con hovertemplate personalizado
    if not df_cta.empty:
        st.markdown("### Compras acumuladas por cuenta (anual)")
        
        fig = px.bar(
            df_cta,
            x="monto",
            y="cuenta_sucursal",
            orientation="h",
            color="sucursal_abrev",
            color_discrete_map=color_discrete_map,
            labels={
                "monto": "Monto (MXN)",
                "cuenta_sucursal": "Cuenta - Sucursal",
                "sucursal_abrev": "Sucursal"
            },
            text=df_cta["monto"].apply(lambda x: f"${x:,.2f}"),
            custom_data=["sucursal", "abreviatura", "monto"]
        )

        altura_grafica = max(300, min(50 * len(df_cta), 1000))

        fig.update_traces(
            textposition="outside",
            cliponaxis=False,
            hovertemplate=(
                "<b>Sucursal:</b> %{customdata[0]}<br>"
                "<b>División:</b> %{customdata[1]}<br>"
                "<b>Monto:</b> $%{customdata[2]:,.2f}<extra></extra>"
            )
        )

        fig.update_layout(
            xaxis_title="Monto (MXN)",
            yaxis_title="Cuenta - Sucursal",
            yaxis={"categoryorder": "total ascending"},
            height=altura_grafica,
            margin=dict(r=70, b=30),
            showlegend=False
        )

        st.plotly_chart(fig, use_container_width=True)
        st.markdown("<br><br>", unsafe_allow_html=True)

    #=================== GRAFICA DE BARRAS APILADAS DE MONTO POR MES Y CUENTA ========================
    # Validar selección
    if not sucursales_seleccionadas:
        st.warning("Selecciona al menos una sucursal para ver esta gráfica.")
    else:
        st.markdown("### Compras por Sucursal, mes a mes")
        # Filtrar por sucursales seleccionadas
        df_filtrado = df_filtrado[df_filtrado["sucursal"].isin(sucursales_seleccionadas)].copy()

        # Crear etiqueta cuenta_sucursal
        df_filtrado["cuenta_sucursal"] = df_filtrado["codigo_normalizado"] + " - " + df_filtrado["sucursal"]

        # Agregar abreviatura de la división
        df_filtrado["abreviatura"] = df_filtrado["codigo_normalizado"].apply(obtener_abreviatura)

        # Crear columna con cuenta-sucursal-abreviatura
        df_filtrado["cuenta_sucursal_abrev"] = (
            df_filtrado["codigo_normalizado"].astype(str) + " (" +
            df_filtrado["abreviatura"] + ") - " +
            df_filtrado["sucursal"]
        )

        # Agrupar por mes y cuenta_sucursal_abrev (en lugar de la columna anterior)
        df_mes_cta = df_filtrado.groupby(
            ["mes_nombre", "cuenta_sucursal_abrev", "sucursal", "division"], as_index=False
        )["monto"].sum()

        # Ordenar meses según orden_meses
        df_mes_cta["mes_nombre"] = pd.Categorical(df_mes_cta["mes_nombre"], categories=orden_meses, ordered=True)
        df_mes_cta = df_mes_cta.sort_values("mes_nombre")

        # Mostrar texto solo si seleccionó menos sucursales que las disponibles
        mostrar_texto = len(sucursales_seleccionadas) < len(sucursales_disponibles)

        # Definir colores y variable de color según cantidad de sucursales seleccionadas
        if len(sucursales_seleccionadas) == 1:
            # Colorear según división
            color_columna = "division"
            color_mapa = colores_divisiones  # ← este sí debería ser plano {division: "#hex"}
        else:
            # Colorear según sucursal
            color_columna = "sucursal"
            color_mapa = colores_sucursales_map  # ← usa el plano, no el anidado

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
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"  # ← ahora cuenta-sucursal-abreviatura
                    "<b>Monto:</b> $%{x:,.2f}<br>"
                    "<b>Porcentaje:</b> %{customdata[1]:.1f}%<extra></extra>"
                ),
                customdata=df_grupo[["cuenta_sucursal_abrev", "porcentaje"]]
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
        df_suc = df_filtrado[df_filtrado["sucursal"] == sucursal].copy()

        # Agrupamos y ordenamos
        df_suc = df_suc.groupby(["mes_nombre", "mes_dt"], as_index=False).agg({"monto": "sum"})
        df_suc = df_suc.sort_values("mes_dt", ascending=False)

        # Crear columnas auxiliares
        df_suc["texto"] = df_suc["monto"].apply(lambda x: f"${x:,.0f}")
        df_suc["porcentaje"] = 100  

        # 👀 DEBUG
        #st.write("📊 DataFrame para gráfico de una sucursal:", df_suc)
        colores_sucursales_map = {k: v["color"] for k, v in colores_sucursales.items()}

        if not df_suc.empty:
            df_suc["sucursal"] = sucursal  # columna fija
            fig_barras = px.bar(
                df_suc,
                x="mes_nombre",
                y="monto",
                text="texto",
                #color_discrete_sequence=[colores_sucursales.get(sucursal, "#636EFA")],
                title=f"Compras mensuales de {sucursal} en {titulo_periodo}"
            )

            fig_barras.update_traces(
                textposition='inside',
                texttemplate='%{text}',
                hovertemplate=(
                    "<b>Sucursal:</b> " + sucursal + "<br>"
                    "<b>Monto:</b> $%{y:,.2f}<extra></extra>"
                ),
                customdata=df_suc[["porcentaje"]]
            )

            fig_barras.update_layout(showlegend=False, xaxis_title="Mes", yaxis_title="Total Comprado")
            st.plotly_chart(fig_barras, use_container_width=True)
    else:
        for mes in orden_meses_desc:  # <- aquí el cambio para orden descendente
            df_mes = df_filtrado[df_filtrado["mes_nombre"] == mes].copy()
            df_mes = df_mes[df_mes["sucursal"].isin(sucursales_seleccionadas)].copy()
            df_mes = df_mes.groupby("sucursal", as_index=False).agg({"monto": "sum"})
            total_mes = df_mes["monto"].sum()
            if total_mes == 0:
                continue
            df_mes["porcentaje"] = df_mes["monto"] / total_mes * 100
            df_mes["texto"] = df_mes.apply(lambda row: f"${row['monto']:,.0f}<br>({row['porcentaje']:.1f}%)", axis=1)
            df_mes = df_mes.sort_values("monto", ascending=False)
            df_mes["sucursal"] = pd.Categorical(df_mes["sucursal"], categories=df_mes["sucursal"], ordered=True)
            # Plano para plotly
            colores_sucursales_map = {k: v["color"] for k, v in colores_sucursales.items()}

            fig_mes = px.bar(
                df_mes,
                x="sucursal",
                y="monto",
                text="texto",
                color="sucursal",
                color_discrete_map=colores_sucursales_map,
                title=f"Compras en {mes}"
            )

            fig_mes.update_traces(
                textposition='inside',
                texttemplate='%{text}',
                hovertemplate=(
                    "<b>Sucursal:</b> %{x}<br>"
                    "<b>Porcentaje:</b> %{customdata[0]:.1f}%<br>"
                    "<b>Monto:</b> $%{y:,.2f}<extra></extra>"
                ),
                customdata=df_mes[["porcentaje"]]
            )

            fig_mes.update_traces(textposition='inside', texttemplate='%{text}')
            fig_mes.update_layout(showlegend=False)
            st.plotly_chart(fig_mes, use_container_width=True, key=f"mes_{mes}")