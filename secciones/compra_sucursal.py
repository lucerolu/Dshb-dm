import streamlit as st
import plotly.express as px
import json
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import io
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
from utils.api_utils import obtener_datos_api


def mostrar(df_filtrado, config):
    st.title("Compra por Sucursal")
    
    if df_filtrado.empty:
        st.warning("No hay datos para mostrar.")
        return
    
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

    st.title("Total de Compras por Mes y Sucursal")
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

    #------------------------------------ GRÁFICA DE BARRAS AGRUPADA ---------------------------------------------------------------------------------------
    df_pivot = df_divisiones_filtrado.pivot_table(
        index="mes_nombre",
        columns="sucursal",
        values="monto",
        aggfunc="sum"
    ).fillna(0)
    orden_meses = df_divisiones_filtrado.drop_duplicates("mes_dt") \
            .sort_values("mes_dt")["mes_nombre"].tolist()

    df_pivot = df_pivot.reindex(orden_meses)
    df_percent = df_pivot.div(df_pivot.sum(axis=1), axis=0) * 100

    fig = go.Figure()
    for sucursal in sorted(df_pivot.columns):
        fig.add_trace(go.Bar(
            y=df_percent.index,
            x=df_percent[sucursal],
            orientation='h',
            name=sucursal,
            marker=dict(color=colores_sucursales.get(sucursal, {}).get("color", "#CCCCCC")),
            customdata=df_pivot[sucursal],
            text=[
                f"{df_percent.loc[mes, sucursal]:.1f}%<br>${df_pivot.loc[mes, sucursal]:,.0f}"
                if df_pivot.loc[mes, sucursal] > 0 else ""
                for mes in df_percent.index
            ],
            hovertemplate="<b>%{fullData.name}</b><br>%{x:.1f}%<br>$%{customdata:,.2f}<extra></extra>",
            textposition='inside'
        ))
    fig.update_layout(
        barmode='stack',
        #title='Distribución porcentual de compras por sucursal (2025)',
        xaxis=dict(title='Porcentaje', ticksuffix='%'),
        yaxis=dict(title='Mes'),
        legend=dict(orientation='h', yanchor='top', y=-0.25, xanchor='center', x=0.5),
        height=650, margin=dict(t=20)
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
    st.markdown("### Distribución porcentual de compras por sucursal (2025)")
    st.markdown("<div style='margin-top:px'></div>", unsafe_allow_html=True)
    # Mostrar gráfica con zoom y opciones de barra
    st.plotly_chart(fig, use_container_width=True, config=config)


    #------------------------------- TABLA: RESUMEN TOTAL POR MES Y SUCURSAL ------------------------------------
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("### Resumen total por mes y sucursal")

    # Crear tabla pivote con totales
    tabla = df_filtrado.pivot_table(
        index="mes_nombre",
        columns="sucursal",
        values="monto",
        aggfunc="sum",
        margins=True,
        margins_name="Total"
    ).fillna(0)

    # Reordenar filas (meses + total)
    tabla = tabla.reindex(orden_meses + ["Total"])

    # Cambiar nombre índice
    tabla.index.name = "Mes"

    # Resetear índice para AgGrid (sin formatear números)
    tabla_reset = tabla.reset_index()

    tabla_reset = tabla.reset_index().fillna(0)

    for col in tabla_reset.columns:
        if col != "Mes":
            tabla_reset[col] = pd.to_numeric(tabla_reset[col], errors='coerce').fillna(0)

    total_row = tabla_reset[tabla_reset["Mes"] == "Total"]
    data_sin_total = tabla_reset[tabla_reset["Mes"] != "Total"]

    print(data_sin_total[["Tierra blanca", "Tuxtla Gtz"]])

    # Separar la fila Total para fijarla abajo
    total_row = tabla_reset[tabla_reset["Mes"] == "Total"]
    data_sin_total = tabla_reset[tabla_reset["Mes"] != "Total"].copy()
    data_sin_total = data_sin_total.fillna(0)
    for col in data_sin_total.columns:
        if col != "Mes":
            data_sin_total[col] = pd.to_numeric(data_sin_total[col], errors='coerce').fillna(0)
    
    print(data_sin_total.columns.tolist())

    # Asegurar que columnas numéricas sean floats
    ultima_col = tabla_reset.columns[-1]
    for col in data_sin_total.columns:
        if col not in ["Mes", ultima_col]:
            data_sin_total[col] = pd.to_numeric(data_sin_total[col], errors='coerce').fillna(0)

    # Calcular min y max por sucursal (excluyendo total vertical)
    min_max_dict = {}
    for col in data_sin_total.columns:
        if col not in ["Mes", ultima_col]:
            valores = data_sin_total[col]
            min_max_dict[col] = (valores.min(), valores.max())

    # JS arreglo meses para orden cronológico
    orden_meses_js_array = str(orden_meses).replace("'", '"')

    # Comparator JS para ordenar meses
    month_comparator = JsCode(f"""
    function(month1, month2) {{
        var orden = {orden_meses_js_array};
        var i1 = orden.indexOf(month1);
        var i2 = orden.indexOf(month2);
        return i1 - i2;
    }}
    """)

    # Formatter para mostrar números con comas y 2 decimales
    value_formatter = JsCode("""
    function(params) {
        if (params.value === undefined || params.value === null) return '0.00';
        return params.value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
    """)

    # JS para pintar celdas con escala rojo → amarillo → verde pastel
    cell_style_gradient_template = """
    function(params) {
        const totalCol = '%s';
        if (params.colDef.field !== 'Mes' && params.colDef.field !== totalCol && params.data['Mes'] !== 'Total') {
            let val = params.value;
            let min = %f;
            let max = %f;
            if (!isNaN(val) && max > min) {
                let ratio = (val - min) / (max - min);

                // Colores definidos
                let r, g, b;
                if (ratio <= 0.5) {
                    // Verde (#75DE54) a Amarillo (#E8E546)
                    let t = ratio / 0.5;
                    r = Math.round(117 + t * (232 - 117));
                    g = Math.round(222 + t * (229 - 222));
                    b = Math.round(84  + t * (70  - 84));
                } else {
                    // Amarillo (#E8E546) a Rojo (#E86046)
                    let t = (ratio - 0.5) / 0.5;
                    r = Math.round(232 + t * (232 - 232));
                    g = Math.round(229 + t * (96  - 229));
                    b = Math.round(70  + t * (70  - 70));
                }

                return {
                    backgroundColor: `rgb(${r},${g},${b})`,
                    textAlign: 'left'
                };
            }
        }
        return { textAlign: 'left' };
    }
    """

    # Construir opciones de grid para AgGrid
    gb = GridOptionsBuilder.from_dataframe(data_sin_total)
    gb.configure_default_column(resizable=True, filter=False)

    # Columna Mes fija en azul y con comparator para orden cronológico
    gb.configure_column(
        "Mes",
        pinned="left",
        width=180,
        cellStyle={
            'textAlign': 'right',
            'backgroundColor': '#0B083D',
            'color': 'white',
            'fontWeight': 'bold'
        },
        comparator=month_comparator
    )

    # Configurar columnas numéricas con valueGetter simple y valueFormatter
    for col in data_sin_total.columns:
        if col not in ["Mes", ultima_col]:
            min_val, max_val = min_max_dict[col]
            gradient_code = JsCode(cell_style_gradient_template % (ultima_col, min_val, max_val))
            gb.configure_column(
                col,
                width=120,
                cellStyle=gradient_code,
                sortable=True,
                valueGetter=JsCode(f"function(params) {{ return params.data['{col}']; }}"),
                valueFormatter=value_formatter
            )

    gb.configure_column(
        col,
        width=120,
        cellStyle=gradient_code,
        sortable=True,
        valueGetter=JsCode(f"function(params) {{ return params.data['{col}']; }}"),
        valueFormatter=value_formatter
    )

    # Columna Total vertical fija azul y sin orden
    gb.configure_column(
        ultima_col,
        width=120,
        cellStyle={
            'textAlign': 'left',
            'backgroundColor': '#0B083D',
            'color': 'white',
            'fontWeight': 'bold'
        },
        sortable=False,
        valueFormatter=value_formatter  # <-- acá el formatter
    )

    # JS para pintar fila total fija abajo
    get_row_style = JsCode("""
    function(params) {
        if(params.node.rowPinned) {
            return {
                backgroundColor: '#0B083D',
                color: 'white',
                fontWeight: 'bold'
            };
        }
        return null;
    }
    """)

    grid_options = gb.build()
    grid_options['pinnedBottomRowData'] = total_row.to_dict('records')
    grid_options['getRowStyle'] = get_row_style
    grid_options['domLayout'] = 'autoHeight'

    # CSS para header azul de la tabla
    custom_css = {
        ".ag-header-cell-label": {
            "background-color": "#0B083D !important",
            "color": "white !important",
            "font-weight": "bold !important",
            "justify-content": "center !important"
        },
        ".ag-header-cell-text": {
            "color": "white !important",
            "font-weight": "bold !important"
        }
    }

    # --- Layout de título + botón en dos columnas ---
    col1, col2 = st.columns([3, 1])  # proporción de ancho 3:1
    with col1:
        st.subheader("Tabla resumen del monto sin ligar por mes y sucursal")

    with col2:
        buffer = io.BytesIO()
        tabla_reset.to_excel(buffer, index=False)
        buffer.seek(0)

        st.download_button(
            label="📥 Descargar tabla en Excel",
            data=buffer,
            file_name="resumen_mensual.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # --- Mostrar tabla debajo ---
    AgGrid(
        data_sin_total,
        gridOptions=grid_options,
        height=400,  # altura de la tabla
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        custom_css=custom_css,
        enable_enterprise_modules=False,
        theme="ag-theme-alpine"
    )

    # ------------------------- GRÁFICO DE LÍNEAS: EVOLUCIÓN DE COMPRAS POR MES Y SUCURSAL -------------------------------------
    fig_lineas = go.Figure()

    for sucursal in df_pivot.columns:
        # Prepara los datos para pasar mes y sucursal por customdata
        customdata = list(zip(df_pivot.index.astype(str), [sucursal]*len(df_pivot)))

        fig_lineas.add_trace(go.Scatter(
            x=df_pivot.index,
            y=df_pivot[sucursal],
            mode='lines+markers',
            name=sucursal,
            line=dict(color=colores_sucursales.get(sucursal, {}).get("color", "#CCCCCC")),
            customdata=customdata,
            hovertemplate=(
                "<b>Sucursal:</b> %{customdata[1]}<br>" +
                "<b>Mes:</b> %{customdata[0]}<br>" +
                "<b>Monto:</b> $%{y:,.2f}<extra></extra>"
            )
        ))

    fig_lineas.update_layout(
        #title="Evolución de Compras por Mes y Sucursal (2025)",
        xaxis_title="Mes",
        yaxis_title="Total Comprado",
        xaxis=dict(tickangle=-45),
        height=500,
        margin=dict(t=60)
    )
    
    # --- Espacio responsivo ---
    st.markdown("<div style='margin-top:1.5em; margin-bottom:1em'></div>", unsafe_allow_html=True)
    #st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("### Evolución de Compras por Mes y Sucursal (2025)")
    st.markdown("<div style='margin-top:-30px'></div>", unsafe_allow_html=True)
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

    # Lista ordenada de meses base (enero a diciembre) en español
    orden_meses_base = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]

    # Generar orden desde el mes actual hacia atrás
    mes_inicio = (mes_actual - 1) % 12
    orden_meses_reversa = [orden_meses_base[(mes_inicio - i) % 12] for i in range(12)]

    # Agregar el año a cada mes en el orden correcto, tomando en cuenta los datos reales
    orden_meses_reversa_completa = []
    for mes_simple in orden_meses_reversa:
        meses_disponibles = [m for m in df_filtrado["mes_nombre"].unique() if m.startswith(mes_simple)]
        orden_meses_reversa_completa.extend(meses_disponibles)

    # Mostrar las gráficas
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("### Compras por Sucursal, mes a mes")

    for i, mes in enumerate(orden_meses_reversa_completa):
        df_mes = df_filtrado[df_filtrado["mes_nombre"] == mes].copy()

        # Agrupar solo por sucursal, sumando montos
        df_mes = df_mes.groupby("sucursal", as_index=False).agg({"monto": "sum"})
        
        if df_mes["monto"].sum() == 0:
            continue

        total_mes = df_mes["monto"].sum()
        df_mes["porcentaje"] = df_mes["monto"] / total_mes * 100
        df_mes["texto"] = df_mes.apply(
            lambda row: f"${row['monto']:,.2f}<br>({row['porcentaje']:.1f}%)", axis=1
        )
        df_mes["custom_data"] = list(zip(df_mes["sucursal"], df_mes["monto"], df_mes["porcentaje"]))
        color_map = {k: v["color"] for k, v in colores_sucursales.items()}

        fig_mes = px.bar(
            df_mes,
            x="sucursal",
            y="monto",
            title=f"Compras en {mes}",
            labels={"monto": "Total Comprado", "sucursal": "Sucursal"},
            color="sucursal",
            color_discrete_map=color_map,
            text="texto",
            custom_data=["sucursal", "monto", "porcentaje"]
        )

        fig_mes.update_traces(
            textposition='inside',
            texttemplate='%{text}',
            hovertemplate=(
                "<b>Sucursal:</b> %{customdata[0]}<br>"
                "<b>Monto:</b> $%{customdata[1]:,.2f}<br>"
                "<b>Porcentaje:</b> %{customdata[2]:.1f}%<extra></extra>"
            )
        )

        fig_mes.update_layout(showlegend=False)
        st.plotly_chart(fig_mes, use_container_width=True, key=f"bar_{i}_{mes}")