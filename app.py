import streamlit as st
import pandas as pd
from datetime import datetime
import json
from supabase import create_client, Client
import plotly.express as px

# -----------------
# 1. CONFIGURACIÓN DE PÁGINA 
# -----------------
st.set_page_config(page_title="Fremec - Sistema", page_icon="🏭", layout="wide", initial_sidebar_state="expanded")

# -----------------
# 2. CONEXIÓN A BASE DE DATOS
# -----------------
@st.cache_resource
def init_connection() -> Client:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except KeyError:
        st.error("⚠️ Faltan las variables SUPABASE_URL o SUPABASE_KEY en tu archivo .streamlit/secrets.toml!")
        st.stop()

supabase = init_connection()

# -----------------
# FUNCIONES AUXILIARES DE AUDITORÍA
# -----------------
def registrar_auditoria(usuario, tabla, accion, descripcion):
    """Envía un registro en tiempo real a la tabla auditoria."""
    try:
        supabase.table("auditoria").insert({
            "usuario_accion": usuario,
            "tabla_afectada": tabla,
            "accion_realizada": accion,
            "detalles": descripcion
        }).execute()
    except Exception as e:
        print(f"Error escribiendo en auditoría: {e}")

# Manejo de la Sesión
if "user_data" not in st.session_state:
    st.session_state["user_data"] = None
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

# -----------------
# PANTALLA DE LOGIN
# -----------------
if not st.session_state["logged_in"]:
    st.markdown("""
    <div style='display: flex; flex-direction: column; align-items: center; margin-top: 50px; margin-bottom: 40px;'>
        <div style='display: flex; align-items: center; justify-content: center;'>
            <div style="width: 170px; height: 190px; overflow: hidden; display: flex; justify-content: flex-start; margin-right: 15px;">
                <img src="https://www.fremec.com.ar/img/logo.svg" style="height: 190px; max-width: none;">
            </div>
            <div style='text-align: left; display: flex; flex-direction: column; justify-content: center; font-family: "Segoe UI", sans-serif;'>
                <span style='color: #0056b3; font-size: 80px; font-weight: 700; line-height: 0.9;'>FREMEC</span>
                <span style='color: #64748b; font-size: 14px; margin-top: 5px; font-weight: 500;'>Cable de comandos</span>
            </div>
        </div>
        <h3 style='color: #64748b; margin-top: 40px;'>Portal de Empleados</h3>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            user_cred = st.text_input("Usuario o Correo Electrónico")
            password = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
            
            if submit:
                res1 = supabase.table("usuarios_envasadores").select("*").eq("nombre", user_cred).eq("password", password).execute()
                res2 = supabase.table("usuarios_envasadores").select("*").eq("email", user_cred).eq("password", password).execute()
                
                usuario_valido = None
                if res1.data:
                    usuario_valido = res1.data[0]
                elif res2.data:
                    usuario_valido = res2.data[0]
                
                if usuario_valido:
                    st.session_state["logged_in"] = True
                    st.session_state["user_data"] = usuario_valido
                    registrar_auditoria(usuario_valido["nombre"], "sistema", "LOGIN", "El usuario inició sesión en el sistema.")
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas o usuario no existe.")
                    
    st.stop() 

# =========================================================================
# CONTEXTO DEL LOGUEADO
# =========================================================================
user_ctx = st.session_state["user_data"]
es_admin = user_ctx.get("permiso_abm", False)
# Convertimos permiso_bi a boolean seguro
puede_bi = bool(user_ctx.get("permiso_bi", False))
puede_envasar = user_ctx.get("permiso_envasado", False)
nombre_activo = user_ctx["nombre"]

def logout():
    registrar_auditoria(nombre_activo, "sistema", "LOGOUT", "Usuario cerró sesión.")
    st.session_state["logged_in"] = False
    st.session_state["user_data"] = None

# -----------------
# ESTILOS UI NATIVA 
# -----------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;600&display=swap');
    .stApp { background-color: #f4f5f7; font-family: 'Segoe UI', sans-serif; }
    
    [data-testid="stSidebar"] { background-color: #2c395a; color: #ffffff; }
    [data-testid="stSidebar"]::before { border-right: none; }
    
    /* Estilo para el botón Cerrar Sesión del sidebar */
    [data-testid="stSidebar"] button { color: #2c395a !important; background-color: #ffffff !important; border-color: #ffffff !important; }
    [data-testid="stSidebar"] button p { color: #2c395a !important; font-weight: 600 !important; }
    [data-testid="stSidebar"] button:hover { background-color: #e2e8f0 !important; border-color: #e2e8f0 !important; }
    [data-testid="stSidebar"] button:hover p { color: #2c395a !important; }

    div[role="radiogroup"] label p { color: #ffffff !important; font-size: 16px; }
    div[role="radiogroup"] { color: #ffffff !important; }
    
    h1 { color: #64748b; font-weight: 400 !important; font-size: 26px !important; margin-bottom: 20px;}

    .custom-table { width: 100%; border-collapse: collapse; font-size: 14px; color: #4b5563; background-color: #ffffff; }
    .custom-table th { background-color: #e2e8f0; color: #475569; font-weight: 600; text-align: left; padding: 10px 15px; border-bottom: 2px solid #cbd5e1; }
    .custom-table td { padding: 10px 15px; }
    .custom-table tr:nth-child(even) { background-color: #f8fafc; }
    .custom-table tr:nth-child(odd) { background-color: #e0e7ff; }

    .top-bar { background-color: #cfd8dc; padding: 10px 20px; margin: -6rem -5rem 1rem -5rem; display: flex; align-items: center; border-bottom: 1px solid #b0bec5; justify-content: space-between;}
    .search-input { background-color: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px 12px; width: 300px; color: #475569; box-shadow: inset 0 1px 2px rgba(0,0,0,0.05); }
    [data-testid="stHeader"] {display: none;}
</style>
""", unsafe_allow_html=True)

