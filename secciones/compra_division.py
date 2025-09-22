import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.ticker as mtick
import json
from datetime import datetime
from utils.api_utils import obtener_datos_api


def mostrar(df_filtrado, config):
    st.title("Compra por División")
    
    if df_filtrado.empty:
        st.warning("No hay datos para mostrar.")
        return
    
    with open("config_colores.json", "r", encoding="utf-8") as f:
        config = json.load(f)
    colores_divisiones = {k: v["color"] for k, v in config["divisiones"].items()}

    orden_meses_asc = (
        df_filtrado.drop_duplicates(subset="mes_period")
        .sort_values("mes_period", ascending=True)["mes_nombre"]
        .tolist()
    )

    # Orden descendente (para gráficas que van de mes más reciente al más antiguo)
    orden_meses_desc = orden_meses_asc[::-1]
    orden_meses = orden_meses_asc

    # ================================================================================================================================
    # ============================================= COMPRA POR DIVISION ==================================================================
    # ================================================================================================================================
    st.title("Distribución de Compras por División - 2025")
    # ----------------- Selector de periodo compacto -----------------
    opciones_periodo = ["Año Natural", "Año Fiscal"]
    periodo = st.radio("Selecciona periodo", opciones_periodo, horizontal=True)

    # Detectar años disponibles
    df_filtrado["fecha"] = pd.to_datetime(df_filtrado["mes"])  # asegúrate de tener columna 'mes' en formato fecha
    años_disponibles = sorted(df_filtrado["fecha"].dt.year.unique())
    año_seleccionado = st.selectbox("Selecciona el año", años_disponibles, index=len(años_disponibles)-1)
    st.markdown("<br><br>", unsafe_allow_html=True)

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

    #------------------------- GRÁFICO DE PASTEL ---------------------------------------------------------
    df_agrupado = df_divisiones_filtrado.groupby("division")["monto"].sum().reset_index()

    fig_pie = px.pie(
        df_agrupado,
        values="monto",
        names="division",
        color="division",
        color_discrete_map=colores_divisiones,
        hole=0.4
    )

    fig_pie.update_traces(
        textinfo="percent+label",
        textposition="inside",
        hovertemplate=(
            "<b>División:</b> %{label}<br>"
            "<b>Monto:</b> $%{value:,.2f}<br>"
            "<b>Porcentaje:</b> %{percent}<extra></extra>"
        )
    )

    fig_pie.update_layout(
        height=500,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.2,
            xanchor="center",
            x=0.5
        )
    )

    # 👇 Título con Markdown y menos espacio debajo
    st.markdown("### Distribución del total anual comprado por División")
    st.markdown("<div style='margin-top:-10px'></div>", unsafe_allow_html=True)

    st.plotly_chart(fig_pie, use_container_width=True)

    # ------------------------- TARJETAS: TOTAL COMPRADO POR DIVISIÓN ------------------------------
    st.markdown("<br><br>", unsafe_allow_html=True)
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
        custom_data=["division", "porcentaje"],  # ← para usar en hovertemplate
        color_discrete_map=colores_divisiones,
        labels={"monto": "Monto Comprado", "division": "División"}
    )

    fig_bar.update_traces(
        textposition="inside",
        texttemplate="%{text}",
        hovertemplate=(
            "<b>División:</b> %{customdata[0]}<br>"
            "<b>Monto:</b> $%{y:,.2f}<br>"
            "<b>Porcentaje:</b> %{customdata[1]:.1f}%<extra></extra>"
        )
    )

    fig_bar.update_layout(
        showlegend=False
    )

    # 👇 Título con Markdown y menos espacio debajo
    st.markdown("### Monto total anual por División")
    st.markdown("<div style='margin-top:-10px'></div>", unsafe_allow_html=True)

    st.plotly_chart(fig_bar, use_container_width=True)

    # ---------------- TABLA: TOTAL MENSUAL COMPRADO POR DIVISIÓN ---------------------------------------------------------------------------
    # Crear tabla pivote
    tabla_pivot = df_divisiones_filtrado.pivot_table(
        index="division",
        columns="mes_nombre",
        values="monto",
        aggfunc="sum",
        fill_value=0
    )

    # Reordenar columnas según el orden cronológico (solo las que existan)
    meses_validos = [m for m in orden_meses if m in tabla_pivot.columns]
    tabla_pivot = tabla_pivot[meses_validos]

    tabla_pivot.index.name = "División"
    tabla_pivot = tabla_pivot.reset_index()

    # Convertir a HTML con estilo
    def construir_tabla_divisiones_html(df):
        estilos_css = """
        <style>
            .tabla-wrapper {
                overflow-x: auto;
                width: 100%;
            }

            .tabla-divisiones {
                min-width: 100%;
                width: max-content;
                border-collapse: collapse;
                table-layout: auto;
            }

            .tabla-divisiones thead th {
                background-color: #0B083D;
                color: white;
                padding: 8px;
                white-space: nowrap;
                position: sticky;
                top: 0;
                z-index: 3;
                border: 1px solid white;
            }

            .tabla-divisiones thead th:first-child {
                text-align: right;
            }

            .tabla-divisiones thead th:not(:first-child) {
                text-align: left;
            }

            /* Fijar el encabezado de la columna División */
            .tabla-divisiones thead th:first-child {
                left: 0;
                position: sticky;
                z-index: 5;
            }

            .tabla-divisiones td, .tabla-divisiones th {
                padding: 8px;
                font-size: 14px;
                white-space: nowrap;
                border: 1px solid white;
            }

            /* Fijar toda la columna División (incluyendo celdas del tbody y tfoot) */
            .tabla-divisiones tbody td:first-child,
            .tabla-divisiones tfoot td:first-child {
                position: sticky;
                left: 0;
                background-color: #eeeeee;
                color: black;
                font-weight: bold;
                text-align: right;
                z-index: 4;
            }

            /* También fijar la celda total primera columna (la última fila) */
            .tabla-divisiones tbody tr:last-child td:first-child {
                background-color: #0B083D;
                color: white;
                z-index: 6;
            }

            /* Texto columnas excepto División alineado a la izquierda */
            .tabla-divisiones tbody td:not(:first-child) {
                text-align: left;
            }

            .agricola {
                background-color: #367C2B !important;
                color: white;
            }

            .construccion {
                background-color: #FFA500 !important;
                color: black;
            }

            .jardineria {
                background-color: #FFDE00 !important;
                color: black;
            }

            .grad {
                color: black;
                font-weight: bold;
                text-align: left;
            }

            /* Estilo celdas totales */
            .celda-total {
                background-color: #0B083D !important;
                color: white !important;
                font-weight: bold;
                text-align: left;
            }
        </style>
        """

        # Calcular totales por fila (división)
        df['Total'] = df[meses_validos].sum(axis=1)

        # Calcular totales por columna (meses + total)
        totales_columna = df[meses_validos + ['Total']].sum()

        # Añadimos columna Total a orden_meses para pintar totales por columna
        columnas_completas = meses_validos + ['Total']

        html = estilos_css + "<div class='tabla-wrapper'><table class='tabla-divisiones'>"
        html += "<thead><tr>"
        for col in df.columns:
            html += f"<th>{col}</th>"
        html += "</tr></thead><tbody>"

        for _, row in df.iterrows():
            html += "<tr>"

            # Estilo para División
            division = row["División"]
            clase_div = ""
            if "Agrícola" in division:
                clase_div = "agricola"
            elif "Construcción" in division:
                clase_div = "construccion"
            elif "Jardinería" in division or "Golf" in division:
                clase_div = "jardineria"
            html += f"<td class='{clase_div}'>{division}</td>"

            # Valores por fila (incluyendo total)
            valores_fila = [row[col] for col in meses_validos]
            max_val = max(valores_fila)
            min_val = min(valores_fila)
            rango = max_val - min_val if max_val != min_val else 1

            # Mostrar celdas de meses con degradado azul por fila
            for col in meses_validos:
                val = row[col]
                ratio = (val - min_val) / rango
                azul = int(255 - (ratio * 120))
                color_fondo = f"rgb({azul},{azul + 20},255)"
                html += f"<td class='grad' style='background-color:{color_fondo}'>{val:,.2f}</td>"

            # Mostrar total por fila (sin degradado, con color fijo)
            total_fila = row['Total']
            html += f"<td class='celda-total'>{total_fila:,.2f}</td>"

            html += "</tr>"

        # Fila totales por columna
        html += "<tr>"
        html += "<td class='celda-total'>Total</td>"
        max_total = totales_columna.max()
        min_total = totales_columna.min()
        rango_total = max_total - min_total if max_total != min_total else 1

        for col in columnas_completas:
            val = totales_columna[col]
            ratio = (val - min_total) / rango_total
            azul = int(255 - (ratio * 120))
            color_fondo = f"rgb({azul},{azul + 20},255)"
            html += f"<td class='celda-total' style='background-color:{color_fondo}'>{val:,.2f}</td>"
        html += "</tr>"

        html += "</tbody></table></div>"
        return html

    # Mostrar tabla
    st.markdown("### Comparativo por división")
    st.markdown(construir_tabla_divisiones_html(tabla_pivot), unsafe_allow_html=True)
    st.markdown("<br><br>", unsafe_allow_html=True)

    # ------------ GRÁFICA DE BARRAS AGRUPADAS: EVOLUCIÓN MENSUAL COMPRADO POR DIVISIÓN ------------------------------------------------------------
    df_mes_div = df_divisiones_filtrado.groupby(["mes_nombre", "division"])["monto"].sum().reset_index()
    df_mes_div["mes_nombre"] = pd.Categorical(df_mes_div["mes_nombre"], categories=orden_meses, ordered=True)
    df_mes_div = df_mes_div.sort_values("mes_nombre")

    fig_mes_div = px.bar(
        df_mes_div,
        x="mes_nombre",
        y="monto",
        color="division",
        text="monto",
        custom_data=["division"],         
        color_discrete_map=colores_divisiones,
        labels={"mes_nombre":"Mes","monto":"Total Comprado","division":"División"}
    )

    fig_mes_div.update_traces(
        texttemplate="$%{y:,.0f}",
        textposition="inside",
        hovertemplate=(
            "<b>Mes:</b> %{x}<br>"
            "<b>División:</b> %{customdata[0]}<br>"
            "<b>Total Comprado:</b> $%{y:,.2f}<extra></extra>"
        )
    )

    fig_mes_div.update_layout(
        barmode="stack",  # usa 'group' si quieres barras agrupadas en lugar de apiladas
        xaxis=dict(tickangle=-45),
        margin=dict(t=60, b=100),
        legend=dict(orientation="h", yanchor="bottom", y=-0.6, xanchor="center", x=0.5)
    )

    st.markdown("### Evolución mensual de compras por División")
    st.markdown("<div style='margin-top:-10px'></div>", unsafe_allow_html=True)

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

    #----------------- GRÁFICA DE BARRAS AGRUPADAS: COMPRA POR SUCURSAL Y DIVISIÓN ------------------------------------------------------------
    df_suc_div = df_divisiones_filtrado.groupby(["sucursal", "division"])["monto"].sum().reset_index()

    fig_suc_div = px.bar(
        df_suc_div,
        x="sucursal",
        y="monto",
        color="division",
        text="monto",
        custom_data=["division"],  # ← aquí mandamos la división como dato adicional
        color_discrete_map=colores_divisiones,
        labels={"sucursal": "Sucursal", "monto": "Total Comprado", "division": "División"}
    )

    fig_suc_div.update_traces(
        texttemplate="$%{y:,.0f}",
        textposition="inside",
        hovertemplate=(
            "<b>Sucursal:</b> %{x}<br>"
            "<b>División:</b> %{customdata[0]}<br>"
            "<b>Monto:</b> $%{y:,.2f}<extra></extra>"
        )
    )

    fig_suc_div.update_layout(
        barmode="stack",  # usa 'group' si prefieres barras agrupadas
        xaxis_tickangle=-45,
        margin=dict(t=60, b=100),
        legend=dict(orientation="h", yanchor="bottom", y=-0.6, xanchor="center", x=0.5)
    )

    st.markdown("### Compra anual por Sucursal y División")
    st.markdown("<div style='margin-top:-10px'></div>", unsafe_allow_html=True)

    st.plotly_chart(fig_suc_div, use_container_width=True)


    #----------------------- Tabla de compra por division y sucursal ----------------------------------
    tabla_sucursal_division = pd.pivot_table(
        df_divisiones_filtrado,   # ✅ aquí aplicamos el filtrado
        values="monto",
        index="division",
        columns="sucursal",
        aggfunc="sum",
        margins=True,
        margins_name="Total",
    )

    # Renombrar índice
    tabla_sucursal_division.index.rename("División", inplace=True)

    # Llenar NaN con 0
    tabla_sucursal_division = tabla_sucursal_division.fillna(0)

    # Convertimos el índice en columna para trabajar con HTML
    tabla_sucursal_division = tabla_sucursal_division.reset_index()

    # Reordenamos para poner "Total" al final si no lo está
    tabla_sucursal_division = tabla_sucursal_division.sort_values(by="División", key=lambda x: x == "Total", ascending=True)

    # Extraer lista de sucursales (columnas)
    sucursales = [col for col in tabla_sucursal_division.columns if col != "División"]

    # Diccionario de colores
    colores_div = {
        "Agrícola": "#367C2B",
        "Construcción": "#FFA500",
        "Jardinería y Golf": "#FFDE00"
    }

    # Función para construir la tabla con estilo
    def construir_tabla_sucursal_division_html(df, columnas_sucursales):
        estilos_css = """
        <style>
            .tabla-wrapper {
                overflow-x: auto;
                width: 100%;
            }

            .tabla-divisiones {
                min-width: 100%;
                width: max-content;
                border-collapse: collapse;
                table-layout: auto;
            }

            .tabla-divisiones thead th {
                background-color: #0B083D;
                color: white;
                padding: 8px;
                white-space: nowrap;
                position: sticky;
                top: 0;
                z-index: 3;
                border: 1px solid white;
            }

            .tabla-divisiones thead th:first-child {
                text-align: right;
                left: 0;
                position: sticky;
                z-index: 5;
            }

            .tabla-divisiones thead th:not(:first-child) {
                text-align: left;
            }

            .tabla-divisiones td, .tabla-divisiones th {
                padding: 8px;
                font-size: 14px;
                white-space: nowrap;
                border: 1px solid white;
            }

            .tabla-divisiones tbody td:first-child {
                position: sticky;
                left: 0;
                font-weight: bold;
                text-align: right;
                background-color: #eeeeee;
                z-index: 4;
            }

            .tabla-divisiones tbody tr:last-child td:first-child {
                background-color: #0B083D;
                color: white;
                z-index: 6;
            }

            .tabla-divisiones tbody td:not(:first-child) {
                text-align: left;
            }

            .celda-total {
                background-color: #0B083D !important;
                color: white !important;
                font-weight: bold;
                text-align: left;
            }

            .grad {
                font-weight: bold;
                text-align: left;
                color: black;
            }
        </style>
        """

        html = estilos_css + "<div class='tabla-wrapper'><table class='tabla-divisiones'>"
        html += "<thead><tr><th>División</th>"
        for col in columnas_sucursales:
            html += f"<th>{col}</th>"
        html += "</tr></thead><tbody>"

        for i, row in df.iterrows():
            division = row["División"]
            es_total_fila = division == "Total"
            color_fondo_div = "#0B083D" if es_total_fila else colores_div.get(division, "#eeeeee")
            color_texto = "white" if es_total_fila else ("black" if color_fondo_div != "#FFDE00" else "black")

            html += f"<tr><td style='background-color:{color_fondo_div}; color:{color_texto}'>{division}</td>"
            columnas_sucursales = [col for col in df.columns if col not in ("División", "Total")]

            if not es_total_fila:
                valores = [row[col] for col in columnas_sucursales]
                max_val = max(valores)
                min_val = min(valores)
                rango = max_val - min_val if max_val != min_val else 1

            for col in columnas_sucursales + ["Total"]:
                val = row[col]
                if es_total_fila or col == "Total":
                    clase = "celda-total"
                    html += f"<td class='{clase}'>{val:,.0f}</td>"
                else:
                    ratio = (val - min_val) / rango
                    azul = int(255 - (ratio * 120))
                    color_fondo = f"rgb({azul},{azul + 20},255)"
                    html += f"<td class='grad' style='background-color:{color_fondo}'>{val:,.0f}</td>"

            html += "</tr>"

        html += "</tbody></table></div>"
        return html
    
    st.subheader("Monto anual comprado por sucursal y división")
    st.markdown(
        construir_tabla_sucursal_division_html(tabla_sucursal_division, sucursales),
        unsafe_allow_html=True
    )
    st.markdown("<br><br>", unsafe_allow_html=True)


    #----------- Graficos de columnas de compra mensual por división y sucursal -------------

    # Cargar colores de divisiones
    with open("config_colores.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    colores_divisiones = {k: v["color"] for k, v in config["divisiones"].items()}

    # Agrupar datos
    df_smd = df_filtrado.groupby(["sucursal", "mes_nombre", "division"], as_index=False)["monto"].sum()
    df_smd["sucursal"] = df_smd["sucursal"].astype(str)
    df_smd["mes_nombre"] = df_smd["mes_nombre"].astype(str)
    df_smd["division"] = df_smd["division"].astype(str)

    sucursales = df_smd["sucursal"].unique()
    num_sucursales = len(sucursales)

    # 📌 Detectar el año base a partir de los datos filtrados
    anio_min = df_smd["mes_nombre"].str.extract(r"(\d{4})").astype(float).min()[0]
    anio_max = df_smd["mes_nombre"].str.extract(r"(\d{4})").astype(float).max()[0]
    anio = int(anio_min) if periodo == "Año Natural" else int(anio_max)  # ← usamos 'periodo', no 'opciones_periodo'

    # 📌 Lista de meses según periodo
    if periodo == "Año Natural":
        orden_meses_con_anio = [
            f"Enero {anio}", f"Febrero {anio}", f"Marzo {anio}", f"Abril {anio}",
            f"Mayo {anio}", f"Junio {anio}", f"Julio {anio}", f"Agosto {anio}",
            f"Septiembre {anio}", f"Octubre {anio}", f"Noviembre {anio}", f"Diciembre {anio}"
        ]
    else:  # 📌 Año Fiscal (Noviembre → Octubre)
        orden_meses_con_anio = [
            f"Noviembre {anio-1}", f"Diciembre {anio-1}",
            f"Enero {anio}", f"Febrero {anio}", f"Marzo {anio}", f"Abril {anio}",
            f"Mayo {anio}", f"Junio {anio}", f"Julio {anio}", f"Agosto {anio}",
            f"Septiembre {anio}", f"Octubre {anio}"
        ]

    # Mapeo español → inglés para conversión
    meses_es_en = {
        'Enero': 'January', 'Febrero': 'February', 'Marzo': 'March', 'Abril': 'April',
        'Mayo': 'May', 'Junio': 'June', 'Julio': 'July', 'Agosto': 'August',
        'Septiembre': 'September', 'Octubre': 'October', 'Noviembre': 'November', 'Diciembre': 'December'
    }

    # Columna temporal para conversión
    df_smd["mes_nombre_en"] = df_smd["mes_nombre"].str.extract(r"(\w+)\s+(\d{4})").apply(
        lambda row: f"{meses_es_en.get(row[0], row[0])} {row[1]}", axis=1
    )

    # Convertir a datetime
    df_smd["fecha_mes"] = pd.to_datetime(df_smd["mes_nombre_en"], format="%B %Y")

    # Filtrar hasta el mes más reciente
    max_fecha = df_smd["fecha_mes"].max()
    orden_meses_fecha = [
        pd.to_datetime(f"{meses_es_en[m.split()[0]]} {m.split()[1]}", format="%B %Y")
        for m in orden_meses_con_anio
    ]
    meses_hasta_max = [
        orden_meses_con_anio[i] for i, fecha in enumerate(orden_meses_fecha) if fecha <= max_fecha
    ]

    # Categorizar para orden
    df_smd["mes_nombre"] = pd.Categorical(df_smd["mes_nombre"], categories=meses_hasta_max, ordered=True)
    df_smd = df_smd.sort_values(["sucursal", "mes_nombre"])
    df_smd.drop(columns=["mes_nombre_en"], inplace=True)

    st.title("Evolución de compras por sucursal")

    # Columnas por fila
    num_columnas = st.radio("Número de columnas de gráficos por fila:", options=[1, 2], index=1)

    # Orden de divisiones y paleta
    divisiones_ordenadas = sorted(df_smd["division"].unique())
    palette = [colores_divisiones.get(div, "#777777") for div in divisiones_ordenadas]

    for i in range(0, num_sucursales, num_columnas):
        cols = st.columns(num_columnas)
        for j in range(num_columnas):
            if i + j < num_sucursales:
                suc = sucursales[i + j]
                df_sucursal = df_smd[df_smd["sucursal"] == suc]

                fig, ax = plt.subplots(figsize=(8, 4))
                fig.patch.set_facecolor('#121212')
                ax.set_facecolor('#121212')

                # Divisiones presentes en este subset y paleta ajustada
                divisiones_presentes = df_filtrado["division"].unique()
                palette_grafico = {div: colores_divisiones.get(div, "#777777") for div in divisiones_presentes}

                sns.barplot(
                    data=df_sucursal,
                    x="monto",
                    y="mes_nombre",
                    hue="division",
                    hue_order=divisiones_presentes,  # solo divisiones presentes
                    palette=palette_grafico,
                    ax=ax,
                    orient="h"
                )

                # Etiquetas de las barras, al borde para no sobreponerse
                for container in ax.containers:
                    ax.bar_label(
                        container,
                        labels=[f"${x:,.0f}" for x in container.datavalues],
                        padding=3,
                        color='white',
                        fontsize=9,
                        label_type='edge'
                    )

                # Formato eje X
                ax.xaxis.set_major_formatter(mtick.StrMethodFormatter('${x:,.0f}'))
                ax.set_title(f"{suc} - Evolución de Compras", color="white")
                ax.set_xlabel("Monto", color="white")
                ax.set_ylabel("Mes", color="white")
                ax.tick_params(colors="white")

                # Leyenda solo con divisiones presentes
                leg = ax.get_legend()
                if leg is not None:
                    leg.set_title("División")
                    leg.get_title().set_color("white")  # título en blanco
                    for text in leg.get_texts():
                        text.set_color("white")           # labels en blanco
                    leg.get_frame().set_facecolor('#121212')
                    leg.get_frame().set_edgecolor('white')
                    # mover la leyenda
                    leg.set_bbox_to_anchor((1.15, 1))   # desplazamiento horizontal
                    leg._legend_box.align = "left"

                # Ajustar márgenes para que la leyenda no se encime con el gráfico
                fig.subplots_adjust(right=0.80)

                cols[j].pyplot(fig)