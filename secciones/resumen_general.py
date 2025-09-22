import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from utils.api_utils import obtener_datos_api

# ================== FUNCIÓN PRINCIPAL =====================
def mostrar(df_filtrado, config):
    """
    Muestra el Resumen General con tablas y gráficos.
    df_filtrado: DataFrame ya filtrado por sucursal/fecha
    config: diccionario de configuración (colores, divisiones, etc.)
    """ 
    # ================== PREPARACIÓN DE DATOS =====================
    # Diccionario de meses (mueve a config.py si lo usas en más lados)
    meses_es = {
        "January": "Enero", "February": "Febrero", "March": "Marzo",
        "April": "Abril", "May": "Mayo", "June": "Junio",
        "July": "Julio", "August": "Agosto", "September": "Septiembre",
        "October": "Octubre", "November": "Noviembre", "December": "Diciembre"
    }

    # Orden de meses (mueve a config.py si lo compartes con más secciones)
    orden_meses = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]

    # Normalizamos la fecha y el nombre del mes
    df_filtrado["mes_dt"] = pd.to_datetime(df_filtrado["mes"])
    df_filtrado["mes_nombre"] = (
        df_filtrado["mes_dt"].dt.month_name()
        .map(meses_es) + " " + df_filtrado["mes_dt"].dt.year.astype(str)
    )

    # ================== AGRUPACIONES ÚNICAS (reutilizables) =====================
    df_mensual = (
        df_filtrado.groupby("mes_nombre", as_index=False)["monto"].sum()
    )
    df_mensual["mes_nombre"] = pd.Categorical(df_mensual["mes_nombre"], categories=orden_meses, ordered=True)
    df_mensual = df_mensual.sort_values("mes_nombre").reset_index(drop=True)



    st.title("Resumen General de Compras")

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
        inicio_fiscal = pd.Timestamp(año_seleccionado-1, 11, 1)
        fin_fiscal = pd.Timestamp(año_seleccionado, 10, 31)
        df_filtrado = df_filtrado[(df_filtrado["fecha"] >= inicio_fiscal) & (df_filtrado["fecha"] <= fin_fiscal)]
        titulo_periodo = f"Fiscal {año_seleccionado}"

    # Recalcular mes_nombre y mes_period después del filtrado
    df_filtrado["mes_dt"] = pd.to_datetime(df_filtrado["fecha"])
    df_filtrado["mes_period"] = df_filtrado["mes_dt"].dt.to_period("M")
    df_filtrado["mes_nombre"] = (
        df_filtrado["mes_dt"].dt.month_name().map(meses_es)
        + " " + df_filtrado["mes_dt"].dt.year.astype(str)
    )

    df_total_mes = (
        df_filtrado.groupby(["mes_dt","mes_nombre"])["monto"].sum().reset_index()
        .sort_values("mes_dt")
    )

    #--------------- TARJETAS: total comprado en el año y en el mes corriente  ------------------------------------------
    ahora = datetime.now()
    ahora_pd = pd.Timestamp(ahora)
    mes_actual_period = ahora_pd.to_period("M")
    mes_actual_esp = meses_es.get(ahora.strftime("%B"), "") + " " + str(ahora.year)

    col1, col2 = st.columns(2)

    with col1:
        total_anual = df_filtrado["monto"].sum()
        st.metric(f"Total comprado ({titulo_periodo})", f"${total_anual:,.2f}")

    with col2:
        total_mes_actual = df_filtrado[df_filtrado["mes_period"] == mes_actual_period]["monto"].sum()
        st.metric(f"Total comprado en {mes_actual_esp}", f"${total_mes_actual:,.2f}")

    st.markdown("<br><br>", unsafe_allow_html=True)

    # ------------------------------------ GÁFICA DE LÍNEAS DEL TOTAL GENERAL  -----------------------------------------------------------------------------------------------------------------
    # Agrupar y conservar solo los meses que realmente existen en df_filtrado
    #df_total_mes = df_filtrado.groupby("mes_nombre")["monto"].sum()
    df_total_mes = (
        df_filtrado.groupby("mes_nombre", as_index=False)["monto"].sum()
    )

    # Ordenar los meses que sí están presentes
    df_total_mes = df_total_mes.reindex([m for m in orden_meses if m in df_total_mes.index])

    # Crear figura
    fig_total = go.Figure()
    fig_total.add_trace(go.Scatter(
        x=df_total_mes["mes_nombre"],
        y=df_total_mes["monto"],
        mode="lines+markers",
        name="Total",
        line=dict(color="blue"),
        hovertemplate="%{x}<br>Total: $%{y:,.2f}<extra></extra>"
    ))

    fig_total.update_layout(
        xaxis_title="Mes",
        yaxis_title="Monto",
        yaxis_tickformat=","
    )

    st.markdown("### Evolución mensual del total comprado")
    st.plotly_chart(fig_total, use_container_width=True)

    # ----------------------------------------- TABLA: TOTAL COMPRADO POR MES --------------------------------------------------------------------------------------------
    st.markdown("### Total comprado por mes")

    # Agrupar
    tabla_horizontal = df_filtrado.groupby("mes_nombre")["monto"].sum()

    # Filtrar y ordenar solo los meses presentes en df_filtrado
    meses_presentes = [m for m in orden_meses if m in tabla_horizontal.index]
    tabla_horizontal = tabla_horizontal.reindex(meses_presentes)

    # Crear DataFrame y transponer
    tabla_horizontal_df = pd.DataFrame(tabla_horizontal).T
    tabla_horizontal_df.index = ["Total Comprado"]

    # Calcular Total
    tabla_horizontal_df["Total"] = tabla_horizontal_df.sum(axis=1)

    # Reordenar columnas
    cols = [col for col in tabla_horizontal_df.columns if col != "Total"] + ["Total"]
    tabla_horizontal_df = tabla_horizontal_df[cols]

    # Formatear montos como moneda
    tabla_html = tabla_horizontal_df.applymap(lambda x: f"${x:,.2f}")

    # HTML dinámico
    header_html = ''.join([
        f'<th style="background-color:#390570; color:white; padding:8px; text-align:left;">{col}</th>'
        for col in tabla_html.columns
    ])

    row_html = ''.join([
        f'<td style="padding:8px; text-align:left;">{val}</td>'
        for val in tabla_html.iloc[0]
    ])

    html_table = f"""
    <div style="overflow-x:auto; width: 100%;">
    <table style="border-collapse:collapse; min-width:800px; width:100%;">
        <thead>
        <tr>
            <th style="background-color:#390570; padding:8px; color:white; text-align:left; position:sticky; left:0; z-index:1;">
            </th>
            {header_html}
        </tr>
        </thead>
        <tbody>
        <tr>
            <td style="padding:8px; text-align:right; background-color:#281436; color:white; font-weight:bold; position:sticky; left:0; z-index:1;">
            Total Comprado
            </td>
            {row_html}
        </tr>
        </tbody>
    </table>
    </div>
    """

    st.markdown(html_table, unsafe_allow_html=True)

