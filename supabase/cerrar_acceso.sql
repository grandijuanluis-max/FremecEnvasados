-- Cierra el acceso directo a las tablas del portal Fremec.
-- Ejecutar una sola vez en Supabase → SQL Editor → Run.
-- Después, en Streamlit, SUPABASE_KEY tiene que ser la clave anon (public),
-- no la service_role.

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;

ALTER TABLE usuarios_envasadores
    ADD COLUMN IF NOT EXISTS permisos_nodb boolean DEFAULT false;

CREATE TABLE IF NOT EXISTS sesiones (
    id bigserial PRIMARY KEY,
    usuario_id bigint NOT NULL,
    token_hash text NOT NULL UNIQUE,
    vence timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS intentos_ingreso (
    id bigserial PRIMARY KEY,
    momento timestamptz NOT NULL DEFAULT now(),
    usuario_intentado text,
    ip text,
    user_agent text,
    exito boolean NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS intentos_ingreso_ip_momento_idx
    ON intentos_ingreso (ip, momento DESC);

UPDATE usuarios_envasadores
SET password = extensions.crypt(password, extensions.gen_salt('bf', 10))
WHERE password IS NOT NULL
  AND password <> ''
  AND password NOT LIKE '$2%';

ALTER TABLE usuarios_envasadores ENABLE ROW LEVEL SECURITY;
ALTER TABLE registros_envasado ENABLE ROW LEVEL SECURITY;
ALTER TABLE auditoria ENABLE ROW LEVEL SECURITY;
ALTER TABLE sesiones ENABLE ROW LEVEL SECURITY;
ALTER TABLE intentos_ingreso ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE usuarios_envasadores FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE registros_envasado FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE auditoria FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE sesiones FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE intentos_ingreso FROM PUBLIC, anon, authenticated;

REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION fremec_usuario_id(p_token text)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_id bigint;
BEGIN
    IF p_token IS NULL OR length(p_token) < 20 THEN
        RETURN NULL;
    END IF;
    SELECT s.usuario_id INTO v_id
    FROM sesiones s
    WHERE s.token_hash = encode(digest(p_token, 'sha256'), 'hex')
      AND s.vence > now();
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION fremec_iniciar_sesion(p_usuario text, p_clave text)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_user usuarios_envasadores%ROWTYPE;
    v_ok boolean := false;
    v_token text;
BEGIN
    SELECT * INTO v_user
    FROM usuarios_envasadores
    WHERE nombre = p_usuario OR email = p_usuario
    ORDER BY id
    LIMIT 1;

    IF NOT FOUND OR p_clave IS NULL OR p_clave = '' THEN
        RETURN json_build_object('ok', false);
    END IF;

    IF v_user.password LIKE '$2%' AND v_user.password = crypt(p_clave, v_user.password) THEN
        v_ok := true;
    ELSIF v_user.password NOT LIKE '$2%' AND v_user.password = p_clave THEN
        UPDATE usuarios_envasadores
        SET password = crypt(p_clave, gen_salt('bf', 10))
        WHERE id = v_user.id;
        v_ok := true;
    END IF;

    IF NOT v_ok THEN
        RETURN json_build_object('ok', false);
    END IF;

    DELETE FROM sesiones WHERE vence < now();
    v_token := encode(gen_random_bytes(32), 'hex');
    INSERT INTO sesiones (usuario_id, token_hash, vence)
    VALUES (v_user.id, encode(digest(v_token, 'sha256'), 'hex'), now() + interval '16 hours');

    RETURN json_build_object(
        'ok', true,
        'token', v_token,
        'usuario', json_build_object(
            'id', v_user.id,
            'nombre', v_user.nombre,
            'email', v_user.email,
            'permiso_abm', COALESCE(v_user.permiso_abm, false),
            'permiso_bi', COALESCE(v_user.permiso_bi, false),
            'permiso_envasado', COALESCE(v_user.permiso_envasado, false),
            'permisos_nodb', COALESCE(v_user.permisos_nodb, false)
        )
    );
END;
$$;

CREATE OR REPLACE FUNCTION fremec_cerrar_sesion(p_token text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
BEGIN
    DELETE FROM sesiones
    WHERE token_hash = encode(digest(COALESCE(p_token, ''), 'sha256'), 'hex');
END;
$$;

CREATE OR REPLACE FUNCTION fremec_yo(p_token text)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_id bigint;
    v_user usuarios_envasadores%ROWTYPE;
BEGIN
    v_id := fremec_usuario_id(p_token);
    IF v_id IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT * INTO v_user FROM usuarios_envasadores WHERE id = v_id;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    RETURN json_build_object(
        'id', v_user.id,
        'nombre', v_user.nombre,
        'email', v_user.email,
        'permiso_abm', COALESCE(v_user.permiso_abm, false),
        'permiso_bi', COALESCE(v_user.permiso_bi, false),
        'permiso_envasado', COALESCE(v_user.permiso_envasado, false),
        'permisos_nodb', COALESCE(v_user.permisos_nodb, false)
    );
END;
$$;

CREATE OR REPLACE FUNCTION fremec_registrar_intento(
    p_usuario text,
    p_ip text,
    p_agente text,
    p_exito boolean
)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_previos integer;
BEGIN
    SELECT count(*) INTO v_previos
    FROM intentos_ingreso
    WHERE ip = left(COALESCE(p_ip, ''), 80)
      AND momento > now() - interval '15 minutes';

    INSERT INTO intentos_ingreso (usuario_intentado, ip, user_agent, exito)
    VALUES (
        left(COALESCE(p_usuario, ''), 200),
        left(COALESCE(p_ip, ''), 80),
        left(COALESCE(p_agente, ''), 400),
        COALESCE(p_exito, false)
    );

    RETURN json_build_object('avisar', v_previos < 8);
END;
$$;

CREATE OR REPLACE FUNCTION fremec_auditar(
    p_token text,
    p_tabla text,
    p_accion text,
    p_detalle text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_id bigint;
    v_nombre text;
BEGIN
    v_id := fremec_usuario_id(p_token);
    IF v_id IS NULL THEN
        RAISE EXCEPTION 'No autorizado';
    END IF;
    SELECT nombre INTO v_nombre FROM usuarios_envasadores WHERE id = v_id;
    INSERT INTO auditoria (usuario_accion, tabla_afectada, accion_realizada, detalles)
    VALUES (v_nombre, left(COALESCE(p_tabla, ''), 80), left(COALESCE(p_accion, ''), 80), left(COALESCE(p_detalle, ''), 2000));
END;
$$;

CREATE OR REPLACE FUNCTION fremec_listar_usuarios(p_token text)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_id bigint;
BEGIN
    v_id := fremec_usuario_id(p_token);
    IF v_id IS NULL OR NOT COALESCE((SELECT permiso_abm FROM usuarios_envasadores WHERE id = v_id), false) THEN
        RAISE EXCEPTION 'No autorizado';
    END IF;
    RETURN COALESCE((
        SELECT json_agg(fila ORDER BY fila.id)
        FROM (
            SELECT id, nombre, email,
                   COALESCE(permiso_abm, false) AS permiso_abm,
                   COALESCE(permiso_bi, false) AS permiso_bi,
                   COALESCE(permiso_envasado, false) AS permiso_envasado,
                   COALESCE(permisos_nodb, false) AS permisos_nodb
            FROM usuarios_envasadores
        ) fila
    ), '[]'::json);
END;
$$;

CREATE OR REPLACE FUNCTION fremec_crear_usuario(p_token text, p_datos json)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_id bigint;
    v_nombre text;
BEGIN
    v_id := fremec_usuario_id(p_token);
    IF v_id IS NULL OR NOT COALESCE((SELECT permiso_abm FROM usuarios_envasadores WHERE id = v_id), false) THEN
        RAISE EXCEPTION 'No autorizado';
    END IF;
    v_nombre := btrim(COALESCE(p_datos->>'nombre', ''));
    IF v_nombre = '' THEN
        RAISE EXCEPTION 'Falta el nombre';
    END IF;
    INSERT INTO usuarios_envasadores (
        nombre, email, password, permiso_abm, permiso_bi, permiso_envasado, permisos_nodb
    ) VALUES (
        v_nombre,
        NULLIF(btrim(COALESCE(p_datos->>'email', '')), ''),
        crypt(COALESCE(p_datos->>'password', ''), gen_salt('bf', 10)),
        COALESCE((p_datos->>'permiso_abm')::boolean, false),
        COALESCE((p_datos->>'permiso_bi')::boolean, false),
        COALESCE((p_datos->>'permiso_envasado')::boolean, false),
        COALESCE((p_datos->>'permisos_nodb')::boolean, false)
    );
END;
$$;

CREATE OR REPLACE FUNCTION fremec_actualizar_usuario(p_token text, p_id bigint, p_datos json)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_id bigint;
BEGIN
    v_id := fremec_usuario_id(p_token);
    IF v_id IS NULL OR NOT COALESCE((SELECT permiso_abm FROM usuarios_envasadores WHERE id = v_id), false) THEN
        RAISE EXCEPTION 'No autorizado';
    END IF;
    UPDATE usuarios_envasadores
    SET nombre = CASE WHEN (p_datos::jsonb) ? 'nombre' THEN NULLIF(btrim(p_datos->>'nombre'), '') ELSE nombre END,
        email = CASE WHEN (p_datos::jsonb) ? 'email' THEN NULLIF(btrim(p_datos->>'email'), '') ELSE email END,
        permiso_abm = CASE WHEN (p_datos::jsonb) ? 'permiso_abm' THEN COALESCE((p_datos->>'permiso_abm')::boolean, false) ELSE permiso_abm END,
        permiso_bi = CASE WHEN (p_datos::jsonb) ? 'permiso_bi' THEN COALESCE((p_datos->>'permiso_bi')::boolean, false) ELSE permiso_bi END,
        permiso_envasado = CASE WHEN (p_datos::jsonb) ? 'permiso_envasado' THEN COALESCE((p_datos->>'permiso_envasado')::boolean, false) ELSE permiso_envasado END,
        permisos_nodb = CASE WHEN (p_datos::jsonb) ? 'permisos_nodb' THEN COALESCE((p_datos->>'permisos_nodb')::boolean, false) ELSE permisos_nodb END
    WHERE id = p_id;
END;
$$;

CREATE OR REPLACE FUNCTION fremec_eliminar_usuario(p_token text, p_id bigint)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_id bigint;
BEGIN
    v_id := fremec_usuario_id(p_token);
    IF v_id IS NULL OR NOT COALESCE((SELECT permiso_abm FROM usuarios_envasadores WHERE id = v_id), false) THEN
        RAISE EXCEPTION 'No autorizado';
    END IF;
    IF p_id = v_id THEN
        RAISE EXCEPTION 'No podés eliminar tu propio usuario';
    END IF;
    DELETE FROM sesiones WHERE usuario_id = p_id;
    DELETE FROM usuarios_envasadores WHERE id = p_id;
END;
$$;

CREATE OR REPLACE FUNCTION fremec_nombres_excluidos(p_token text)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_id bigint;
BEGIN
    v_id := fremec_usuario_id(p_token);
    IF v_id IS NULL OR NOT COALESCE((SELECT permiso_bi FROM usuarios_envasadores WHERE id = v_id), false) THEN
        RAISE EXCEPTION 'No autorizado';
    END IF;
    RETURN COALESCE((
        SELECT json_agg(nombre)
        FROM usuarios_envasadores
        WHERE COALESCE(permisos_nodb, false)
    ), '[]'::json);
END;
$$;

CREATE OR REPLACE FUNCTION fremec_listar_registros(p_token text)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_id bigint;
BEGIN
    v_id := fremec_usuario_id(p_token);
    IF v_id IS NULL THEN
        RAISE EXCEPTION 'No autorizado';
    END IF;
    RETURN COALESCE((
        SELECT json_agg(fila ORDER BY fila.id DESC)
        FROM (
            SELECT id, fecha, cantidad, nombre_envasador, observaciones
            FROM registros_envasado
        ) fila
    ), '[]'::json);
END;
$$;

CREATE OR REPLACE FUNCTION fremec_crear_registro(p_token text, p_datos json)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_id bigint;
    v_nombre text;
    v_puede boolean;
BEGIN
    v_id := fremec_usuario_id(p_token);
    IF v_id IS NULL THEN
        RAISE EXCEPTION 'No autorizado';
    END IF;
    SELECT nombre, COALESCE(permiso_envasado, false)
      INTO v_nombre, v_puede
    FROM usuarios_envasadores
    WHERE id = v_id;
    IF NOT v_puede THEN
        RAISE EXCEPTION 'No autorizado';
    END IF;
    INSERT INTO registros_envasado (nombre_envasador, fecha, cantidad, observaciones)
    VALUES (
        v_nombre,
        left(COALESCE(p_datos->>'fecha', ''), 20),
        COALESCE((p_datos->>'cantidad')::numeric, 0),
        left(COALESCE(p_datos->>'observaciones', ''), 2000)
    );
END;
$$;

CREATE OR REPLACE FUNCTION fremec_actualizar_registro(p_token text, p_id bigint, p_datos json)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_id bigint;
BEGIN
    v_id := fremec_usuario_id(p_token);
    IF v_id IS NULL OR NOT COALESCE((SELECT permiso_abm FROM usuarios_envasadores WHERE id = v_id), false) THEN
        RAISE EXCEPTION 'No autorizado';
    END IF;
    UPDATE registros_envasado
    SET fecha = CASE WHEN (p_datos::jsonb) ? 'fecha' THEN left(COALESCE(p_datos->>'fecha', ''), 20) ELSE fecha END,
        cantidad = CASE WHEN (p_datos::jsonb) ? 'cantidad' THEN COALESCE((p_datos->>'cantidad')::numeric, 0) ELSE cantidad END,
        nombre_envasador = CASE WHEN (p_datos::jsonb) ? 'nombre_envasador' THEN left(COALESCE(p_datos->>'nombre_envasador', ''), 200) ELSE nombre_envasador END,
        observaciones = CASE WHEN (p_datos::jsonb) ? 'observaciones' THEN left(COALESCE(p_datos->>'observaciones', ''), 2000) ELSE observaciones END
    WHERE id = p_id;
END;
$$;

CREATE OR REPLACE FUNCTION fremec_eliminar_registro(p_token text, p_id bigint)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    v_id bigint;
BEGIN
    v_id := fremec_usuario_id(p_token);
    IF v_id IS NULL OR NOT COALESCE((SELECT permiso_abm FROM usuarios_envasadores WHERE id = v_id), false) THEN
        RAISE EXCEPTION 'No autorizado';
    END IF;
    DELETE FROM registros_envasado WHERE id = p_id;
END;
$$;

REVOKE ALL ON FUNCTION fremec_usuario_id(text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION fremec_iniciar_sesion(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION fremec_cerrar_sesion(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION fremec_yo(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION fremec_registrar_intento(text, text, text, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION fremec_auditar(text, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION fremec_listar_usuarios(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION fremec_crear_usuario(text, json) FROM PUBLIC;
REVOKE ALL ON FUNCTION fremec_actualizar_usuario(text, bigint, json) FROM PUBLIC;
REVOKE ALL ON FUNCTION fremec_eliminar_usuario(text, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION fremec_nombres_excluidos(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION fremec_listar_registros(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION fremec_crear_registro(text, json) FROM PUBLIC;
REVOKE ALL ON FUNCTION fremec_actualizar_registro(text, bigint, json) FROM PUBLIC;
REVOKE ALL ON FUNCTION fremec_eliminar_registro(text, bigint) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION fremec_iniciar_sesion(text, text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION fremec_cerrar_sesion(text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION fremec_yo(text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION fremec_registrar_intento(text, text, text, boolean) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION fremec_auditar(text, text, text, text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION fremec_listar_usuarios(text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION fremec_crear_usuario(text, json) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION fremec_actualizar_usuario(text, bigint, json) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION fremec_eliminar_usuario(text, bigint) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION fremec_nombres_excluidos(text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION fremec_listar_registros(text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION fremec_crear_registro(text, json) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION fremec_actualizar_registro(text, bigint, json) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION fremec_eliminar_registro(text, bigint) TO anon, authenticated;

NOTIFY pgrst, 'reload schema';
