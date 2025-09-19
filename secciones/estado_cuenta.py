import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import json
import io
import xlsxwriter  
import calendar
import math
import plotly.graph_objects as go
import plotly.express as px
from io import BytesIO
from datetime import datetime, timedelta
from utils.api_utils import obtener_estado_cuenta_api
from st_aggrid import AgGrid, GridOptionsBuilder, ColumnsAutoSizeMode, JsCode, AgGridTheme


#================= CARGA DE DATOS ====================
@st.cache_data(ttl=300)
def cargar_estado_cuenta():
    return obtener_estado_cuenta_api()

@st.cache_data(ttl=600)
def cargar_config():
    with open("config_colores.json", "r", encoding="utf-8") as f:
        return json.load(f)
    
# ================== CONFIGURACIÓN =====================
config = cargar_config()
divisiones = config["divisiones"]          # abreviaturas y códigos
colores_sucursales = config["sucursales"]  # colores por sucursal
CREDITO_MAX = 180_000_000                  # límite de crédito
# --- Tema ---
modo = st.get_option("theme.base")  # 'dark' o 'light'
template = "plotly_dark" if modo == "dark" else "plotly_white"

# Función para obtener abreviatura de código
def obtener_abreviatura(codigo):
    for division, info in divisiones.items():
        if codigo in info["codigos"]:
            return info["abreviatura"]
    return ""

# Función para color según días de vencimiento
def color_por_vencimiento(fecha_str, hoy):
    try:
        fecha = datetime.strptime(fecha_str, "%d/%m/%Y")
        diff = (fecha - hoy).days
        if diff < 0: return "red"
        elif diff <= 30: return "orange"
        elif diff <= 60: return "yellow"
        else: return "green"
    except:
        return "transparent"
    
def generar_cuenta_sucursal(df):
    df = df.copy()
    df["cuenta_sucursal"] = df["codigo"] + " (" + df["abreviatura"] + ") - " + df["sucursal"]
    return df

def calcular_vencimientos(df, hoy):
    total_vencido = df[df["fecha_exigibilidad"] < hoy]["total"].sum()
    por_vencer_30 = df[(df["fecha_exigibilidad"] >= hoy) & (df["fecha_exigibilidad"] <= hoy + timedelta(days=30))]["total"].sum()
    por_vencer_90 = df[df["fecha_exigibilidad"] > hoy + timedelta(days=90)]["total"].sum()
    return total_vencido, por_vencer_30, por_vencer_90

def formatear_fechas(df, columna="fecha_exigibilidad"):
    df = df.copy()
    df[columna + "_str"] = df[columna].dt.strftime("%d/%m/%Y")
    return df