# -----------------
# SIDEBAR
# -----------------
with st.sidebar:
    st.markdown("""
        <div style="margin-bottom: 40px; margin-top: 20px; padding: 0 20px;">
            <div style="display: flex; justify-content: flex-start;">
                <img src="https://www.fremec.com.ar/img/logo.svg" style="width: 100%; max-width: 250px;">
            </div>
            <div style="font-size: 13px; color: #a1a1aa; margin-top: 15px;">👤 Logueado: """ + nombre_activo + """</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.button("Cerrar Sesión", on_click=logout)
    st.markdown("---")
    
    # Menú Dinámico: Solo mostramos lo que tienen acceso para no generar vista con error feo a la derecha
    opciones = []
    if puede_bi: 
        opciones.append("BI")
    if es_admin: 
        opciones.append("Gestión")
    
    # Envasado se ve siempre para todos los logueados (ya sea para ver historial de planta o si tienen permiso, para cargar)
    opciones.append("Envasado")
    
    default_idx = opciones.index("Envasado") if "Envasado" in opciones else 0
    nav_selection = st.radio("Menú Principal", opciones, index=default_idx, label_visibility="collapsed")


# -----------------
# TOP BAR 
# -----------------
st.markdown("""
<div class="top-bar">
    <div>
        <span style="font-size: 20px; margin-right: 20px; color: #4b5563;">☰</span>
        <input type="text" class="search-input" placeholder="buscar...">
    </div>
</div>
""", unsafe_allow_html=True)


# ==========================================
# RUTAS DE APLICACIÓN
# ==========================================

# 1. GESTION (SÓLO ABM) - Bloqueo estricto por si acaso, aunque el boton lateral ya este oculto
# ------------------
if nav_selection == "Gestión":
    if not es_admin:
        st.error("🚫 Tu rol no te permite visualizar esto.")
        st.stop()
        
    st.title("Gestión (ABM Envasadores)")
    
    with st.expander("➕ Cargar Nuevo Usuario", expanded=False):
        with st.form("form_alta_usuario", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1: u_nombre = st.text_input("Nombre Completo")
            with col2: u_email = st.text_input("Correo Electrónico")
            with col3: u_pass = st.text_input("Contraseña", type="password")
            
            st.markdown("**Permisos de Acceso**")
            colp1, colp2, colp3, colp4 = st.columns(4)
            with colp1: p_abm = st.checkbox("ABM Envasadores")
            with colp2: p_bi = st.checkbox("Módulo BI (Dashboards)")
            with colp3: p_envasado = st.checkbox("Carga de Envasados")
            with colp4: p_nodb = st.checkbox("No mostrar en Dashboard", value=False)
                
            if st.form_submit_button("Guardar Usuario"):
                if u_nombre:
                    try:
                        data = {
                            "nombre": u_nombre, 
                            "email": u_email, 
                            "password": u_pass, 
                            "permiso_abm": p_abm, 
                            "permiso_bi": p_bi, 
                            "permiso_envasado": p_envasado,
                            "permisos_nodb": p_nodb
                        }
                        supabase.table("usuarios_envasadores").insert(data).execute()
                        registrar_auditoria(nombre_activo, "usuarios_envasadores", "ALTA", f"El admin creó al usuario: {u_nombre}.")
                        st.success("Usuario registrado.")
                    except Exception as e:
                        st.error(f"Error insertando: {e}")
    
    st.markdown("### Usuarios en la Nube (Administración Completa)")
    try:
        response = supabase.table("usuarios_envasadores").select("*").order("id").execute()
        if response.data:
            df_users = pd.DataFrame(response.data)
            
            # Asegurar la columna permisos_nodb de forma defensiva si no viene de BD
            if 'permisos_nodb' not in df_users.columns:
                df_users['permisos_nodb'] = False
            else:
                df_users['permisos_nodb'] = df_users['permisos_nodb'].fillna(False).astype(bool)
                
            display_df = df_users[['id', 'nombre', 'email', 'permiso_abm', 'permiso_bi', 'permiso_envasado', 'permisos_nodb']].copy()
            
            st.info("💡 **Tip de Edición:** Edita cualquier celda directamente. Para **BORRAR** un usuario, selecciona la fila tocando su casilla izquierda y oprime suprimir o el icono de tacho. Al finalizar, haz click en Guardar.")
            
            edited_df = st.data_editor(
                display_df, num_rows="dynamic", use_container_width=True, hide_index=True, key="abm_editor",
                column_config={
                    "id": None, 
                    "nombre": "Nombre", 
                    "email": "Correo", 
                    "permiso_abm": "Admin", 
                    "permiso_bi": "Analítica", 
                    "permiso_envasado": "Planta",
                    "permisos_nodb": "No mostrar en Dashboard"
                }
            )
            
            if st.button("💾 Guardar Cambios Editados de Tabla", type="primary"):
                cambios = False
                for row_idx in st.session_state["abm_editor"]["deleted_rows"]:
                    uid = int(display_df.iloc[row_idx]['id'])
                    uname = display_df.iloc[row_idx]['nombre']
                    supabase.table("usuarios_envasadores").delete().eq("id", uid).execute()
                    registrar_auditoria(nombre_activo, "usuarios_envasadores", "BAJA", f"Se eliminó permanentemente al usuario: {uname}.")
                    cambios = True
                        
                for row_idx, changed_data in st.session_state["abm_editor"]["edited_rows"].items():
                    uid = int(display_df.iloc[int(row_idx)]['id'])
                    uname = display_df.iloc[int(row_idx)]['nombre']
                    supabase.table("usuarios_envasadores").update(changed_data).eq("id", uid).execute()
                    registrar_auditoria(nombre_activo, "usuarios_envasadores", "MODIFICACION", f"Modificación al usuario {uname}. Detalle JSON: {json.dumps(changed_data)}")
                    cambios = True
                    
                for new_row in st.session_state["abm_editor"]["added_rows"]:
                    if "nombre" in new_row and new_row["nombre"]:
                        new_data = {
                            "nombre": new_row.get("nombre", ""),
                            "email": new_row.get("email", ""),
                            "password": "ClaveGenerica123", 
                            "permiso_abm": new_row.get("permiso_abm", False),
                            "permiso_bi": new_row.get("permiso_bi", False),
                            "permiso_envasado": new_row.get("permiso_envasado", False),
                            "permisos_nodb": new_row.get("permisos_nodb", False),
                        }
                        supabase.table("usuarios_envasadores").insert(new_data).execute()
                        cambios = True
                
                if cambios:
                    st.success("Los datos administrativos fueron sincronizados exitosamente.")
                    st.rerun()
    except Exception as e:
        st.error(f"Error cargando los datos administrativos: {e}")


# 2. ENVASADO DE PLANTA
# ------------------
elif nav_selection == "Envasado":
    st.title("Envasado Diario")
    
    if not puede_envasar:
        st.warning(f" Tu usuario ({nombre_activo}) sólo tiene permisos de contemplación. No puedes declarar producción a nombre de terceros ni el tuyo.")
    else:
        if "form_reset_counter" not in st.session_state:
            st.session_state["form_reset_counter"] = 0
            
        with st.expander("➕ Carga de Registro Personal", expanded=True):
            with st.form("form_alta_registro", clear_on_submit=False):
                col_f, col_c, col_e = st.columns(3)
                with col_f: r_fecha = st.date_input("Fecha", format="DD/MM/YYYY", key="r_fecha_input")
                
                cantidad_key = f"r_cantidad_{st.session_state['form_reset_counter']}"
                obs_key = f"r_obs_{st.session_state['form_reset_counter']}"
                
                with col_c: r_cantidad = st.number_input("Cantidad Producida", min_value=0, step=1, key=cantidad_key)
                
                with col_e: st.text_input("Envasador Responsable", value=nombre_activo, disabled=True)
                
                r_obs = st.text_area("Observaciones del turno", key=obs_key)
                
                submit_btn = st.form_submit_button("Guardar en Nube")
                
                if "mostrar_exito_guardado" in st.session_state and st.session_state["mostrar_exito_guardado"]:
                    st.success("Guardado ok.")
                    st.session_state["mostrar_exito_guardado"] = False
                    
                if submit_btn:
                    if not r_obs or str(r_obs).strip() == "":
                        st.error("No se ingresaron observaciones, por favor ingreselas para poder guardar")
                        st.components.v1.html("""
                            <script>
                                const doc = window.parent.document;
                                const alerts = doc.querySelectorAll('[data-testid="stAlert"]');
                                if(alerts.length > 0) {
                                    const lastAlert = alerts[alerts.length - 1];
                                    const hideAlert = () => { lastAlert.style.display = 'none'; };
                                    setTimeout(hideAlert, 3000);
                                    doc.addEventListener('mousemove', hideAlert, {once: true});
                                    doc.addEventListener('keydown', hideAlert, {once: true});
                                }
                            </script>
                        """, height=0)
                    elif r_cantidad > 0:
                        fecha_str = r_fecha.strftime("%d/%m/%Y")
                        data = {"nombre_envasador": nombre_activo, "fecha": fecha_str, "cantidad": r_cantidad, "observaciones": r_obs}
                        try:
                            supabase.table("registros_envasado").insert(data).execute()
                            registrar_auditoria(nombre_activo, "registros_envasado", "ALTA", f"Cargó {r_cantidad} unds producidas.")
                            
                            # Incrementamos el contador para generar nuevas keys y resetear los widgets
                            st.session_state["form_reset_counter"] += 1
                            st.session_state["mostrar_exito_guardado"] = True
                            st.rerun()
                        except Exception as e:
                             st.error(f"Error al subir: {e}")
                    else:
                        st.error("La cantidad debe ser mayor a cero.")

    st.markdown("### Historial de Registros")
    try:
        response = supabase.table("registros_envasado").select("*").order("id", desc=True).execute()
        if response.data:
            df_registros = pd.DataFrame(response.data)
            
            if es_admin:
                st.info("⚡ Tienes permisos de Administrador: Puedes auditar, modificar o borrar los registros históricos tocando en las celdas.")
                display_reg = df_registros[['id', 'fecha', 'cantidad', 'nombre_envasador', 'observaciones']].copy()
                
                edit_reg = st.data_editor(
                    display_reg, num_rows="dynamic", use_container_width=True, hide_index=True, key="reg_editor",
                    column_config={"id": None, "fecha": "Fecha", "cantidad": "Cantidad", "nombre_envasador": "Envasador Imputable", "observaciones": "Comentarios"}
                )
                
                if st.button("Aplicar Correcciones a la Nube (Administrador)"):
                    hubo_cambios = False
                    for r_idx in st.session_state["reg_editor"]["deleted_rows"]:
                        reg_id = int(display_reg.iloc[r_idx]['id'])
                        old_op = display_reg.iloc[r_idx]['nombre_envasador']
                        old_date = display_reg.iloc[r_idx]['fecha']
                        supabase.table("registros_envasado").delete().eq("id", reg_id).execute()
                        registrar_auditoria(nombre_activo, "registros_envasado", "BAJA_ADMINISTRATIVA", f"Eliminó el registro de producción de {old_op} del {old_date}")
                        hubo_cambios = True

                    for r_idx, c_data in st.session_state["reg_editor"]["edited_rows"].items():
                        reg_id = int(display_reg.iloc[int(r_idx)]['id'])
                        supabase.table("registros_envasado").update(c_data).eq("id", reg_id).execute()
                        registrar_auditoria(nombre_activo, "registros_envasado", "MODIFICACION_ADMINISTRATIVA", f"Alteró la producción con ID {reg_id}. Detalle: {json.dumps(c_data)}")
                        hubo_cambios = True
                    
                    if hubo_cambios:
                        st.success("Tus correcciones formales fueron guardadas y auditadas exitosamente.")
                        st.rerun()
            else:
                html_table = "<table class='custom-table'><tr><th>Fecha</th><th>Cantidad</th><th>Usuario</th><th>Observaciones</th></tr>"
                for index, row in df_registros.iterrows():
                    obs = row.get('observaciones', '') or "-"
                    html_table += f"<tr><td>{row['fecha']}</td><td>{row['cantidad']}</td><td>{row['nombre_envasador']}</td><td>{obs}</td></tr>"
                html_table += "</table>"
                st.markdown(html_table, unsafe_allow_html=True)
        else:
             st.info("La bitácora de envasados diaria está vacía.")
    except Exception as e:
         st.error(f"Fallo del servidor: {e}")


# 3. BI
# ------------------
elif nav_selection == "BI":
    st.title("Business Intelligence")
    
    try:
        # Obtener los usuarios que tienen marcado "No mostrar en Dashboard" (permisos_nodb = True)
        try:
            res_excluidos = supabase.table("usuarios_envasadores").select("nombre").eq("permisos_nodb", True).execute()
            nombres_excluidos = [u["nombre"] for u in res_excluidos.data] if res_excluidos.data else []
        except Exception as e:
            nombres_excluidos = []
            st.warning("⚠️ Nota: No se pudo verificar la exclusión de usuarios en el dashboard (¿Columna 'permisos_nodb' pendiente en la base de datos?)")
            
        # Descargar la BD entera y tratarla analíticamente en memoria
        response = supabase.table("registros_envasado").select("*").execute()
        if response.data:
            df_bi = pd.DataFrame(response.data)
            # Excluir registros de producción de los usuarios tildados
            if nombres_excluidos:
                df_bi = df_bi[~df_bi['nombre_envasador'].isin(nombres_excluidos)]
            
            # Formatear la fecha para extraer años, meses y días
            df_bi['fecha_dt'] = pd.to_datetime(df_bi['fecha'], format="%d/%m/%Y", errors='coerce')
            df_bi = df_bi.dropna(subset=['fecha_dt']) # Quitar ruteos imposibles por mal tipado manual
            df_bi['year'] = df_bi['fecha_dt'].dt.year.astype(int)
            df_bi['month'] = df_bi['fecha_dt'].dt.month.astype(int)
            df_bi['day'] = df_bi['fecha_dt'].dt.day.astype(int)
            
            st.markdown("### Filtros")
            col1, col2, col3 = st.columns([1, 1, 2])
            
            anio_actual = datetime.now().year
            mes_actual = datetime.now().month
            
            years_avail = sorted(df_bi['year'].unique().tolist())
            months_avail = sorted(df_bi['month'].unique().tolist())
            
            # Inserción de año actual si de pura casualidad nadie registró nada en este año, pero mantener el filtro
            if anio_actual not in years_avail: years_avail.append(anio_actual)
            if mes_actual not in months_avail: months_avail.append(mes_actual)
            years_avail.sort()
            months_avail.sort()
            
            # Formulario de filtros encajados
            with col1:
                sel_years = st.multiselect("Año", years_avail, default=[anio_actual], placeholder="Todos...")
            with col2:
                dicc_meses = {1:"enero", 2:"febrero", 3:"marzo", 4:"abril", 5:"mayo", 6:"junio", 7:"julio", 8:"agosto", 9:"septiembre", 10:"octubre", 11:"noviembre", 12:"diciembre"}
                rev_meses = {v:k for k,v in dicc_meses.items()}
                meses_nombres = [dicc_meses[m] for m in months_avail]
                sel_months_str = st.multiselect("Mes", meses_nombres, default=[dicc_meses[mes_actual]], placeholder="Todos...")
                sel_months = [rev_meses[m] for m in sel_months_str]
                
            envasadores_unicos = sorted(df_bi['nombre_envasador'].unique().tolist())
            with col3:
                sel_envasadores = st.multiselect("Envasador", envasadores_unicos, default=[], placeholder="Todos los envasadores...")
                
            # Intersección de cortes del Dataframe
            df_filtered = df_bi.copy()
            
            # Filtros ágiles: si el campo está vacío, significa "Todos"
            if sel_years:
                df_filtered = df_filtered[df_filtered['year'].isin(sel_years)]
            if sel_months:
                df_filtered = df_filtered[df_filtered['month'].isin(sel_months)]
            if sel_envasadores:
                df_filtered = df_filtered[df_filtered['nombre_envasador'].isin(sel_envasadores)]
                
            df_filtered = df_filtered.copy() # Evitar SettingWithCopyWarning
                
            if df_filtered.empty:
                st.warning("No hay registros de producción para los filtros seleccionados.")
            else:
                st.markdown("---")
                # 1. ARMADO DE LA TABLA PIVOT POR DIA EXACTA (Excel style)
                # Para evitar que Streamlit aplane visualmente 3 niveles (Año / Mes / Día), 
                # combinamos Año y Mes en un solo nivel de cabecera "Período" (Ej: "Mayo 2026")
                
                df_filtered['Mes_Str'] = df_filtered['month'].map(dicc_meses).str.capitalize()
                df_filtered['Período'] = df_filtered['Mes_Str'] + " " + df_filtered['year'].astype(str)
                
                # Forzamos orden cronológico creando un tipo categórico estructurado
                all_years_sorted = sorted(df_bi['year'].unique())
                periodos_ordenados = []
                for y in all_years_sorted:
                    for m in sorted(dicc_meses.keys()):
                        periodos_ordenados.append(f"{dicc_meses[m].capitalize()} {y}")
                        
                df_filtered['Período'] = pd.Categorical(df_filtered['Período'], categories=periodos_ordenados, ordered=True)
                
                # Remover categorías sin datos para que no aparezcan columnas vacías (Enero, Febrero, etc.)
                df_filtered['Período'] = df_filtered['Período'].cat.remove_unused_categories()
                
                # Renombrar columnas para el cruce
                df_filtered_renamed = df_filtered.rename(columns={'day': 'Día'})
                
                # Pivot de 2 niveles: Período -> Día. observed=True asegura que solo se pivoteen datos reales
                pivot = pd.pivot_table(df_filtered_renamed, values='cantidad', index='nombre_envasador', columns=['Período', 'Día'], aggfunc='sum', fill_value=0, observed=True)
                
                # Fila mágica de bottom "Total" cruzando los arrays de sumas
                pivot.loc['Total'] = pivot.sum()
                
                # Renombrar el índice para que se renderice como "Envasadores"
                pivot.index.name = "Envasadores"
                
                # Aplicamos formato de miles para la vista HTML
                if hasattr(pivot, 'map'):
                    pivot_fmt = pivot.map(lambda x: f"{x:,.0f}" if pd.notnull(x) and x != 0 else "0")
                else:
                    pivot_fmt = pivot.applymap(lambda x: f"{x:,.0f}" if pd.notnull(x) and x != 0 else "0")
                
                # Convertimos a HTML para inyectar CSS y lograr un diseño más Premium y personalizado
                html_table = pivot_fmt.to_html(classes="custom-table")
                
                custom_css = """
                <style>
                .table-container {
                    overflow-x: auto;
                    width: 100%;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    margin-bottom: 10px;
                    box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
                }
                .custom-table {
                    width: 100%;
                    border-collapse: collapse;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 13px;
                }
                /* Títulos superiores (Año, Mes, Día) */
                .custom-table thead th {
                    background-color: #004b99 !important; /* Azul oscuro corporativo similar al logo Fremec */
                    color: #ffffff !important; /* Letras blancas para contraste */
                    font-style: italic; /* Inclinadas */
                    font-weight: 600;
                    padding: 10px 8px;
                    border: 1px solid #003366;
                    text-align: center;
                    white-space: nowrap;
                }
                /* Columna lateral izquierda (Envasadores) */
                .custom-table tbody th {
                    background-color: #f8fafc !important;
                    color: #0f172a;
                    font-weight: 600;
                    padding: 8px 12px;
                    border: 1px solid #cbd5e1;
                    position: sticky;
                    left: 0;
                    z-index: 1;
                    text-align: left;
                    white-space: nowrap;
                }
                /* Intersección superior izquierda (Período / Día) */
                .custom-table thead th:first-child {
                    position: sticky;
                    left: 0;
                    z-index: 2;
                    background-color: #003366 !important; /* Azul más oscuro para diferenciar la esquina superior izquierda */
                }
                .custom-table tbody td {
                    padding: 8px 10px;
                    border: 1px solid #e2e8f0;
                    text-align: right;
                    background-color: #ffffff;
                    color: #334155;
                    min-width: 45px;
                }
                .custom-table tbody tr:hover td {
                    background-color: #f1f5f9;
                }
                /* Fix para forzar color oscuro y contraste en los radio buttons */
                div[role="radiogroup"] label p {
                    color: #0f172a !important;
                    font-weight: 600 !important;
                }
                </style>
                """
                
                # Eliminamos la indentación (espacios al inicio) para que Markdown no lo tome como un bloque de código (code block)
                html_str = custom_css + f'<div class="table-container">\n{html_table}\n</div>'
                html_str_clean = "\n".join([line.lstrip() for line in html_str.split("\n")])
                
                st.markdown(html_str_clean, unsafe_allow_html=True)
                
                # Agregamos un botón de descarga para no perder la exportación a Excel/CSV
                csv_data = pivot.to_csv().encode('utf-8')
                st.download_button(
                    label="📥 Descargar Grilla en CSV",
                    data=csv_data,
                    file_name="grilla_produccion.csv",
                    mime="text/csv",
                )
                
                # 2. SECCIÓN DE GRÁFICOS
                st.markdown("---")
                
                # Controles de los gráficos
                agg_level = st.radio(
                    "📊 Agrupar gráficos por:",
                    options=["Día", "Mes", "Año"],
                    horizontal=True
                )
                
                # Preparar la columna de agrupación de tiempo (como texto para que Plotly no estire las barras)
                # Ordenamos cronológicamente antes de convertir a texto para que Plotly respete el orden visual
                df_filtered = df_filtered.sort_values('fecha_dt')
                
                if agg_level == "Día":
                    group_col = 'fecha_str'
                    df_filtered['fecha_str'] = df_filtered['fecha_dt'].dt.strftime("%d/%m/%Y")
                    x_title = "Fecha"
                elif agg_level == "Mes":
                    group_col = 'mes_str'
                    df_filtered['mes_str'] = df_filtered['fecha_dt'].dt.strftime("%m/%Y")
                    x_title = "Mes"
                else: # Año
                    group_col = 'año_str'
                    df_filtered['año_str'] = df_filtered['fecha_dt'].dt.strftime("%Y")
                    x_title = "Año"
                
                st.markdown(f"#### Producción Total de la Empresa (Por {agg_level})")
                # Gráfico 1: Total Empresa
                # Al hacer groupby, sort=False asegura que Pandas mantenga el orden cronológico que forzamos arriba
                company_sum = df_filtered.groupby(group_col, sort=False)['cantidad'].sum().reset_index()
                
                fig1 = px.bar(company_sum, x=group_col, y='cantidad')
                fig1.update_layout(
                    xaxis_title=x_title,
                    yaxis_title="Cantidad Total",
                    xaxis=dict(type='category'), # Forzar eje categórico para evitar el estiramiento de barras de fechas
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=20, r=20, t=30, b=20)
                )
                fig1.update_traces(marker_color='#2196F3') # Azul corporativo
                st.plotly_chart(fig1, use_container_width=True)
                
                st.markdown(f"#### Comparativa por Envasador (Por {agg_level})")
                # Gráfico 2: Comparativa Envasadores
                env_sum = df_filtered.groupby([group_col, 'nombre_envasador'], sort=False)['cantidad'].sum().reset_index()
                
                # Calculamos el total global por envasador para ordenarlos de mayor a menor
                # de izquierda a derecha en las barras y en la leyenda
                ranking_envasadores = env_sum.groupby('nombre_envasador')['cantidad'].sum().sort_values(ascending=False).index.tolist()
                
                fig2 = px.bar(env_sum, x=group_col, y='cantidad', color='nombre_envasador', barmode='group', category_orders={'nombre_envasador': ranking_envasadores})
                fig2.update_layout(
                    xaxis_title=x_title,
                    yaxis_title="Cantidad Producida",
                    xaxis=dict(type='category'), # Forzar eje categórico
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=20, r=20, t=30, b=20),
                    legend_title_text='Envasadores',
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1) # Leyenda horizontal arriba para más limpieza
                )
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("La plataforma no posee datos matemáticos suficientes aún para nutrir el modelo BI.")
    except Exception as e:
        st.error(f"Hubo un quiebre numérico descargando a Pandas en RAM: {e}")