# -------------------------------------------- GRÁFICA: Total comprado por mes ------------------------------------------------------------------------------
    #st.markdown("### Gráfica de Total comprado por mes")
    # Agrupar de nuevo (en bruto, sin formato)
    df_mensual = df_filtrado.groupby("mes_nombre", as_index=False)["monto"].sum()
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
    st.markdown("#### Compra vs mes anterior")

    # Agrupar y ordenar por mes
    df_mensual = df_filtrado.groupby("mes_nombre", as_index=False)["monto"].sum()
    df_mensual["mes_nombre"] = pd.Categorical(df_mensual["mes_nombre"], categories=orden_meses, ordered=True)
    df_mensual = df_mensual.sort_values("mes_nombre").reset_index(drop=True)

    # Calcular diferencia y variación
    df_mensual["diferencia"] = df_mensual["monto"].diff().fillna(0)
    df_mensual["variacion_pct"] = df_mensual["monto"].pct_change().fillna(0) * 100

    # Flechas al final
    df_mensual["monto_str"] = df_mensual["monto"].apply(lambda x: f"${x:,.2f}")
    df_mensual["diferencia_str"] = df_mensual["diferencia"].apply(
        lambda x: f"${x:,.2f} ⬆" if x > 0 else f"${x:,.2f} ⬇" if x < 0 else "$0 ➖"
    )
    df_mensual["variacion_str"] = df_mensual["variacion_pct"].apply(
        lambda x: f"{x:.1f}% ⬆" if x > 0 else f"{x:.1f}% ⬇" if x < 0 else "0.0% ➖"
    )

    # Tabla base
    df_comp = df_mensual[["mes_nombre", "monto_str", "diferencia_str", "variacion_str"]]
    df_comp.columns = ["Mes", "Total Comprado", "Diferencia ($)", "Variación (%)"]

    # Convertir a HTML
    def construir_tabla_comparativa(df):
        estilos_css = """
        <style>
            .tabla-wrapper {
                overflow-x: auto;
                width: 100%;
            }

            .tabla-comparativa {
                min-width: 100%;
                width: max-content;
                border-collapse: collapse;
                table-layout: auto;
            }

            .tabla-comparativa thead th {
                background-color: #0B083D;
                color: white;
                padding: 8px;
                white-space: nowrap;
                position: sticky;
                top: 0;
                z-index: 3;
                border: 1px solid white;
            }

            .tabla-comparativa thead th:first-child {
                text-align: right;
                left: 0;
                position: sticky;
                z-index: 5;
            }

            .tabla-comparativa thead th:not(:first-child) {
                text-align: left;
            }

            .tabla-comparativa td, .tabla-comparativa th {
                padding: 8px;
                font-size: 14px;
                white-space: nowrap;
                border: 1px solid white;
            }

            .tabla-comparativa tbody td:first-child,
            .tabla-comparativa tfoot td:first-child {
                position: sticky;
                left: 0;
                background-color: #0B083D;
                color: white;
                font-weight: bold;
                text-align: right;
                z-index: 4;
            }

            .tabla-comparativa tbody td:not(:first-child) {
                text-align: left;
            }

            .subida {
                background-color: #7D1F08;
                color: white;
            }

            .bajada {
                background-color: #184E08;
                color: white;
            }

            .neutra {
                color: white;
            }
        </style>
        """

        html = f"{estilos_css}<div class='tabla-wrapper'><table class='tabla-comparativa'>"
        html += (
            "<thead><tr>"
            "<th>Mes</th>"
            "<th>Total Comprado</th>"
            "<th>Diferencia ($)</th>"
            "<th>Variación (%)</th>"
            "</tr></thead><tbody>"
        )

        for _, row in df.iterrows():
            html += "<tr>"

            # Determinar clase de color
            clase_color = (
                "subida" if "⬆" in row["Diferencia ($)"] else
                "bajada" if "⬇" in row["Diferencia ($)"] else
                "neutra"
            )

            html += f"<td>{row['Mes']}</td>"
            html += f"<td class='{clase_color}'>{row['Total Comprado']}</td>"
            html += f"<td class='{clase_color}'>{row['Diferencia ($)']}</td>"
            html += f"<td class='{clase_color}'>{row['Variación (%)']}</td>"

            html += "</tr>"

        html += "</tbody></table></div>"
        return html

    # Mostrar tabla
    tabla_html = construir_tabla_comparativa(df_comp)
    st.markdown(tabla_html, unsafe_allow_html=True)
    st.markdown("<div class='spacer'></div>", unsafe_allow_html=True)

    # --------------------------------------- GRÁFICA DE DIFERENCIAS MENSUALES --------------------------------------------------------------------------------------------
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("### Variación de compras respecto al mes anterior")

    # Agrupar y ordenar por mes
    df_mensual = df_filtrado.groupby("mes_nombre", as_index=False)["monto"].sum()
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