#=============================================
def mostrar():
    st.title("Cuadro de estado de cuenta")
    
    df_estado_cuenta, fecha_corte = cargar_estado_cuenta()
    if df_estado_cuenta.empty or fecha_corte is None:
        st.warning("No hay datos de estado de cuenta.")
        return
    
    st.markdown(f"### Estado de cuenta actualizado a {fecha_corte.strftime('%d/%m/%Y')}")
    
    # ----------------- Preparar DataFrame -----------------
    df = df_estado_cuenta.copy()
    df["fecha_exigibilidad"] = pd.to_datetime(df["fecha_exigibilidad"], errors="coerce")
    df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
    df = generar_cuenta_sucursal(df)
    df = formatear_fechas(df, "fecha_exigibilidad")

    # Meta info para merge posterior
    meta = df[["cuenta_sucursal", "codigo", "sucursal", "abreviatura"]].drop_duplicates()

    # Pivot table
    tabla = df.pivot_table(
        index="fecha_exigibilidad",
        columns="cuenta_sucursal",
        values="total",
        aggfunc="sum"
    )
    fechas = sorted(df["fecha_exigibilidad"].dropna().unique())
    tabla = tabla.reindex(fechas).fillna(0)
    
    df_completo = tabla.stack(dropna=False).reset_index(name="total")
    df_completo = df_completo.rename(columns={"level_2": "cuenta_sucursal"})
    df_completo = df_completo.merge(meta, on="cuenta_sucursal", how="left")
    df_completo[["sucursal","codigo","abreviatura"]] = df_completo[["sucursal","codigo","abreviatura"]].fillna({
        "sucursal":"Desconocida",
        "codigo":"Desconocido",
        "abreviatura":""
    })

    # Mostrar tabla
    st.dataframe(df_completo)

    # ----------------- Tarjetas de crédito -----------------
    total_estado_cuenta = df_estado_cuenta["total"].sum()
    credito_disponible = CREDITO_MAX - total_estado_cuenta
    porcentaje_disponible = (credito_disponible / CREDITO_MAX) * 100
    porcentaje_usado = (total_estado_cuenta / CREDITO_MAX) * 100

    col1, col2, col3 = st.columns([1,1,1])
    for col, (titulo, valor) in zip(
        [col1, col2, col3],
        [
            ("💰 Crédito disponible", f"${credito_disponible:,.2f}"),
            ("📊 % Crédito disponible", f"{porcentaje_disponible:.2f}%"),
            ("📈 % Crédito usado", f"{porcentaje_usado:.2f}%")
        ]
    ):
        col.metric(titulo, valor)

    st.markdown("<div class='spacer'></div>", unsafe_allow_html=True)

    # ----------------- Tarjetas de vencimiento -----------------
    hoy = pd.to_datetime(datetime.today().date())
    total_vencido, por_vencer_30, por_vencer_90 = calcular_vencimientos(df_estado_cuenta, hoy)

    col1, col2, col3 = st.columns([1,1,1])
    for col, (titulo, valor) in zip(
        [col1, col2, col3],
        [
            ("🔴 Total vencido", f"${total_vencido:,.2f}"),
            ("🟡 Por vencer en 30 días", f"${por_vencer_30:,.2f}"),
            ("🟢 Por vencer >90 días", f"${por_vencer_90:,.2f}")
        ]
    ):
        col.metric(titulo, valor)

    # ----------------- Próxima exigibilidad -----------------
    fechas_exig = pd.to_datetime(df_estado_cuenta["fecha_exigibilidad"]).dt.date
    fechas_futuras = [f for f in fechas_exig if f >= hoy.date()]
    
    if fechas_futuras:
        proxima_fecha = min(fechas_futuras)
        dias_faltan = (proxima_fecha - hoy.date()).days
        st.markdown(
            f"""
            <div style="
                background-color:#0B083D; 
                color:white; 
                padding:12px; 
                border-radius:10px; 
                text-align:center; 
                font-weight:bold; 
                font-size:16px;
                margin-bottom:15px;
            ">
                📅 Próxima exigibilidad: {proxima_fecha.strftime("%d/%m/%Y")}  
                ⏳ Faltan <span style="color:#FFD700;">{dias_faltan} días</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            """
            <div style="
                background-color:#0B083D; 
                color:white; 
                padding:12px; 
                border-radius:10px; 
                text-align:center; 
                font-weight:bold; 
                font-size:16px;
                margin-bottom:15px;
            ">
                ✅ No hay fechas de exigibilidad futuras.
            </div>
            """,
            unsafe_allow_html=True
        )

    #------------------------------------------ TABLA: ESTADO DE CUENTA -----------------------------------------------------------------------
    # --- Preparar fechas y pivote ---
    df_estado_cuenta["fecha_exigibilidad"] = pd.to_datetime(df_estado_cuenta["fecha_exigibilidad"])
    df_estado_cuenta["fecha_exigibilidad_str"] = df_estado_cuenta["fecha_exigibilidad"].dt.strftime("%d/%m/%Y")
    hoy_str = pd.Timestamp(datetime.today().date()).strftime("%Y-%m-%d")  # para JS
    def obtener_abreviatura(codigo):
        for division, info in divisiones.items():
            if codigo in info["codigos"]:
                return info["abreviatura"]
        return ""
    # --- Enriquecer código con abreviatura ---
    df_estado_cuenta["codigo"] = df_estado_cuenta["codigo_6digitos"].astype(str)
    df_estado_cuenta["abreviatura"] = df_estado_cuenta["codigo"].apply(obtener_abreviatura)
    df_estado_cuenta["codigo"] = df_estado_cuenta["codigo"] + " (" + df_estado_cuenta["abreviatura"] + ")"

    df_pivot = df_estado_cuenta.pivot_table(
        index=["sucursal", "codigo"],  # 👈 aquí el cambio
        columns="fecha_exigibilidad_str",
        values="total",
        aggfunc="sum",
        fill_value=0,
        margins=True,
        margins_name="Total"
    )

    # Ordenar columnas por fecha
    cols_ordenadas = sorted(
        [c for c in df_pivot.columns if c != "Total"],
        key=lambda x: datetime.strptime(x, "%d/%m/%Y")
    )
    if "Total" in df_pivot.columns:
        cols_ordenadas.append("Total")
    df_pivot = df_pivot[cols_ordenadas]
    df_pivot.index = df_pivot.index.set_names(["sucursal", "codigo"])
    df_reset = df_pivot.reset_index()
    #df_reset["codigo"] = df_reset["codigo"].astype(str)

    # --- Separar fila total ---
    mascara_total = (
        df_reset["codigo"].str.strip().str.lower() == "total"
    ) | (
        df_reset["sucursal"].str.strip().str.lower() == "total"
    )
    total_row = df_reset[mascara_total].copy()
    data_sin_total = df_reset[~mascara_total].copy()

    # Columnas numéricas excluyendo índices y columna Total
    ultima_col = data_sin_total.columns[-1]
    numeric_cols_sin_total = [c for c in data_sin_total.columns if c not in ["sucursal", "codigo", ultima_col]]

    # --- Formateador de valores ---
    value_formatter = JsCode("""
    function(params) { 
        if (params.value == null) return '0.00';
        return params.value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
    """)

    # --- Renderer dinámico con barra izquierda y línea inferior ---
    gradient_y_line_renderer = JsCode(f"""
    function(params) {{
        const totalCol = '{ultima_col}';
        const hoy = new Date('{hoy_str}');

        let style = {{
            color: params.node.rowPinned ? 'white':'black',
            fontWeight: params.node.rowPinned ? 'bold':'normal',
            textAlign:'left',
            paddingLeft:'4px',   
            paddingRight:'4px',  
            borderRadius: '2px'
            // borderLeftStyle y borderLeftWidth comentados, ya no habrá líneas
        }};

        if(!params.node.rowPinned && params.data && params.colDef.field !== 'codigo' && params.colDef.field !== 'sucursal' && params.colDef.field !== totalCol) {{
            let val = params.value;
            let min = {data_sin_total[numeric_cols_sin_total].min().min()};
            let max = {data_sin_total[numeric_cols_sin_total].max().max()};

            // degradado de fondo (opcional, puedes dejarlo o quitarlo)
            let bgColor = '#ffffff';
            if(!isNaN(val) && max > min){{
                let ratio = (val - min)/(max - min);
                let r,g,b;
                if(ratio<=0.5){{
                    let t = ratio/0.5;
                    r = Math.round(117+t*(232-117));
                    g = Math.round(222+t*(229-222));
                    b = Math.round(84+t*(70-84));
                }} else {{
                    let t=(ratio-0.5)/0.5;
                    r=232;
                    g=Math.round(229+t*(96-229));
                    b=70;
                }}
                bgColor = 'rgb('+r+','+g+','+b+')';
            }}
            style.backgroundColor = bgColor;

            // --- Se quitan todas las líneas verticales ---
        }} else {{
            style.backgroundColor = '#0B083D';
            // style.borderLeft = 'transparent'; // ya no hace falta
        }}

        return style;
    }}
    """)

    # --- Renderer para fila total anclada (línea superior según vencimiento) ---
    total_row_renderer = JsCode(f"""
    function(params) {{
        const hoy = new Date('{hoy_str}');
        let style = {{
            color: 'white',
            fontWeight: 'bold',
            textAlign: 'left',
            backgroundColor: '#0B083D',
            borderTopStyle: 'solid',
            borderTopWidth: '4px'
        }};
        
        if(params.data && params.colDef.field !== 'codigo' && params.colDef.field !== 'sucursal' && params.value != null) {{
            let fecha_parts = params.colDef.field.split('/');
            if(fecha_parts.length === 3){{
                let fecha_obj = new Date(fecha_parts[2], fecha_parts[1]-1, fecha_parts[0]);
                let diffDias = Math.round((fecha_obj - hoy)/(1000*60*60*24));
                if(diffDias < 0) style.borderTopColor = 'red';
                else if(diffDias <= 30) style.borderTopColor = 'orange';
                else if(diffDias <= 60) style.borderTopColor = 'yellow';
                else style.borderTopColor = 'green';
            }}
        }} else {{
            style.borderTopColor = 'transparent';
        }}
        return style;
    }}
    """)

    def color_por_vencimiento(fecha_str, hoy):
        try:
            fecha = datetime.strptime(fecha_str, "%d/%m/%Y")
            diff = (fecha - hoy).days
            if diff < 0:
                return "red"
            elif diff <= 30:
                return "orange"
            elif diff <= 60:
                return "yellow"
            else:
                return "green"
        except:
            return "transparent"

    # --- Configuración inicial del grid ---
    columnas = list(data_sin_total.columns)
    if "codigo" in columnas and "sucursal" in columnas:
        columnas.remove("codigo")
        columnas.remove("sucursal")
        data_sin_total = data_sin_total[["codigo", "sucursal"] + columnas]

    gb = GridOptionsBuilder.from_dataframe(data_sin_total)
    gb.configure_default_column(resizable=True, filter=False, valueFormatter=value_formatter)

    gb.configure_column(
        "codigo",
        headerName="Código",   # 👈 aquí
        pinned="left",
        minWidth=150,
        width=140,
        cellStyle={
            'backgroundColor': '#0B083D',
            'color': 'white',
            'fontWeight': 'bold',
            'textAlign':'right'
        }
    )

    gb.configure_column(
        "sucursal",
        headerName="Sucursal",   # 👈 aquí
        minWidth=150,
        width=140,
        cellStyle={
            'backgroundColor': '#0B083D',
            'color': 'white',
            'fontWeight': 'bold',
            'textAlign':'right'
        }
    )

    # --- Función JS para color de vencimiento en header ---
    header_vencimiento = JsCode(f"""
    function(params) {{
        const hoy = new Date('{hoy_str}');
        let fecha_parts = params.colDef.field.split('/');
        if(fecha_parts.length === 3){{
            let fecha_obj = new Date(fecha_parts[2], fecha_parts[1]-1, fecha_parts[0]);
            let diffDias = Math.round((fecha_obj - hoy)/(1000*60*60*24));
            let color = 'transparent';
            if(diffDias < 0) color='red';
            else if(diffDias <= 30) color='orange';
            else if(diffDias <= 60) color='yellow';
            else color='green';
            return {{borderBottom: '4px solid ' + color}};
        }}
        return {{}};
    }}
    """)

    for col in numeric_cols_sin_total:
        gb.configure_column(
            col,
            minWidth=100,
            headerClass='header-left',
            headerStyle=header_vencimiento,   # línea en el header
            cellStyle=gradient_y_line_renderer,  # degradado + barra vertical normal
            #pinnedRowCellStyle=total_row_renderer,  # <- línea superior en fila total anclada
            valueFormatter=value_formatter
        )

    # Columna Total (solo estilo)
    gb.configure_column(
        ultima_col,
        minWidth=140,
        headerClass='header-left',
        valueFormatter=value_formatter,
        cellStyle={'backgroundColor': '#0B083D','color':'white','fontWeight':'bold','textAlign':'left'}
    )

    custom_css = {
        # Alineación headers normales
        ".header-left": {"justify-content": "flex-start !important"},
        ".header-right": {"justify-content": "flex-end !important"},

        # Headers de codigo y sucursal → como los normales, texto negro sobre blanco
        ".ag-header-cell[col-id='codigo'] .ag-header-cell-text, .ag-header-cell[col-id='sucursal'] .ag-header-cell-text": {
            "color": "black !important",
            "font-weight": "bold !important",
            "background-color": "white !important",
            "padding-right": "4px",
            "border-bottom": "none !important"   # 👈 les quita el subrayado
        },

        # Para que sigan alineados a la derecha en el header
        ".ag-header-cell[col-id='codigo'] .ag-header-cell-label, .ag-header-cell[col-id='sucursal'] .ag-header-cell-label": {
            "justify-content": "flex-end !important",
            "display": "flex",
            "align-items": "center"
        },

        # Filas (como ya lo tenías)
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

    # --- Toggle arriba de la tabla (antes de construir grid_options) ---
    if "expandir_columnas" not in st.session_state:
        st.session_state.expandir_columnas = False

    col1, col2 = st.columns([8,1])
    with col2:
        if st.button("🔎", help="Expandir columnas al contenido"):
            st.session_state.expandir_columnas = not st.session_state.expandir_columnas

    expandir = st.session_state.expandir_columnas  # ← bandera en Python

    # --- Script para scroll horizontal en móviles ---
    on_grid_ready = JsCode(f"""
    function(params) {{
        const expandir = {str(expandir).lower()};

        // Helpers globales para poder limpiar en re-renders
        function clearHandlers() {{
            try {{
                if (window.__agResizeHandler) {{
                    window.removeEventListener('resize', window.__agResizeHandler);
                    window.__agResizeHandler = null;
                }}
                if (window.__agRO) {{
                    window.__agRO.disconnect();
                    window.__agRO = null;
                }}
            }} catch(e) {{}}
        }}

        // Siempre limpia lo que hubiera de una corrida anterior
        clearHandlers();

        function ajustarColumnas() {{
            if (expandir) return;  // si el toggle está activo, NO toques los anchos
            if (window.innerWidth <= 768) {{
                params.api.resetColumnState();
            }} else {{
                params.api.sizeColumnsToFit();
            }}
        }}

        if (!expandir) {{
            ajustarColumnas();
            setTimeout(ajustarColumnas, 300);

            // Guarda el handler globalmente para poder removerlo en la próxima corrida
            window.__agResizeHandler = ajustarColumnas;
            window.addEventListener('resize', window.__agResizeHandler);

            // Observa cambios de tamaño del grid
            const gridBody = params.api.gridBodyCtrl ? params.api.gridBodyCtrl.eGridBody : null;
            if (window.ResizeObserver && gridBody) {{
                window.__agRO = new ResizeObserver(() => ajustarColumnas());
                window.__agRO.observe(gridBody);
            }}
        }} else {{
            // Expandir activo: auto-size lo haremos aparte y no registramos nada
            clearHandlers();
        }}
    }}
    """)     

    # --- onFirstDataRendered solo cuando expandir = True (para autosize real) ---
    on_first_render = None
    if expandir:
        on_first_render = JsCode("""
        function(params) {
            // Primero ajusta al contenedor para tener una base, luego auto-size por contenido
            // (el setTimeout asegura que ocurra después de cualquier reflow inicial)
            setTimeout(() => {
                try { params.api.sizeColumnsToFit(); } catch(e) {}
                try { params.columnApi.autoSizeAllColumns(); } catch(e) {}
            }, 50);
        }
        """)
    
    grid_options = gb.build()
    hoy_py = datetime.today()
    total_row_styles = {}

    for col in numeric_cols_sin_total:
        color = color_por_vencimiento(col, hoy_py)
        total_row_styles[col] = {
            "color": "white",
            "fontWeight": "bold",
            "textAlign": "left",
            "backgroundColor": "#0B083D",
            "borderTop": f"4px solid {color}"
        }

    # Para la columna "Total"
    total_row_styles[ultima_col] = {
        "color": "white",
        "fontWeight": "bold",
        "textAlign": "left",
        "backgroundColor": "#0B083D"
    }

    grid_options["onGridReady"] = on_grid_ready
    if on_first_render:
            grid_options["onFirstDataRendered"] = on_first_render
    grid_options['pinnedBottomRowData'] = total_row.to_dict('records')

    if st.session_state.expandir_columnas:
        grid_options["onFirstDataRendered"] = JsCode("""
        function(params) {
            params.api.sizeColumnsToFit();  
            setTimeout(() => {
                params.columnApi.autoSizeAllColumns();
            }, 200);
        }
        """)

    # --- Render del grid ---
    # clave distinta para forzar re-montaje cuando cambies el toggle y limpiar listeners viejos
    AgGrid(
        data_sin_total,
        gridOptions=grid_options,
        custom_css=custom_css,
        height=800,
        allow_unsafe_jscode=True,
        theme=AgGridTheme.ALPINE,
        fit_columns_on_grid_load=False,
        columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
        enable_enterprise_modules=False,
        key=f"grid-estado-cuenta-{'expand' if expandir else 'fit'}"
    )

    #--------------------- BOTON DE DESCARGA -----------
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

    #----------------------------------------- TABLA DE FECHA DE VENCIMIENTO -------------------------------------------------------------------------------

    hoy = datetime.today()

    # --- Limpiar nombres de sucursal y códigos ---
    df_estado_cuenta["sucursal"] = df_estado_cuenta["sucursal"].str.strip()
    df_estado_cuenta["codigo_6digitos"] = df_estado_cuenta["codigo_6digitos"].astype(str).str.strip()

    # --- Aplicar abreviaturas ---
    df_estado_cuenta["sucursal_abrev"] = df_estado_cuenta["sucursal"].apply(
        lambda x: config["sucursales"].get(x, {}).get("abreviatura", x)
    )

    def agregar_abrev_division(codigo):
        for div, info in config["divisiones"].items():
            if codigo in info["codigos"]:
                return info['abreviatura']
        return codigo

    df_estado_cuenta["codigo_abrev"] = df_estado_cuenta["codigo_6digitos"].apply(agregar_abrev_division)

    # --- Clasificar cada fila en bucket ---
    def bucket_vencimiento(fecha, hoy):
        diff = (fecha - hoy).days
        if diff < 0:
            return "Vencido"
        elif diff <= 30:
            return "0-30 dias"
        elif diff <= 60:
            return "31-60 dias"
        elif diff <= 90:
            return "61-90 dias"
        else:
            return "91+ dias"

    df_estado_cuenta["bucket_venc"] = df_estado_cuenta["fecha_exigibilidad"].apply(lambda f: bucket_vencimiento(f, hoy))
    df_estado_cuenta["codigo_original"] = df_estado_cuenta["codigo_6digitos"]

    # --- Pivot usando sucursal_abrev y codigo_abrev ---
    df_pivot_bucket = df_estado_cuenta.pivot_table(
        index=["sucursal_abrev", "codigo_abrev", "codigo_original"],
        columns="bucket_venc",
        values="total",
        aggfunc="sum",
        fill_value=0,
        margins=True,
        margins_name="Total"
    )

    # --- Ordenar columnas ---
    orden_buckets = ["Vencido", "0-30 dias", "31-60 dias", "61-90 dias", "91+ dias"]
    cols_presentes = [c for c in orden_buckets if c in df_pivot_bucket.columns]
    if "Total" in df_pivot_bucket.columns:
        cols_presentes.append("Total")
    df_pivot_bucket = df_pivot_bucket[cols_presentes]
    df_pivot_bucket.index = df_pivot_bucket.index.set_names(["sucursal_abrev", "codigo_abrev", "codigo_original"])
    df_reset = df_pivot_bucket.reset_index()

    # --- Separar fila total ---
    mascara_total = (
        df_reset["codigo_original"].str.strip().str.lower() == "total"
    ) | (
        df_reset["sucursal_abrev"].str.strip().str.lower() == "total"
    )
    total_row_bucket = df_reset[mascara_total].copy()
    data_sin_total_bucket = df_reset[~mascara_total].copy()

    # --- Crear columna combinada ---
    data_sin_total_bucket["codigo_sucursal"] = (
        data_sin_total_bucket["codigo_original"] + " - " +
        data_sin_total_bucket["codigo_abrev"] + " - " +
        data_sin_total_bucket["sucursal_abrev"]
    )

    # --- Columnas numéricas ---
    numeric_cols_bucket = [c for c in data_sin_total_bucket.select_dtypes(include='number').columns if c != "Total"]

    if numeric_cols_bucket:
        min_val = data_sin_total_bucket[numeric_cols_bucket].min().min()
        max_val = data_sin_total_bucket[numeric_cols_bucket].max().max()
    else:
        min_val, max_val = 0, 1

    # --- Formatter JS ---
    value_formatter = JsCode("""
    function(params) { 
        if (params.value == null) return '0.00';
        return params.value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
    """)

    # --- Gradient renderer ---
    buckets_cols_js_str = str(numeric_cols_bucket)
    gradient_renderer = JsCode(f"""
    function(params) {{
        let gradientCols = {buckets_cols_js_str};
        let style = {{
            color: params.node.rowPinned ? 'white':'black',
            fontWeight: params.node.rowPinned ? 'bold':'normal',
            textAlign:'left',
            paddingLeft:'4px',
            paddingRight:'4px',
            borderRadius: '2px'
        }};
        if(!params.node.rowPinned && params.data && gradientCols.includes(params.colDef.field)) {{
            let val = params.value;
            let min = {min_val};
            let max = {max_val};
            let bgColor = '#ffffff';
            if(!isNaN(val) && max > min){{
                let ratio = (val - min)/(max - min);
                let r,g,b;
                if(ratio<=0.5){{
                    let t = ratio/0.5;
                    r = Math.round(117+t*(232-117));
                    g = Math.round(222+t*(229-222));
                    b = Math.round(84+t*(70-84));
                }} else {{
                    let t=(ratio-0.5)/0.5;
                    r=232;
                    g=Math.round(229+t*(96-229));
                    b=70;
                }}
                bgColor = 'rgb('+r+','+g+','+b+')';
            }}
            style.backgroundColor = bgColor;
        }} else {{
            style.backgroundColor = '#0B083D';  // azul para Total y filas pinned
        }}
        return style;
    }}
    """)

    # --- Ordenar columnas finales ---
    columnas_finales = ["codigo_sucursal"] + orden_buckets
    if "Total" in data_sin_total_bucket.columns:
        columnas_finales.append("Total")
    columnas_finales = [c for c in columnas_finales if c in data_sin_total_bucket.columns]
    data_sin_total_bucket = data_sin_total_bucket[columnas_finales]

    # --- Calcular ancho dinámico según columnas ---
    # Tomamos el ancho aproximado por columna (ajústalo si quieres más espacio)
    ancho_por_columna = 150
    num_columnas = len(data_sin_total_bucket.columns)
    ancho_total_tabla = ancho_por_columna * num_columnas

    # Máximo ancho para no salirse de la pantalla
    ancho_maximo = 1600  # puedes ajustar según tu layout
    ancho_final = min(ancho_total_tabla, ancho_maximo)

    # --- Configuración AgGrid ---
    gb = GridOptionsBuilder.from_dataframe(data_sin_total_bucket)
    gb.configure_default_column(resizable=True, filter=False, valueFormatter=value_formatter)

    # Columna combinada
    gb.configure_column(
        "codigo_sucursal",
        headerName="Codigo - Sucursal",
        pinned="left",
        minWidth=170,
        cellStyle={'backgroundColor': '#0B083D','color': 'white','fontWeight': 'bold','textAlign':'left'}
    )

    # Buckets numéricos
    for col in orden_buckets:
        if col in data_sin_total_bucket.columns:
            header_class = f"header-{col.replace(' ', '').replace('+','')}"
            gb.configure_column(
                col,
                minWidth=130,
                headerClass=header_class,
                cellStyle=gradient_renderer,
                valueFormatter=value_formatter
            )

    # Columna Total
    if "Total" in data_sin_total_bucket.columns:
        gb.configure_column(
            "Total",
            minWidth=140,
            headerClass='header-total',
            valueFormatter=value_formatter,
            cellStyle={'backgroundColor': '#0B083D','color':'white','fontWeight':'bold','textAlign':'left'}
        )

    # --- Custom CSS para AgGrid ---
    custom_css = {
        ".header-Vencido": {"border-bottom": "4px solid red"},
        ".header-0-30dias": {"border-bottom": "4px solid orange"},
        ".header-31-60dias": {"border-bottom": "4px solid yellow"},
        ".header-61-90dias": {"border-bottom": "4px solid lightgreen"},
        ".header-91+dias": {"border-bottom": "4px solid green"},
        ".header-total": {"border-bottom": "4px solid #0B083D"},
        ".ag-center-cols-container .ag-row": {"height": "20px", "line-height": "16px"},
        ".ag-pinned-left-cols-container .ag-row": {"height": "20px", "line-height": "16px"}
        # --- Ajuste ancho del contenedor ---
        #".ag-root-wrapper": {"width": f"{ancho_final}px", "margin": "auto"}
    }

    grid_options = gb.build()
    grid_options['pinnedBottomRowData'] = total_row_bucket.to_dict('records')

    st.markdown("### Tabla de estado de cuenta agrupada por fecha de vencimiento")
    # --- AgGrid con scroll horizontal ---
    st.markdown("""
    <div style="overflow-x: auto; width: 100%;">
        <div id="grid-container"></div>
    </div>
    """, unsafe_allow_html=True)

    grid_response = AgGrid(
        data_sin_total_bucket,
        gridOptions=grid_options,
        custom_css=custom_css,
        height=700,
        allow_unsafe_jscode=True,
        theme=AgGridTheme.ALPINE,
        fit_columns_on_grid_load=True,
        columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
        enable_enterprise_modules=False
    )

    # --- Capturar la data filtrada/ordenada de AgGrid ---
    df_filtrado = pd.DataFrame(grid_response["data"])

    # --- Agregar la fila de totales al final ---
    if not total_row_bucket.empty:
        df_filtrado = pd.concat([df_filtrado, total_row_bucket], ignore_index=True)

    # --- Función para exportar a Excel ---
    def to_excel(df):
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Vencimiento")
        return output.getvalue()

    # --- Botón de descarga ---
    st.download_button(
        label="📥 Descargar tabla en Excel",
        data=to_excel(df_filtrado),
        file_name="estado_cuenta_vencimiento.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    #----------------------------------- GRAFICO DE ANILLOS ------------------------------------------------------------------------------------------------------------------------
    st.markdown("### Distribución de la deuda según la fecha de exigibilidad")
    # --- helper para formato moneda ---
    def fmt(v):
        try:
            return f"${float(v):,.2f}"
        except Exception:
            return "$0.00"

    # Asegura que estas columnas existan y tipos correctos
    df_estado_cuenta["fecha_exigibilidad_str"] = df_estado_cuenta["fecha_exigibilidad"].dt.strftime("%d/%m/%Y")
    df_estado_cuenta["codigo"] = df_estado_cuenta["codigo_6digitos"].astype(str)

    fechas_ordenadas = sorted(
        df_completo["fecha_exigibilidad_str"].unique(),
        key=lambda x: pd.to_datetime(x, format="%d/%m/%Y")
    )

    # Loop: 2 gráficos por fila
    for i in range(0, len(fechas_ordenadas), 2):
        col1, col2 = st.columns(2)
        for j, col in enumerate([col1, col2]):
            if i + j >= len(fechas_ordenadas):
                break

            fecha = fechas_ordenadas[i + j]
            # --- dataset de esa fecha ---
            #df_fecha_raw = df_estado_cuenta[df_estado_cuenta["fecha_exigibilidad_str"] == fecha].copy()
            df_grafico_base = df_completo.copy()
            df_fecha_raw = df_completo[df_completo["fecha_exigibilidad_str"] == fecha].copy()

            # MUY IMPORTANTE: agrupar por sucursal + cuenta para evitar duplicados
            df_fecha = (
                df_fecha_raw.groupby(["sucursal", "cuenta_sucursal", "codigo", "abreviatura"], as_index=False)["total"]
                .sum()
            )

            # Totales por sucursal (para texto del nodo padre)
            tot_por_suc = df_fecha.groupby("sucursal", as_index=False)["total"].sum().rename(columns={"total": "total_sucursal"})
            map_tot_suc = dict(zip(tot_por_suc["sucursal"], tot_por_suc["total_sucursal"]))

            # --- construir nodos: ids, parents, values, labels, colors, text, hover ---
            ids, parents, values, labels, colors, texts, hovertexts = [], [], [], [], [], [], []

            # Nodos de sucursal (padres)
            for _, r in tot_por_suc.iterrows():
                suc = r["sucursal"]
                t_suc = r["total_sucursal"]
                sid = f"S|{suc}"
                ids.append(sid)
                parents.append("")                  # raíz implícita
                values.append(t_suc)                # branchvalues='total' y valor del padre = suma cuentas
                labels.append(suc)
                colors.append(colores_sucursales.get(suc, {}).get("color", "#808080"))
                texts.append(fmt(t_suc))            # muestra total sucursal en el anillo interno
                hovertexts.append(
                    f"<b>Fecha:</b> {fecha}<br>"
                    f"<b>Sucursal:</b> {suc}<br>"
                    f"<b>Total Sucursal:</b> {fmt(t_suc)}"
                )

            # Nodos de cuenta (hijas)
            # Orden estable por sucursal para consistencia visual
            df_fecha = df_fecha.sort_values(["sucursal", "cuenta_sucursal"]).reset_index(drop=True)
            for _, r in df_fecha.iterrows():
                suc = r["sucursal"]
                cuenta = r["cuenta_sucursal"]
                monto = float(r["total"])
                codigo = r["codigo"]
                abrev = r["abreviatura"]
                t_suc = map_tot_suc.get(suc, 0.0)

                cid = f"A|{suc}|{cuenta}"
                ids.append(cid)
                parents.append(f"S|{suc}")
                values.append(monto)
                labels.append(cuenta)                      # etiqueta externa = cuenta (como querías)
                colors.append(colores_sucursales.get(suc, {}).get("color", "#808080"))   # color por sucursal
                texts.append(fmt(monto))                   # muestra monto cuenta en el anillo externo
                hovertexts.append(
                    f"<b>Fecha:</b> {fecha}<br>"
                    f"<b>Código:</b> {codigo}<br>"
                    f"<b>Sucursal:</b> {suc}<br>"
                    f"<b>División:</b> {abrev}<br>"
                    f"<b>Monto Cuenta:</b> {fmt(monto)}<br>"
                    f"<b>Total Sucursal:</b> {fmt(t_suc)}"
                )

            # --- Sunburst GO: control total, sin customdata que se desordene ---
            fig = go.Figure(
                go.Sunburst(
                    ids=ids,
                    parents=parents,
                    values=values,
                    labels=labels,
                    text=texts,                 # monto visible en cada porción
                    textinfo="label+text",
                    insidetextorientation="horizontal",
                    marker=dict(
                        colors=colors,
                        line=dict(color="white", width=1)
                    ),
                    branchvalues="total",
                    hovertext=hovertexts,
                    hovertemplate="%{hovertext}<extra></extra>"
                )
            )

            fig.update_layout(
                title={
                    'text': f"Distribución por cuenta - {fecha}",
                    'x': 0.5,            # centrado
                    'xanchor': 'center', # ancla en el centro
                    'yanchor': 'top'     # opcional: ancla arriba
                },
                title_font=dict(size=18, color="#E1E1EC", family="Arial"),
                template="plotly_white",
                margin=dict(t=60, l=0, r=0, b=0)
            )

            col.plotly_chart(fig, use_container_width=True)
            st.markdown("<br><br>", unsafe_allow_html=True)

    #----------------------------------- GRAFICO DE ANILLOS: SOLO VENCIDAS -----------------------------------------------------------------------------------
    st.markdown("### Distribución de la deuda vencida (todas las fechas)")

    # --- helper para formato moneda ---
    def fmt(v):
        try:
            return f"${float(v):,.2f}"
        except Exception:
            return "$0.00"

    # Fecha de hoy para detectar vencidas
    hoy = pd.Timestamp.today().normalize()

    # Filtrar solo fechas vencidas
    df_vencidas = df_completo[df_completo["fecha_exigibilidad"] < hoy].copy()

    if not df_vencidas.empty:
        # Agrupar por sucursal + cuenta
        df_vencidas_group = (
            df_vencidas.groupby(["sucursal", "cuenta_sucursal", "codigo", "abreviatura"], as_index=False)["total"]
            .sum()
        )

        # Totales por sucursal (para nodos padres)
        tot_por_suc = (
            df_vencidas_group.groupby("sucursal", as_index=False)["total"].sum()
            .rename(columns={"total": "total_sucursal"})
        )
        map_tot_suc = dict(zip(tot_por_suc["sucursal"], tot_por_suc["total_sucursal"]))

        # --- 🚀 Construcción de tabla para exportar ---
        export_rows = []
        for _, row in df_vencidas_group.iterrows():
            suc = row["sucursal"]
            cuenta = row["cuenta_sucursal"]
            monto_cuenta = row["total"]
            monto_sucursal = map_tot_suc.get(suc, 0.0)
            export_rows.append([suc, monto_sucursal, cuenta, monto_cuenta])

        df_export = pd.DataFrame(export_rows, columns=["Sucursal", "Monto sucursal", "Cuenta sucursal", "Monto cuenta"])

        # Crear Excel en memoria
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            df_export.to_excel(writer, index=False, sheet_name="Deuda vencida")
            workbook  = writer.book
            worksheet = writer.sheets["Deuda vencida"]

            # Combinar celdas de sucursal y monto sucursal
            row_start = 1  # ExcelWriter escribe encabezados en la fila 0
            for suc in df_export["Sucursal"].unique():
                df_suc = df_export[df_export["Sucursal"] == suc]
                if len(df_suc) > 1:
                    # Columna 0 = Sucursal, Columna 1 = Monto sucursal
                    worksheet.merge_range(row_start, 0, row_start + len(df_suc) - 1, 0, suc)
                    worksheet.merge_range(row_start, 1, row_start + len(df_suc) - 1, 1, df_suc["Monto sucursal"].iloc[0])
                row_start += len(df_suc)

        buffer.seek(0)

        # Botón de descarga
        st.download_button(
            label="📥 Descargar tabla en Excel",
            data=buffer,
            file_name="deuda_vencida.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # --- Sunburst GO ---
        ids, parents, values, labels, colors, texts, hovertexts = [], [], [], [], [], [], []

        # Nodos de sucursal
        for _, r in tot_por_suc.iterrows():
            suc = r["sucursal"]
            t_suc = r["total_sucursal"]
            sid = f"S|{suc}"
            ids.append(sid)
            parents.append("")
            values.append(t_suc)
            labels.append(suc)
            colors.append(colores_sucursales.get(suc, {}).get("color", "#808080"))
            texts.append(fmt(t_suc))
            hovertexts.append(f"<b>Sucursal:</b> {suc}<br><b>Total vencido sucursal:</b> {fmt(t_suc)}")

        # Nodos de cuenta
        df_vencidas_group = df_vencidas_group.sort_values(["sucursal", "cuenta_sucursal"]).reset_index(drop=True)
        for _, r in df_vencidas_group.iterrows():
            suc = r["sucursal"]
            cuenta = r["cuenta_sucursal"]
            monto = float(r["total"])
            codigo = r["codigo"]
            abrev = r["abreviatura"]
            t_suc = map_tot_suc.get(suc, 0.0)

            cid = f"A|{suc}|{cuenta}"
            ids.append(cid)
            parents.append(f"S|{suc}")
            values.append(monto)
            labels.append(cuenta)
            colors.append(colores_sucursales.get(suc, {}).get("color", "#808080"))
            texts.append(fmt(monto))
            hovertexts.append(
                f"<b>Sucursal:</b> {suc}<br>"
                f"<b>Código:</b> {codigo}<br>"
                f"<b>División:</b> {abrev}<br>"
                f"<b>Monto vencido:</b> {fmt(monto)}<br>"
                f"<b>Total sucursal:</b> {fmt(t_suc)}"
            )

        fig_vencidas = go.Figure(
            go.Sunburst(
                ids=ids,
                parents=parents,
                values=values,
                labels=labels,
                text=texts,
                textinfo="label+text",
                insidetextorientation="horizontal",
                marker=dict(colors=colors, line=dict(color="white", width=1)),
                branchvalues="total",
                hovertext=hovertexts,
                hovertemplate="%{hovertext}<extra></extra>"
            )
        )

        fig_vencidas.update_layout(
            title={"text": "Monto vencido", "x": 0.5, "xanchor": "center", "yanchor": "top"},
            title_font=dict(size=18, color="#E1E1EC", family="Arial"),
            template="plotly_white",
            margin=dict(t=60, l=0, r=0, b=0)
        )

        st.plotly_chart(fig_vencidas, use_container_width=True)

    else:
        st.info("✅ No hay deuda vencida.")

    #------------------------------------------------------- CALENDARIO ------------------------------------------------------------------------------------------------------------------
    st.markdown("### Calendario de fechas de exigibilidad")
    # --- Leyenda de colores arriba ---
    st.markdown("""
    <div style="display:flex; gap:20px; flex-wrap:wrap; font-size:14px; color:black;">
    <div><span style="background-color:#ff6666; padding:4px 12px; border-radius:4px; color:black;">Vencido</span></div>
    <div><span style="background-color:#ffcc66; padding:4px 12px; border-radius:4px; color:black;">0-30 días</span></div>
    <div><span style="background-color:#ffff99; padding:4px 12px; border-radius:4px; color:black;">31-60 días</span></div>
    <div><span style="background-color:#ccff99; padding:4px 12px; border-radius:4px; color:black;">61-90 días</span></div>
    <div><span style="background-color:#99ff99; padding:4px 12px; border-radius:4px; color:black;">91+ días</span></div>
    <div><span style="background-color:#66b3ff; padding:4px 12px; border-radius:4px; color:black;">Día actual</span></div>
    </div>
    """, unsafe_allow_html=True)
    # --- Datos ---
    hoy = datetime.today()
    df_estado_cuenta["fecha_exigibilidad"] = pd.to_datetime(df_estado_cuenta["fecha_exigibilidad"])

    # --- Colores según tema ---
    line_color = "#ffffff" if modo == "dark" else "#000000"   # bordes de las celdas
    day_text_color = "#ffffff" if modo == "dark" else "#000000"  # números de los días
    bg_color = "#ffffff" if modo == "dark" else "#0e1117"  # s
    text_color = "#ffffff" if modo == "dark" else "#000000"

    def clasificar_estado(fecha, hoy):
        diff = (fecha - hoy).days
        if diff < 0:
            return "Vencido"
        elif diff <= 30:
            return "0-30 días"
        elif diff <= 60:
            return "31-60 días"
        elif diff <= 90:
            return "61-90 días"
        else:
            return "91+ días"

    df_estado_cuenta["estado"] = df_estado_cuenta["fecha_exigibilidad"].apply(lambda f: clasificar_estado(f, hoy))

    color_map = {
        "Vencido": "#ff6666",
        "0-30 días": "#ffcc66",
        "31-60 días": "#ffff99",
        "61-90 días": "#ccff99",
        "91+ días": "#99ff99",
        None: "#ffffff"
    }

    # --- Meses ---
    fecha_min = df_estado_cuenta["fecha_exigibilidad"].min().replace(day=1)
    fecha_max = df_estado_cuenta["fecha_exigibilidad"].max().replace(day=28) + pd.offsets.MonthEnd(1)
    meses = pd.date_range(start=fecha_min, end=fecha_max, freq="MS")
    meses_es = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

    # --- Columnas por fila ---
    cols_per_row = 4
    total_rows = math.ceil(len(meses)/cols_per_row)
    row_cols = []
    for i in range(total_rows):
        row_cols.append(st.columns(cols_per_row))

    # --- Columnas para todos los meses en una fila ---
    cols = st.columns(len(meses))

    for idx, m in enumerate(meses):
        with cols[idx]:
            cal = calendar.Calendar(firstweekday=0)
            month_matrix = cal.monthdatescalendar(m.year, m.month)

            fig = go.Figure()

            # Estados presentes en el mes
            dias_mes = df_estado_cuenta[df_estado_cuenta["fecha_exigibilidad"].dt.month == m.month]
            estados_presentes = dias_mes["estado"].unique()
            leyenda = [(estado, color_map[estado]) for estado in estados_presentes]

            # Dibujar celdas de cada día
            for week_idx, week in enumerate(month_matrix):
                for day_idx, day in enumerate(week):
                    if day.month == m.month:
                        estado = df_estado_cuenta.loc[df_estado_cuenta["fecha_exigibilidad"].dt.date == day, "estado"]
                        estado = estado.values[0] if len(estado) > 0 else None
                        color = color_map[estado]

                        if day == hoy.date():
                            color = "#66b3ff"   # Azul especial para día actual

                        x0, x1 = day_idx, day_idx + 1
                        y0, y1 = -week_idx, -week_idx + 1

                        fig.add_shape(
                            type="rect",
                            x0=x0, x1=x1, y0=y0, y1=y1,
                            line=dict(color=line_color, width=1),   # antes "black"
                            fillcolor=color
                        )

                        fig.add_annotation(
                            x=(x0 + x1)/2,
                            y=(y0 + y1)/2,
                            text=str(day.day),
                            showarrow=False,
                            font=dict(size=12, color=day_text_color)   # antes sin color
                        )

            # Nombre del mes (más separado del calendario)
            fig.add_annotation(
                x=3.5,
                y=2.9,
                text=f"{meses_es[m.month-1]} {m.year}",
                showarrow=False,
                font=dict(size=14)
            )

            # Nombres de los días
            for i, day_name in enumerate(["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]):
                fig.add_annotation(
                    x=i + 0.5,
                    y=1.6,
                    text=day_name,
                    showarrow=False,
                    font=dict(size=10)
                )

            # Ejes sin ticks ni controles, escala cuadrada
            fig.update_xaxes(showgrid=False, zeroline=False, showticklabels=False, range=[0,7])
            fig.update_yaxes(showgrid=False, zeroline=False, showticklabels=False, range=[-6,3], scaleanchor="x")

            fig.update_layout(
                template=template,
                paper_bgcolor=bg_color,
                plot_bgcolor=bg_color,
                margin=dict(l=10, r=10, t=6, b=8),
                height=400,
                autosize=True,
                dragmode=False,
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.15,
                    xanchor="center",
                    x=0.5,
                    font=dict(size=12, color=text_color),
                    bgcolor=bg_color,
                )
            )

            # --- Leyenda centrada debajo del calendario ---
            leyenda_y = -5.5
            if leyenda:
                total_width = len(leyenda) * 1.2
                start_x = (7 - total_width)/2
                for i, (estado, color) in enumerate(leyenda):
                    # Cuadrito
                    x0 = start_x + i*1.2
                    x1 = x0 + 0.5
                    fig.add_shape(
                        type="rect",
                        x0=x0, x1=x1,
                        y0=leyenda_y, y1=leyenda_y+0.3,
                        fillcolor=color,
                        line=dict(color="black")
                    )
                    # Texto al lado del cuadrito
                    fig.add_annotation(
                        x=x1 + 0.1,
                        y=leyenda_y + 0.15,
                        text=estado,
                        showarrow=False,
                        font=dict(size=9),
                        xanchor="left",
                        yanchor="middle"
                    )

            # --- Mostrar gráfico sin barra de herramientas ---
            st.plotly_chart(fig, use_container_width=False, config={'displayModeBar': False})

    # --------------------------------- Gráfico: montos por fecha de exigibilidad ---------------------------------------------------------------------------------------
    # --- Preparación de datos ---
    hoy = pd.to_datetime("today").normalize()

    df_vencimientos = (
        df_estado_cuenta.copy()
    )

    # Normalizamos la fecha al primer día del mes (para agrupar por mes)
    df_vencimientos["mes"] = df_vencimientos["fecha_exigibilidad"].dt.to_period("M").dt.to_timestamp()

    # Clasificamos según el rango de días
    df_vencimientos["dias_diferencia"] = (df_vencimientos["fecha_exigibilidad"] - hoy).dt.days

    def clasificar(dias):
        if dias < 0:
            return "Vencido"
        elif dias <= 60:
            return "≤ 60 días"
        elif dias <= 90:
            return "61–90 días"
        else:
            return "> 90 días"

    # --- Agrupamos por mes y categoría conservando fecha exacta ---
    df_vencimientos["categoria"] = df_vencimientos["dias_diferencia"].apply(clasificar)
    df_vencimientos["fecha_str"] = df_vencimientos["fecha_exigibilidad"].dt.strftime("%d-%m-%Y")

    df_agrupado = (
        df_vencimientos.groupby(["mes", "categoria"])  # agrupamos
        .agg({
            "total": "sum",
            "fecha_str": lambda x: ", ".join(sorted(set(x)))  # guardamos fechas únicas del mes
        })
        .reset_index()
    )

    # --- Gráfico ---
    colores = {
        "Vencido": "#ff4d4d",
        "≤ 60 días": "#ffd633",
        "61–90 días": "#66cc66",
        "> 90 días": "#b3b3b3"
    }

    # --- Gráfico ---
    fig_venc = px.bar(
        df_agrupado,
        x="mes",
        y="total",
        color="categoria",
        color_discrete_map=colores,
        text="total",
        custom_data=["fecha_str", "categoria"],  # 👈 agregamos customdata
        labels={"mes": "Mes de exigibilidad", "total": "Monto total", "categoria": "Estado"},
        title="📊 Montos a vencer agrupados por mes"
    )

    # --- Hovertemplate ---
    fig_venc.update_traces(
        hovertemplate=(
            "<b>Mes:</b> %{x|%b %Y}<br>"
            "<b>Estado:</b> %{customdata[1]}<br>"
            "<b>Fechas exactas:</b> %{customdata[0]}<br>"
            "<b>Monto:</b> $%{y:,.2f}<extra></extra>"
        )
    )

    fig_venc.update_traces(texttemplate="%{text:,.0f}", textposition="outside")

    fig_venc.update_layout(
        xaxis=dict(tickformat="%b %Y"),
        bargap=0.2,
        height=500,
        margin=dict(l=40, r=20, t=60, b=40),
        template="plotly_white"
    )

    st.plotly_chart(fig_venc, use_container_width=True)

    #----------------------------------
    # --- Agrupamos por categoría (para el pastel) ---
    df_pastel = (
        df_vencimientos.groupby("categoria")["total"]
        .sum()
        .reset_index()
    )

    # --- Colores ---
    colores = {
        "Vencido": "#ff4d4d",
        "≤ 60 días": "#ffd633",
        "61–90 días": "#66cc66",
        "> 90 días": "#b3b3b3"
    }

    # --- Gráfico de pastel ---
    fig_pie = px.pie(
        df_pastel,
        names="categoria",
        values="total",
        color="categoria",
        color_discrete_map=colores,
        hole=0.4,  # 👈 si quieres tipo "dona"
    )

    # --- Hovertemplate ---
    fig_pie.update_traces(
        textposition="inside",
        textinfo="percent+label",
        hovertemplate=(
            "<b>Estado:</b> %{label}<br>"
            "<b>Monto:</b> $%{value:,.2f}<br>"
            "<b>Porcentaje:</b> %{percent}<extra></extra>"
        )
    )

    fig_pie.update_layout(
        title="🥧 Distribución de montos por estado de exigibilidad",
        height=500,
        margin=dict(l=40, r=20, t=60, b=40),
        template="plotly_white"
    )

    st.plotly_chart(fig_pie, use_container_width=True)


    #-------------------------------------- GRAFICO DE LÍNEAS DEL ESTADO DE CUENTA -----------------------------------------------------------
    # ------------------ Cargar configuración de colores y divisiones ------------------
    st.markdown("### Gráfico del comportamiento de la deuda según las fechas de exigibilidad")
    with open("config_colores.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    divisiones = config["divisiones"]
    colores_sucursales = config["sucursales"]

    # ------------------ Función para abreviatura ------------------
    def obtener_abreviatura(codigo):
        for division, info in divisiones.items():
            if codigo in info["codigos"]:
                return info["abreviatura"]
        return ""

    # ------------------ Preparar DataFrame base ------------------
    df = df_estado_cuenta.copy()
    df["fecha_exigibilidad"] = pd.to_datetime(df["fecha_exigibilidad"], errors="coerce")
    df["codigo"] = df["codigo_6digitos"].astype(str)
    df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
    df["abreviatura"] = df["codigo"].apply(obtener_abreviatura)
    df["cuenta_sucursal"] = df["codigo"] + " (" + df["abreviatura"] + ") - " + df["sucursal"]

    meta = df[["cuenta_sucursal", "codigo", "sucursal", "abreviatura"]].drop_duplicates()

    # ------------------ Construir universo de fechas y rellenar huecos a 0 ------------------
    tabla = df.pivot_table(
        index="fecha_exigibilidad",
        columns="cuenta_sucursal",
        values="total",
        aggfunc="sum"
    )
    fechas = sorted(df["fecha_exigibilidad"].dropna().unique())
    tabla = tabla.reindex(fechas).fillna(0)
    df_completo = tabla.stack(dropna=False).reset_index(name="total").rename(columns={"level_2": "cuenta_sucursal"})
    df_completo = df_completo.merge(meta, on="cuenta_sucursal", how="left")
    df_completo[["sucursal","codigo","abreviatura"]] = df_completo[["sucursal","codigo","abreviatura"]].fillna({
        "sucursal":"Desconocida",
        "codigo":"Desconocido",
        "abreviatura":""
    })
    df_completo["fecha_exigibilidad_str"] = df_completo["fecha_exigibilidad"].dt.strftime("%d/%m/%Y")
    fechas_ordenadas = sorted(df_completo["fecha_exigibilidad_str"].unique(),
                            key=lambda x: pd.to_datetime(x, format="%d/%m/%Y"))
    
    # ------------------ Funciones auxiliares ------------------
    def get_color(suc):
        if suc == "Todas":
            return "#555555"
        return colores_sucursales.get(suc, {}).get("color", "#555555")

    def get_abrev(suc):
        if suc == "Todas":
            return "Todas"
        return colores_sucursales.get(suc, {}).get("abreviatura", suc[:3])

    # ------------------ Selector de sucursales ------------------
    sucursales_disponibles = ["Todas"] + sorted(df_completo["sucursal"].dropna().unique().tolist())
    sucursales_seleccionadas = st.multiselect(
        "Selecciona sucursales a mostrar:",
        sucursales_disponibles,
        default=sucursales_disponibles
    )

    # ------------------ Inyectar CSS para colorear los seleccionados ------------------
    css = "<style>"
    for suc in sucursales_disponibles:
        color = get_color(suc)
        # Streamlit envía los items seleccionados dentro de <div class="css-... multiValue"> con <span>
        # Esto aplica el fondo solo a los items que contengan el texto exacto
        css += f"""
        div[data-baseweb='select'] span:has-text('{suc}') {{
            background-color: {color} !important;
            color: white !important;
            border-radius: 6px !important;
            padding: 2px 6px !important;
            font-weight: 600 !important;
        }}
        """
    css += "</style>"

    st.markdown(css, unsafe_allow_html=True)

    # ------------------ Filtrar el DataFrame según selección ------------------
    if "Todas" in sucursales_seleccionadas:
        df_filtrado = df_completo.copy()
    else:
        df_filtrado = df_completo[df_completo["sucursal"].isin(sucursales_seleccionadas)]

    # ------------------ Colores por cuenta para el gráfico ------------------
    color_cuentas = {
        row["cuenta_sucursal"]: colores_sucursales.get(row["sucursal"], {}).get("color", "#808080")
        for _, row in meta.iterrows()
    }

    # ------------------ Gráfico de líneas ------------------
    fig = px.line(
        df_filtrado,
        x="fecha_exigibilidad_str",
        y="total",
        color="cuenta_sucursal",
        color_discrete_map=color_cuentas,
        custom_data=["sucursal", "codigo", "abreviatura"]
    )

    fig.update_traces(
        mode="lines+markers",
        marker=dict(size=6, symbol="circle"),
        connectgaps=False,
        hovertemplate=(
            "<b>Fecha:</b> %{x}<br>"
            "<b>Código:</b> %{customdata[1]}<br>"
            "<b>Sucursal:</b> %{customdata[0]}<br>"
            "<b>División:</b> %{customdata[2]}<br>"
            "<b>Monto:</b> $%{y:,.2f}<extra></extra>"
        )
    )

    fig.update_layout(
        xaxis_title="Fecha de exigibilidad",
        yaxis_title="Monto",
        hovermode="closest",
        template="plotly_white",
        margin=dict(t=20, b=20)
    )

    st.plotly_chart(fig, use_container_width=True)
