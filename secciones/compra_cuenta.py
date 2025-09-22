import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import itertools
import io
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode, ColumnsAutoSizeMode, AgGridTheme
from utils.api_utils import obtener_datos_api
from utils.helpers import meses_es

def mostrar(df_filtrado, config):
    st.title("Compra por Cuenta")
    
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
    
    df_filtrado["cuenta_id"] = df_filtrado["codigo_normalizado"]  
    df_cuenta = df_filtrado.groupby(["mes_nombre", "cuenta_id"])["monto"].sum().reset_index()
    
    fig = px.line(df_cuenta, x="mes_nombre", y="monto", color="cuenta_id",
                  title="Compras por Cuenta")
    st.plotly_chart(fig, use_container_width=True)
    
    st.title("Compra Total Anual por Cuenta")
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

    #-------------------------------------- GRAFICO DE BARRAS HORIZONTAL ----------------------------------------------------------------
    
    # 1️⃣ Agregar división antes de agrupar
    df_filtrado["division"] = df_filtrado["codigo_normalizado"].map(mapa_codigos)

    # 2️⃣ Agrupar por cuenta y sucursal
    df_cta = df_filtrado.groupby(
        ["codigo_normalizado", "sucursal", "division"],
        as_index=False
    )["monto"].sum()

    # Crear etiqueta tipo "1234 - Monterrey"
    df_cta["cuenta_sucursal"] = df_cta["codigo_normalizado"] + " - " + df_cta["sucursal"]

    # Ordenar de mayor a menor
    df_cta = df_cta.sort_values("monto", ascending=False)

    # ✅ Columna de texto formateada
    df_cta["monto_fmt"] = df_cta["monto"].apply(lambda x: f"${x:,.2f}")

    # Gráfico de barras usando la columna formateada
    fig = px.bar(
        df_cta,
        x="monto",
        y="cuenta_sucursal",
        color="division",
        color_discrete_map=colores_divisiones,
        orientation="h",
        labels={
            "monto": "Monto",
            "cuenta_sucursal": "Cuenta - Sucursal",
            "division": "División"
        },
        text="monto_fmt",          # ⚡ texto formateado afuera
        hover_data={"monto_fmt": True, "monto": False}  # ⚡ hover con formato
    )

    # Ajustar trazas
    fig.update_traces(
        textposition="outside",
        cliponaxis=False
    )

    # Layout
    fig.update_layout(
        xaxis_title="Monto (MXN)",
        yaxis_title="Cuenta - Sucursal",
        margin=dict(r=70),
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

    st.markdown("### Monto Total Anual por Cuenta")
    st.markdown("<div style='margin-top:-30px'></div>", unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("<br><br>", unsafe_allow_html=True)

    #------------------------------ TABLA: COMPRA MENSUAL POR CUENTA: 2025 ---------------------------------------------------
    st.title(f"Compra mensual por Cuenta ({titulo_periodo})")
    st.markdown("<div style='margin-top:-5px'></div>", unsafe_allow_html=True)

    # --- Función para obtener abreviatura ---
    def obtener_abreviatura(codigo):
        for division, info in divisiones.items():
            if codigo in info["codigos"]:
                return info["abreviatura"]
        return ""

    if "mes_dt" not in df_filtrado.columns:
        df_filtrado["mes_dt"] = pd.to_datetime(df_filtrado["mes"])

    # Preparar tabla
    df_filtrado["abreviatura"] = df_filtrado["codigo_normalizado"].apply(obtener_abreviatura)
    df_filtrado["cuenta_sucursal"] = df_filtrado["codigo_normalizado"] + " (" + df_filtrado["abreviatura"] + ") - " + df_filtrado["sucursal"]

    df_filtrado["mes_anio"] = df_filtrado["mes_dt"].dt.month_name().map(meses_es) + " " + df_filtrado["mes_dt"].dt.year.astype(str)
    df_filtrado["orden_mes"] = df_filtrado["mes_dt"].dt.to_period("M")

    tabla_compras = df_filtrado.pivot_table(
        index="cuenta_sucursal",
        columns="mes_anio",
        values="monto",
        aggfunc="sum",
        fill_value=0
    )

    orden_columnas = df_filtrado.drop_duplicates("mes_anio").sort_values("orden_mes")["mes_anio"].tolist()
    tabla_compras = tabla_compras[orden_columnas]

    # Agregar totales
    tabla_compras["Total Cuenta"] = tabla_compras.sum(axis=1)
    tabla_compras.loc["Total General"] = tabla_compras.sum(axis=0)

    tabla_compras = tabla_compras.rename_axis("Cuenta - Sucursal")
    
    # --- Preparar tabla en formato plano ---
    tabla_formateada = tabla_compras.reset_index()

    # Separar fila total
    mascara_total = tabla_formateada["Cuenta - Sucursal"].str.strip().str.lower() == "total general"
    total_row = tabla_formateada[mascara_total].copy()
    data_sin_total = tabla_formateada[~mascara_total].copy()

    # --- Preparar columnas separadas ---
    # Asegurar que la columna sea string
    data_sin_total["Cuenta - Sucursal"] = data_sin_total["Cuenta - Sucursal"].astype(str)

    # Dividir en dos partes: antes y después de " - "
    data_sin_total[["Cuenta", "Sucursal"]] = data_sin_total["Cuenta - Sucursal"].str.split(" - ", n=1, expand=True)

    # Reordenar columnas para que Cuenta y Sucursal vayan al inicio
    cols = ["Cuenta", "Sucursal"] + [
        c for c in data_sin_total.columns 
        if c not in ["Cuenta", "Sucursal", "Cuenta - Sucursal"]
    ]
    data_sin_total = data_sin_total[cols]

    # Columnas numéricas excluyendo índice y columna Total
    ultima_col = data_sin_total.columns[-1]
    # Columnas numéricas excluyendo la columna Total
    numeric_cols_sin_total = data_sin_total.select_dtypes(include=["number"]).columns.tolist()
    numeric_cols_sin_total = [c for c in numeric_cols_sin_total if c != ultima_col]

    # --- Formateador de valores ---
    value_formatter = JsCode("""
    function(params) { 
        if (params.value == null) return '0.00';
        return params.value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
    """)

    # --- Degradado dinámico (excepto fila Total y columna Total) ---
    min_val = data_sin_total[numeric_cols_sin_total].min().min()
    max_val = data_sin_total[numeric_cols_sin_total].max().max()
    gradient_code = JsCode(f"""
    function(params) {{
        const totalCol = '{ultima_col}';
        if (params.node.rowPinned || 
            (params.data && typeof params.data["Cuenta - Sucursal"] === 'string' &&
            params.data["Cuenta - Sucursal"].trim().toLowerCase() === 'total general')) {{
            return {{
                backgroundColor: '#0B083D',
                color: 'white',
                fontWeight: 'bold',
                textAlign: 'left'
            }};
        }}
        if (params.colDef.field === totalCol) {{
            return {{
                backgroundColor: '#0B083D',
                color: 'white',
                fontWeight: 'bold',
                textAlign: 'left'
            }};
        }}
        let val = params.value;
        let min = {min_val};
        let max = {max_val};
        if (!isNaN(val) && max > min) {{
            let ratio = (val - min) / (max - min);
            let r,g,b;
            if(ratio <= 0.5) {{
                let t = ratio/0.5;
                r = Math.round(204 + t*(0-204));
                g = Math.round(229 + t*(102-229));
                b = Math.round(255 + t*(204-255));
            }} else {{
                let t = (ratio-0.5)/0.5;
                r = 0; g = Math.round(102 + t*(204-102)); b = 204;
            }}
            return {{ backgroundColor: `rgb(${{r}},${{g}},${{b}})`, textAlign:'left' }};
        }}
        return {{ textAlign:'left' }};
    }}
    """)

    # --- Configuración del grid ---
    gb = GridOptionsBuilder.from_dataframe(data_sin_total)
    gb.configure_default_column(resizable=True, filter=False, valueFormatter=value_formatter)

    gb.configure_column(
        "Cuenta",
        pinned="left",
        minWidth=100,
        width=200,
        cellStyle=JsCode("""
            function(params) {
                if (params.node.rowPinned) {
                    return {
                        backgroundColor: '#0B083D',
                        color: 'white',
                        fontWeight: 'bold',
                        textAlign: 'center'
                    };
                }
                return {
                    backgroundColor: '#0B083D',
                    color: 'white',
                    fontWeight: 'bold',
                    textAlign: 'center'
                };
            }
        """)
    )

    # Columna Sucursal (no fija)
    gb.configure_column(
        "Sucursal",
        minWidth=120,
        width=140,
        cellStyle={
            'backgroundColor': '#0B083D',
            'color': 'white',
            'fontWeight': 'bold',
            'textAlign': 'right'
        }
    )

    # Columnas numéricas
    for col in numeric_cols_sin_total:
        gb.configure_column(
            col,
            cellStyle=gradient_code,
            valueFormatter=value_formatter,
            headerClass='header-left',
            minWidth=120,
        )

    # Columna Total
    gb.configure_column(
        ultima_col,
        cellStyle={
            'backgroundColor': '#0B083D',
            'color': 'white',
            'fontWeight': 'bold',
            'textAlign': 'left'
        },
        valueFormatter=value_formatter,
        minWidth=160,
        headerClass='header-left'
    )

    # --- CSS para headers alineados a la izquierda ---
    custom_css = {
        ".header-left": {"text-align": "left"},
        ".ag-center-cols-container .ag-row": {
            "height": "20px",
            "line-height": "16px",
            "padding-top": "2px",
            "padding-bottom": "2px"
        },
        ".ag-pinned-left-cols-container .ag-row": {
            "height": "20px",
            "line-height": "16px",
            "padding-top": "2px",
            "padding-bottom": "2px"
        }
    }

    # --- Responsive en móviles ---
    on_grid_ready = JsCode("""
    function(params) {
        function ajustarColumnas() {
            if (window.innerWidth <= 768) {
                params.api.resetColumnState();
            } else {
                params.api.sizeColumnsToFit();
            }
        }
        ajustarColumnas();
        setTimeout(ajustarColumnas, 300);
        window.addEventListener('resize', ajustarColumnas);
        const gridDiv = params.api.gridBodyCtrl.eGridBody;
        if (window.ResizeObserver) {
            const ro = new ResizeObserver(() => ajustarColumnas());
            ro.observe(gridDiv);
        }
    }
    """)

    grid_options = gb.build()
    grid_options["onGridReady"] = on_grid_ready

    # --- Ajustar fila de totales ---
    total_row = total_row.copy()
    total_row.loc[:, "Cuenta"] = "TOTAL"
    total_row.loc[:, "Sucursal"] = ""

    # --- Fila Total fija ---
    grid_options['pinnedBottomRowData'] = total_row.to_dict('records')

    # --- Render ---
    AgGrid(
        data_sin_total,
        gridOptions=grid_options,
        custom_css=custom_css,
        height=800,
        allow_unsafe_jscode=True,
        theme=AgGridTheme.ALPINE,
        fit_columns_on_grid_load=False,
        columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
        enable_enterprise_modules=False
    )

    # --- Descargar Excel ---
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        tabla_compras.to_excel(writer, sheet_name='Compras')
    processed_data = output.getvalue()

    st.download_button(
        label="📥 Descargar tabla en Excel",
        data=processed_data,
        file_name="compras_por_mes_por_cuenta.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    st.markdown("<br><br>", unsafe_allow_html=True)

    #-------------------- GRÁFICO DE LÍNEAS: COMPRAS MENSUALES POR CUENTA --------------------------------------------------------------------------
    # Asegúrate de que la columna mes_dt exista en df_divisiones_filtra
    if "mes_dt" not in df_divisiones_filtrado.columns:
        df_divisiones_filtrado["mes_dt"] = pd.to_datetime(df_divisiones_filtrado["fecha"]).dt.to_period("M").dt.to_timestamp()

    # Crear columnas mes_nombre y mes_anio en español
    df_divisiones_filtrado["mes_nombre"] = df_divisiones_filtrado["mes_dt"].dt.month_name().map(meses_es)
    df_divisiones_filtrado["mes_anio"] = df_divisiones_filtrado["mes_nombre"] + " " + df_divisiones_filtrado["mes_dt"].dt.year.astype(str)

    # Función para obtener abreviatura de la división
    def obtener_abreviatura(codigo):
        codigo_str = str(codigo).strip()
        for division, info in divisiones.items():
            if codigo_str in info["codigos"]:
                return info["abreviatura"]
        return ""

    # Crear columnas abreviatura y cuenta_sucursal
    df_divisiones_filtrado["abreviatura"] = df_divisiones_filtrado["codigo_normalizado"].apply(obtener_abreviatura)
    df_divisiones_filtrado["cuenta_sucursal"] = (
        df_divisiones_filtrado["codigo_normalizado"].astype(str) + " (" +
        df_divisiones_filtrado["abreviatura"] + ") - " +
        df_divisiones_filtrado["sucursal"]
    )

    # Agrupar datos para plotly (long-form)
    df_grafico = df_divisiones_filtrado.groupby(
        ["mes_anio", "cuenta_sucursal", "abreviatura"], as_index=False
    )["monto"].sum()

    # Definir el orden de los meses
    orden_meses = df_divisiones_filtrado.drop_duplicates("mes_anio").sort_values("mes_dt")["mes_anio"].tolist()

    # Obtener lista de cuentas únicas
    cuentas = df_grafico["cuenta_sucursal"].unique()

    # Crear todas las combinaciones posibles mes-cuenta
    import itertools
    combinaciones = pd.DataFrame(
        list(itertools.product(orden_meses, cuentas)),
        columns=["mes_anio", "cuenta_sucursal"]
    )

    # Merge para completar montos faltantes con cero
    df_grafico = combinaciones.merge(df_grafico, on=["mes_anio", "cuenta_sucursal"], how="left")
    df_grafico["monto"] = df_grafico["monto"].fillna(0)

    # Convertir mes_anio en categoría ordenada
    df_grafico["mes_anio"] = pd.Categorical(df_grafico["mes_anio"], categories=orden_meses, ordered=True)
    df_grafico = df_grafico.sort_values("mes_anio")

    # Selector de sucursales en lugar de cuentas
    sucursales_disponibles = ["Todas"] + sorted(df_grafico["cuenta_sucursal"].apply(lambda x: x.split(" - ")[-1]).unique())

    st.markdown("### Compras mensuales por cuenta")

    # Selector de cuentas
    sucursales_seleccionadas = st.multiselect(
        "Selecciona sucursales a mostrar:",
        sucursales_disponibles,
        default=sucursales_disponibles
    )

    # Filtrar el DataFrame según selección
    df_filtrado = df_grafico[df_grafico["cuenta_sucursal"].isin(sucursales_seleccionadas)]
    # Filtrar según sucursales seleccionadas
    if "Todas" in sucursales_seleccionadas:
        df_filtrado = df_grafico.copy()
    else:
        df_filtrado = df_grafico[df_grafico["cuenta_sucursal"].apply(lambda x: x.split(" - ")[-1]).isin(sucursales_seleccionadas)]

    # Construir un mapa de colores basado en el JSON de sucursales
    color_map = {}
    for cuenta in df_filtrado["cuenta_sucursal"].unique():
        # extraer el nombre de sucursal desde la cadena (después del " - ")
        sucursal = cuenta.split(" - ")[-1]
        color_map[cuenta] = colores_sucursales.get(sucursal, {}).get("color", "#CCCCCC")

    # Mostrar advertencia si no hay datos
    if df_filtrado.empty:
        st.warning("No hay datos para mostrar con las cuentas seleccionadas.")
        st.dataframe(df_grafico.head(10))
    else:
        # Crear gráfico de líneas con customdata incluyendo abreviatura
        fig = px.line(
            df_filtrado,
            x="mes_anio",
            y="monto",
            color="cuenta_sucursal",
            markers=True,
            custom_data=["mes_anio", "cuenta_sucursal", "monto", "abreviatura"],
            color_discrete_map=color_map  # <-- aquí el truco
        )

        # Formato de hovertemplate mostrando abreviatura
        fig.update_traces(
            hovertemplate=(
                "<b>Mes:</b> %{customdata[0]}<br>"
                "<b>Cuenta - Sucursal:</b> %{customdata[1]}<br>"
                "<b>Monto:</b> $%{customdata[2]:,.2f}<br>"
                "<b>División:</b> %{customdata[3]}<extra></extra>"
            )
        )

        fig.update_layout(
            xaxis_title="Mes",
            yaxis_title="Monto (MXN)",
            yaxis_tickformat=",",
            legend_title="Cuenta - Sucursal"
        )

        config = {
            "scrollZoom": True,
            "modeBarButtonsToKeep": ["toImage", "zoom2d", "autoScale2d", "toggleFullscreen"],
            "displaylogo": False
        }

        st.markdown("<div style='margin-top:-30px'></div>", unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True, config=config)


    #---------------- GRAFICAS DE BARRAS: COMPRA POR CUENTA POR MES POR SUCURSAL -----------------
    st.header("Evolución mensual de compras por cuenta")

    if df_divisiones_filtrado.empty:
        st.warning("No hay datos disponibles.")
    else:
        # --- Crear columnas necesarias en df_divisiones_filtrado ---
        def obtener_abreviatura(codigo):
            codigo_str = str(codigo).strip()
            for division, info in divisiones.items():
                if codigo_str in info["codigos"]:
                    return info["abreviatura"]
            return ""

        df_divisiones_filtrado["abreviatura"] = df_divisiones_filtrado["codigo_normalizado"].apply(obtener_abreviatura)
        df_divisiones_filtrado["cuenta_sucursal"] = (
            df_divisiones_filtrado["codigo_normalizado"].astype(str) + " (" +
            df_divisiones_filtrado["abreviatura"] + ") - " +
            df_divisiones_filtrado["sucursal"]
        )
        df_divisiones_filtrado["sucursal_nombre"] = df_divisiones_filtrado["cuenta_sucursal"].str.split(" - ").str[-1]

        # Crear columna mes_nombre en español
        df_divisiones_filtrado["mes_nombre"] = (
            df_divisiones_filtrado["mes_dt"].dt.month_name().map(meses_es) + " " +
            df_divisiones_filtrado["mes_dt"].dt.year.astype(str)
        )

        # --- Agrupar datos por mes y cuenta ---
        df_barras = df_divisiones_filtrado.groupby(["mes_nombre", "cuenta_sucursal"], as_index=False)["monto"].sum()

        # --- Definir orden de meses y cuentas ---
        orden_meses = df_divisiones_filtrado.drop_duplicates("mes_nombre").sort_values("mes_dt", ascending=False)["mes_nombre"].tolist()
        todas_cuentas = df_divisiones_filtrado["cuenta_sucursal"].unique()

        # Crear combinaciones mes-cuenta para completar valores faltantes
        idx = pd.MultiIndex.from_product([orden_meses, todas_cuentas], names=["mes_nombre", "cuenta_sucursal"])
        df_barras = df_barras.set_index(["mes_nombre", "cuenta_sucursal"]).reindex(idx, fill_value=0).reset_index()

        # Añadir sucursal_nombre mediante merge
        df_sucursales = df_divisiones_filtrado.drop_duplicates("cuenta_sucursal")[["cuenta_sucursal", "sucursal_nombre"]]
        df_barras = df_barras.merge(df_sucursales, on="cuenta_sucursal", how="left")

        # Convertir mes_nombre en categoría ordenada
        df_barras["mes_nombre"] = pd.Categorical(df_barras["mes_nombre"], categories=orden_meses, ordered=True)

        # --- Crear gráfico de barras por mes ---
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
                    marker_color=colores_sucursales.get(row["sucursal_nombre"], {}).get("color", "#CCCCCC"),
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