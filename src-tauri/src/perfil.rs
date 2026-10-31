//! Tu música (F2.2.8): lo que el historial local dice del usuario, con las
//! secciones de la V1 (`VistaPerfil.qml`): identidad, actividad, el ánimo del día,
//! los días activos del mes y los tops.
//!
//! Todo sale de `historial`, que la V2 trajo entero de la V1. Las horas y los días
//! se cuentan en la hora local del equipo (`'localtime'` de SQLite): la V1 los
//! guardaba en UTC, y la hora pico de alguien en Colombia no son las 23:00.

use std::f64::consts::PI;
use std::path::Path;

use rusqlite::types::Value;
use serde::Serialize;
use ts_rs::TS;

use crate::biblioteca::{self, AlbumResumen, ArtistaResumen};
use crate::db::BaseDeDatos;
use crate::error::{NsError, NsResult};
use crate::inicio::PistaEscuchada;

/// Los seis ejes del radar de ánimos del resumen de escucha (F8.3), de 0 a 1.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct RadarAnimos {
    pub energia: f64,
    pub bailable: f64,
    pub alegre: f64,
    pub calma: f64,
    pub nocturna: f64,
    pub melancolica: f64,
}

/// Resumen local de escucha (F8.3) para un mes (`YYYY-MM`), un año (`YYYY`) o `"todo"`.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct ResumenEscucha {
    pub periodo: String,
    pub periodos_disponibles: Vec<String>,
    pub reproducciones: u32,
    pub pistas_distintas: u32,
    pub artistas_distintos: u32,
    pub albumes_distintos: u32,
    pub segundos_escuchados: f64,
    pub radar: RadarAnimos,
    /// 7 días (0 = lunes .. 6 = domingo) × 24 horas (0..24) = 168 celdas en hora local.
    pub mapa_calor: Vec<u32>,
    pub top_canciones: Vec<PistaEscuchada>,
    pub top_albumes: Vec<AlbumResumen>,
    pub top_artistas: Vec<ArtistaResumen>,
}

#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct ArtistaDelDia {
    #[ts(type = "number")]
    pub id: i64,
    pub nombre: String,
    pub escuchas: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "../../src/lib/bindings/")]
#[serde(rename_all = "camelCase")]
pub struct Perfil {
    pub reproducciones: u32,
    pub pistas_distintas: u32,
    pub pistas_en_biblioteca: u32,
    pub artistas_distintos: u32,
    pub albumes_distintos: u32,
    pub segundos_escuchados: f64,
    #[ts(type = "number | null")]
    pub anio_favorito: Option<i64>,
    /// De 0 a 23, en la hora local.
    pub hora_pico: Option<u32>,
    /// Escuchas de hoy y sus artistas, de más a menos.
    pub escuchas_hoy: u32,
    pub artistas_hoy: Vec<ArtistaDelDia>,
    /// Escuchas de cada día del mes en curso: el índice 0 es el día 1.
    pub dias_del_mes: Vec<u32>,
    pub top_canciones: Vec<PistaEscuchada>,
    pub top_albumes: Vec<AlbumResumen>,
    pub top_artistas: Vec<ArtistaResumen>,
}

fn uno<T: rusqlite::types::FromSql>(conn: &rusqlite::Connection, sql: &str) -> NsResult<T> {
    conn.query_row(sql, [], |f| f.get(0))
        .map_err(|_| NsError::StorageFailure)
}

fn pares(conn: &rusqlite::Connection, sql: &str) -> NsResult<Vec<(i64, i64)>> {
    pares_con_params(conn, sql, &[])
}

fn pares_con_params(
    conn: &rusqlite::Connection,
    sql: &str,
    params: &[Value],
) -> NsResult<Vec<(i64, i64)>> {
    let mut s = conn.prepare(sql).map_err(|_| NsError::StorageFailure)?;
    let filas = s
        .query_map(rusqlite::params_from_iter(params.iter()), |f| {
            Ok((f.get(0)?, f.get(1)?))
        })
        .map_err(|_| NsError::StorageFailure)?
        .collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|_| NsError::StorageFailure)?;
    Ok(filas)
}

fn uno_con_params<T: rusqlite::types::FromSql>(
    conn: &rusqlite::Connection,
    sql: &str,
    params: &[Value],
) -> NsResult<T> {
    conn.query_row(sql, rusqlite::params_from_iter(params.iter()), |f| f.get(0))
        .map_err(|_| NsError::StorageFailure)
}

fn normalizar_periodo(periodo: Option<&str>) -> NsResult<(&'static str, String, Vec<Value>)> {
    let p = periodo.map(str::trim).unwrap_or("todo");
    if p.is_empty() || p == "todo" {
        return Ok(("1 = 1", "todo".to_owned(), Vec::new()));
    }
    if p.len() == 4 && p.bytes().all(|b| b.is_ascii_digit()) {
        return Ok((
            "strftime('%Y', h.reproducida_en, 'localtime') = ?1",
            p.to_owned(),
            vec![Value::Text(p.to_owned())],
        ));
    }
    if p.len() == 7
        && p.as_bytes()[4] == b'-'
        && p[..4].bytes().all(|b| b.is_ascii_digit())
        && p[5..].bytes().all(|b| b.is_ascii_digit())
    {
        let mes: u32 = p[5..].parse().unwrap_or(0);
        if (1..=12).contains(&mes) {
            return Ok((
                "strftime('%Y-%m', h.reproducida_en, 'localtime') = ?1",
                p.to_owned(),
                vec![Value::Text(p.to_owned())],
            ));
        }
    }
    Err(NsError::InvalidInput)
}

fn periodos_en_historial(conn: &rusqlite::Connection) -> NsResult<Vec<String>> {
    let mut lista = vec!["todo".to_owned()];
    for sql in [
        "SELECT DISTINCT strftime('%Y', reproducida_en, 'localtime') AS p
         FROM historial WHERE reproducida_en IS NOT NULL ORDER BY p DESC LIMIT 20",
        "SELECT DISTINCT strftime('%Y-%m', reproducida_en, 'localtime') AS p
         FROM historial WHERE reproducida_en IS NOT NULL ORDER BY p DESC LIMIT 36",
    ] {
        let mut s = conn.prepare(sql).map_err(|_| NsError::StorageFailure)?;
        let filas = s
            .query_map([], |f| f.get::<_, Option<String>>(0))
            .map_err(|_| NsError::StorageFailure)?
            .collect::<rusqlite::Result<Vec<_>>>()
            .map_err(|_| NsError::StorageFailure)?;
        for p in filas.into_iter().flatten() {
            if !p.is_empty() && !lista.contains(&p) {
                lista.push(p);
            }
        }
    }
    Ok(lista)
}

/// Calcula el resumen local de escucha (F8.3) para un mes (`YYYY-MM`), un año (`YYYY`) o `"todo"`.
///
/// # Errors
///
/// [`NsError::InvalidInput`] si `periodo` no tiene formato válido;
/// [`NsError::StorageFailure`] si alguna consulta falla.
pub fn resumen_escucha(db: &BaseDeDatos, periodo: Option<&str>) -> NsResult<ResumenEscucha> {
    let (cond, periodo_norm, params) = normalizar_periodo(periodo)?;
    let conn = db.conexion()?;
    let periodos_disponibles = periodos_en_historial(&conn)?;

    let reproducciones: i64 = uno_con_params(
        &conn,
        &format!("SELECT count(*) FROM historial h WHERE {cond}"),
        &params,
    )?;
    let pistas_distintas: i64 = uno_con_params(
        &conn,
        &format!("SELECT count(DISTINCT h.pista_id) FROM historial h WHERE {cond}"),
        &params,
    )?;
    let artistas_distintos: i64 = uno_con_params(
        &conn,
        &format!(
            "SELECT count(DISTINCT p.artista_id) FROM historial h
             JOIN pistas p ON p.id = h.pista_id WHERE {cond}"
        ),
        &params,
    )?;
    let albumes_distintos: i64 = uno_con_params(
        &conn,
        &format!(
            "SELECT count(DISTINCT p.album_id) FROM historial h
             JOIN pistas p ON p.id = h.pista_id WHERE {cond}"
        ),
        &params,
    )?;
    let segundos_escuchados: f64 = uno_con_params(
        &conn,
        &format!(
            "SELECT total(coalesce(h.escuchado_seg, p.duracion_seg, 0))
             FROM historial h LEFT JOIN pistas p ON p.id = h.pista_id WHERE {cond}"
        ),
        &params,
    )?;

    let radar = {
        let sql = format!(
            "SELECT
                avg(coalesce(CASE WHEN ap.version = '{}' THEN (coalesce(r.energia, 0.0) * 0.7 + coalesce(ap.activacion, r.energia, 0.0) * 0.3) END, r.energia, 0.0)),
                avg(coalesce(CASE WHEN ap.bailable IS NOT NULL THEN (coalesce(r.bailabilidad, 0.0) * 0.6 + ap.bailable * 0.4) END, r.bailabilidad, 0.0)),
                avg(coalesce(CASE WHEN ap.feliz IS NOT NULL THEN (coalesce(r.valencia, 0.0) * 0.65 + ap.feliz * 0.35) END, r.valencia, 0.0)),
                avg(coalesce(CASE WHEN ap.relajada IS NOT NULL THEN (coalesce(r.calma, 0.0) * 0.65 + ap.relajada * 0.35) END, r.calma, 0.0)),
                avg(coalesce(r.para_la_noche, 0.0) * 0.6 + coalesce(r.oscuridad, 0.0) * 0.4),
                avg(coalesce(CASE WHEN ap.triste IS NOT NULL THEN (coalesce(r.melancolia, 0.0) * 0.65 + ap.triste * 0.35) END, r.melancolia, 0.0))
             FROM historial h
             JOIN rasgos r ON r.pista_id = h.pista_id
             LEFT JOIN analisis_profundo ap ON ap.pista_id = h.pista_id
             WHERE (r.bpm IS NOT NULL OR r.energia IS NOT NULL) AND ({cond})",
            crate::analisis::VERSION
        );
        let c01 = |v: Option<f64>| v.unwrap_or(0.0).clamp(0.0, 1.0);
        conn.query_row(&sql, rusqlite::params_from_iter(params.iter()), |f| {
            Ok(RadarAnimos {
                energia: c01(f.get(0)?),
                bailable: c01(f.get(1)?),
                alegre: c01(f.get(2)?),
                calma: c01(f.get(3)?),
                nocturna: c01(f.get(4)?),
                melancolica: c01(f.get(5)?),
            })
        })
        .map_err(|_| NsError::StorageFailure)?
    };

    let mut mapa_calor = vec![0u32; 168];
    {
        let sql = format!(
            "SELECT (CAST(strftime('%w', h.reproducida_en, 'localtime') AS INTEGER) + 6) % 7 AS dia,
                    CAST(strftime('%H', h.reproducida_en, 'localtime') AS INTEGER) AS hora,
                    count(*) AS n
             FROM historial h
             WHERE h.reproducida_en IS NOT NULL AND ({cond})
             GROUP BY dia, hora"
        );
        let mut s = conn.prepare(&sql).map_err(|_| NsError::StorageFailure)?;
        let celdas = s
            .query_map(rusqlite::params_from_iter(params.iter()), |f| {
                Ok((
                    f.get::<_, Option<i64>>(0)?,
                    f.get::<_, Option<i64>>(1)?,
                    f.get::<_, i64>(2)?,
                ))
            })
            .map_err(|_| NsError::StorageFailure)?
            .collect::<rusqlite::Result<Vec<_>>>()
            .map_err(|_| NsError::StorageFailure)?;
        for (dia, hora, n) in celdas {
            if let (Some(d), Some(h)) = (dia, hora) {
                if (0..7).contains(&d) && (0..24).contains(&h) {
                    mapa_calor[(d * 24 + h) as usize] = n.max(0) as u32;
                }
            }
        }
    }

    let canciones = pares_con_params(
        &conn,
        &format!(
            "SELECT h.pista_id, count(*) AS n FROM historial h
             JOIN pistas p ON p.id = h.pista_id
             WHERE p.estado = 'biblioteca' AND ({cond})
             GROUP BY h.pista_id ORDER BY n DESC, h.pista_id LIMIT 5"
        ),
        &params,
    )?;
    let albumes = pares_con_params(
        &conn,
        &format!(
            "SELECT p.album_id, count(*) AS n FROM historial h
             JOIN pistas p ON p.id = h.pista_id
             WHERE p.album_id IS NOT NULL AND ({cond})
             GROUP BY p.album_id ORDER BY n DESC, p.album_id LIMIT 5"
        ),
        &params,
    )?;
    let artistas = pares_con_params(
        &conn,
        &format!(
            "SELECT p.artista_id, count(*) AS n FROM historial h
             JOIN pistas p ON p.id = h.pista_id
             WHERE p.artista_id IS NOT NULL AND ({cond})
             GROUP BY p.artista_id ORDER BY n DESC, p.artista_id LIMIT 5"
        ),
        &params,
    )?;
    drop(conn);

    let ids: Vec<i64> = canciones.iter().map(|f| f.0).collect();
    let top_canciones = biblioteca::resumenes(db, &ids)?
        .into_iter()
        .map(|pista| {
            let n = canciones
                .iter()
                .find(|f| f.0 == pista.id)
                .map_or(0, |f| f.1);
            PistaEscuchada {
                pista,
                reproducciones: n as u32,
            }
        })
        .collect();
    let top_albumes = albumes
        .iter()
        .filter_map(|(id, _)| biblioteca::album(db, *id).transpose())
        .collect::<NsResult<Vec<_>>>()?;
    let top_artistas = artistas
        .iter()
        .filter_map(|(id, _)| biblioteca::artista(db, *id).transpose())
        .collect::<NsResult<Vec<_>>>()?;

    Ok(ResumenEscucha {
        periodo: periodo_norm,
        periodos_disponibles,
        reproducciones: reproducciones as u32,
        pistas_distintas: pistas_distintas as u32,
        artistas_distintos: artistas_distintos as u32,
        albumes_distintos: albumes_distintos as u32,
        segundos_escuchados,
        radar,
        mapa_calor,
        top_canciones,
        top_albumes,
        top_artistas,
    })
}

fn escapar_xml(texto: &str) -> String {
    let mut s = String::with_capacity(texto.len());
    for c in texto.chars() {
        match c {
            '&' => s.push_str("&amp;"),
            '<' => s.push_str("&lt;"),
            '>' => s.push_str("&gt;"),
            '"' => s.push_str("&quot;"),
            '\'' => s.push_str("&apos;"),
            _ => s.push(c),
        }
    }
    s
}

fn truncar_texto(texto: &str, max_chars: usize) -> String {
    if texto.chars().count() <= max_chars {
        texto.to_owned()
    } else {
        let mut s: String = texto.chars().take(max_chars.saturating_sub(1)).collect();
        s.push('…');
        s
    }
}

fn etiqueta_periodo(periodo: &str) -> String {
    if periodo == "todo" {
        return "Todo el historial".to_owned();
    }
    if periodo.len() == 7 && periodo.as_bytes()[4] == b'-' {
        let anio = &periodo[..4];
        let mes = match &periodo[5..] {
            "01" => "Enero",
            "02" => "Febrero",
            "03" => "Marzo",
            "04" => "Abril",
            "05" => "Mayo",
            "06" => "Junio",
            "07" => "Julio",
            "08" => "Agosto",
            "09" => "Septiembre",
            "10" => "Octubre",
            "11" => "Noviembre",
            "12" => "Diciembre",
            _ => periodo,
        };
        return format!("{mes} {anio}");
    }
    periodo.to_owned()
}

fn formatear_tiempo_svg(segundos: f64) -> String {
    let total_min = (segundos.max(0.0) / 60.0).round() as u64;
    if total_min < 60 {
        format!("{total_min} min")
    } else {
        let h = total_min / 60;
        let m = total_min % 60;
        if m == 0 {
            format!("{h} h")
        } else {
            format!("{h} h {m} min")
        }
    }
}

/// Genera una tarjeta SVG autónoma (800×480) del resumen de escucha (F8.3).
#[must_use]
pub fn tarjeta_svg(resumen: &ResumenEscucha, nombre_usuario: &str) -> String {
    let titulo_usuario = escapar_xml(&truncar_texto(
        if nombre_usuario.trim().is_empty() {
            "Tu música"
        } else {
            nombre_usuario.trim()
        },
        32,
    ));
    let subtitulo_periodo = escapar_xml(&etiqueta_periodo(&resumen.periodo));
    let tiempo = escapar_xml(&formatear_tiempo_svg(resumen.segundos_escuchados));

    let artista_top = resumen
        .top_artistas
        .first()
        .map_or_else(|| "—".to_owned(), |a| truncar_texto(&a.nombre, 28));
    let cancion_top = resumen
        .top_canciones
        .first()
        .map_or_else(|| "—".to_owned(), |c| truncar_texto(&c.pista.titulo, 28));

    let valores = [
        resumen.radar.energia,
        resumen.radar.bailable,
        resumen.radar.alegre,
        resumen.radar.calma,
        resumen.radar.nocturna,
        resumen.radar.melancolica,
    ];
    let cx = 610.0_f64;
    let cy = 240.0_f64;
    let radio = 105.0_f64;

    let mut puntos_poligono = String::new();
    for (i, v) in valores.iter().enumerate() {
        let ang = -PI / 2.0 + (i as f64) * PI / 3.0;
        let r = radio * v.clamp(0.08, 1.0);
        let x = cx + r * ang.cos();
        let y = cy + r * ang.sin();
        if !puntos_poligono.is_empty() {
            puntos_poligono.push(' ');
        }
        puntos_poligono.push_str(&format!("{x:.1},{y:.1}"));
    }

    let mut guia_ext = String::new();
    let mut guia_med = String::new();
    for i in 0..6 {
        let ang = -PI / 2.0 + (i as f64) * PI / 3.0;
        let x1 = cx + radio * ang.cos();
        let y1 = cy + radio * ang.sin();
        let x2 = cx + (radio * 0.5) * ang.cos();
        let y2 = cy + (radio * 0.5) * ang.sin();
        if i > 0 {
            guia_ext.push(' ');
            guia_med.push(' ');
        }
        guia_ext.push_str(&format!("{x1:.1},{y1:.1}"));
        guia_med.push_str(&format!("{x2:.1},{y2:.1}"));
    }

    format!(
        r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 480" width="800" height="480">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0b0d12"/>
      <stop offset="100%" stop-color="#151924"/>
    </linearGradient>
  </defs>
  <rect width="800" height="480" rx="20" fill="url(#bg)"/>
  <rect x="20" y="20" width="760" height="440" rx="16" fill="none" stroke="#262c3d" stroke-width="1"/>
  <text x="48" y="68" fill="#9aa3b8" font-family="Inter, sans-serif" font-size="14" font-weight="600" letter-spacing="1.5">RESUMEN LOCAL DE ESCUCHA · {subtitulo_periodo}</text>
  <text x="48" y="106" fill="#f3f5f9" font-family="Inter, sans-serif" font-size="30" font-weight="700">{titulo_usuario}</text>

  <g font-family="Inter, sans-serif">
    <rect x="48" y="132" width="180" height="78" rx="10" fill="#171c28"/>
    <text x="64" y="160" fill="#9aa3b8" font-size="12">TIEMPO ESCUCHADO</text>
    <text x="64" y="192" fill="#e8a849" font-size="22" font-weight="700">{tiempo}</text>

    <rect x="242" y="132" width="180" height="78" rx="10" fill="#171c28"/>
    <text x="258" y="160" fill="#9aa3b8" font-size="12">REPRODUCCIONES</text>
    <text x="258" y="192" fill="#f3f5f9" font-size="22" font-weight="700">{reproducciones}</text>

    <rect x="48" y="222" width="180" height="78" rx="10" fill="#171c28"/>
    <text x="64" y="250" fill="#9aa3b8" font-size="12">PISTAS DISTINTAS</text>
    <text x="64" y="282" fill="#f3f5f9" font-size="22" font-weight="700">{pistas}</text>

    <rect x="242" y="222" width="180" height="78" rx="10" fill="#171c28"/>
    <text x="258" y="250" fill="#9aa3b8" font-size="12">ARTISTAS DISTINTOS</text>
    <text x="258" y="282" fill="#f3f5f9" font-size="22" font-weight="700">{artistas}</text>

    <rect x="48" y="314" width="374" height="52" rx="10" fill="#171c28"/>
    <text x="64" y="336" fill="#9aa3b8" font-size="11">ARTISTA MÁS ESCUCHADO</text>
    <text x="64" y="356" fill="#f3f5f9" font-size="15" font-weight="600">{artista_top}</text>

    <rect x="48" y="376" width="374" height="52" rx="10" fill="#171c28"/>
    <text x="64" y="398" fill="#9aa3b8" font-size="11">CANCIÓN MÁS ESCUCHADA</text>
    <text x="64" y="418" fill="#f3f5f9" font-size="15" font-weight="600">{cancion_top}</text>
  </g>

  <g font-family="Inter, sans-serif" font-size="12" fill="#9aa3b8" text-anchor="middle">
    <polygon points="{guia_ext}" fill="#131722" stroke="#2c3448" stroke-width="1"/>
    <polygon points="{guia_med}" fill="none" stroke="#23293a" stroke-width="1" stroke-dasharray="3 3"/>
    <polygon points="{puntos_poligono}" fill="#e8a849" fill-opacity="0.32" stroke="#e8a849" stroke-width="2.5"/>
    <text x="610" y="120">Energía</text>
    <text x="728" y="186" text-anchor="start">Bailable</text>
    <text x="728" y="302" text-anchor="start">Alegre</text>
    <text x="610" y="368">Calma</text>
    <text x="492" y="302" text-anchor="end">Nocturna</text>
    <text x="492" y="186" text-anchor="end">Melancólica</text>
  </g>

  <text x="752" y="444" fill="#687086" font-family="Inter, sans-serif" font-size="12" font-weight="600" text-anchor="end">NB Sound</text>
</svg>
"##,
        reproducciones = resumen.reproducciones,
        pistas = resumen.pistas_distintas,
        artistas = resumen.artistas_distintos,
        artista_top = escapar_xml(&artista_top),
        cancion_top = escapar_xml(&cancion_top),
    )
}

/// Exporta la tarjeta SVG del resumen de escucha a `destino` (F8.3).
///
/// # Errors
///
/// Devuelve error si el periodo es inválido, si falla la consulta o si no se
/// puede escribir el archivo en `destino`.
pub fn exportar_tarjeta(db: &BaseDeDatos, periodo: Option<&str>, destino: &Path) -> NsResult<()> {
    let resumen = resumen_escucha(db, periodo)?;
    let nombre = crate::preferencias::apariencia(db)?
        .nombre_usuario
        .unwrap_or_else(|| "Tu música".to_owned());
    let svg = tarjeta_svg(&resumen, &nombre);
    std::fs::write(destino, svg.as_bytes()).map_err(|_| NsError::StorageFailure)
}

/// # Errors
///
/// [`NsError::StorageFailure`] si alguna consulta falla.
pub fn perfil(db: &BaseDeDatos) -> NsResult<Perfil> {
    let conn = db.conexion()?;
    let reproducciones: i64 = uno(&conn, "SELECT count(*) FROM historial")?;
    let pistas_distintas: i64 = uno(&conn, "SELECT count(DISTINCT pista_id) FROM historial")?;
    let pistas_en_biblioteca: i64 = uno(
        &conn,
        "SELECT count(*) FROM pistas WHERE estado = 'biblioteca'",
    )?;
    let artistas_distintos: i64 = uno(
        &conn,
        "SELECT count(DISTINCT p.artista_id) FROM historial h JOIN pistas p ON p.id = h.pista_id",
    )?;
    let albumes_distintos: i64 = uno(
        &conn,
        "SELECT count(DISTINCT p.album_id) FROM historial h JOIN pistas p ON p.id = h.pista_id",
    )?;
    // La V1 no apuntó cuánto se escuchó en más de la mitad de las filas: entonces
    // cuenta la duración de la pista, que es lo que la V1 sumaba.
    let segundos_escuchados: f64 = uno(
        &conn,
        "SELECT total(coalesce(h.escuchado_seg, p.duracion_seg, 0))
         FROM historial h LEFT JOIN pistas p ON p.id = h.pista_id",
    )?;
    let anio_favorito = pares(
        &conn,
        "SELECT p.anio, count(*) AS n FROM historial h JOIN pistas p ON p.id = h.pista_id
         WHERE p.anio IS NOT NULL GROUP BY p.anio ORDER BY n DESC, p.anio DESC LIMIT 1",
    )?
    .first()
    .map(|f| f.0);
    let hora_pico = pares(
        &conn,
        "SELECT CAST(strftime('%H', reproducida_en, 'localtime') AS INTEGER) AS h, count(*) AS n
         FROM historial GROUP BY h ORDER BY n DESC, h LIMIT 1",
    )?
    .first()
    .map(|f| f.0.clamp(0, 23) as u32);

    let hoy = "date(h.reproducida_en, 'localtime') = date('now', 'localtime')";
    let escuchas_hoy: i64 = uno(
        &conn,
        &format!("SELECT count(*) FROM historial h WHERE {hoy}"),
    )?;
    let artistas_hoy = {
        let mut s = conn
            .prepare(&format!(
                "SELECT a.id, a.nombre, count(*) AS n FROM historial h
                 JOIN pistas p ON p.id = h.pista_id JOIN artistas a ON a.id = p.artista_id
                 WHERE {hoy} GROUP BY a.id ORDER BY n DESC, a.nombre LIMIT 3"
            ))
            .map_err(|_| NsError::StorageFailure)?;
        let filas = s
            .query_map([], |f| {
                Ok(ArtistaDelDia {
                    id: f.get(0)?,
                    nombre: f.get(1)?,
                    escuchas: f.get::<_, i64>(2)? as u32,
                })
            })
            .map_err(|_| NsError::StorageFailure)?
            .collect::<rusqlite::Result<Vec<_>>>()
            .map_err(|_| NsError::StorageFailure)?;
        filas
    };

    let dias: i64 = uno(
        &conn,
        "SELECT CAST(strftime('%d', date('now', 'localtime', 'start of month', '+1 month', '-1 day')) AS INTEGER)",
    )?;
    let mut dias_del_mes = vec![0u32; dias.max(0) as usize];
    for (dia, n) in pares(
        &conn,
        "SELECT CAST(strftime('%d', reproducida_en, 'localtime') AS INTEGER), count(*) FROM historial
         WHERE strftime('%Y-%m', reproducida_en, 'localtime') = strftime('%Y-%m', 'now', 'localtime')
         GROUP BY 1",
    )? {
        if let Some(d) = dias_del_mes.get_mut((dia - 1).max(0) as usize) {
            *d = n as u32;
        }
    }

    let canciones = pares(
        &conn,
        "SELECT h.pista_id, count(*) AS n FROM historial h JOIN pistas p ON p.id = h.pista_id
         WHERE p.estado = 'biblioteca' GROUP BY h.pista_id ORDER BY n DESC, h.pista_id LIMIT 10",
    )?;
    let albumes = pares(
        &conn,
        "SELECT p.album_id, count(*) AS n FROM historial h JOIN pistas p ON p.id = h.pista_id
         WHERE p.album_id IS NOT NULL GROUP BY p.album_id ORDER BY n DESC, p.album_id LIMIT 10",
    )?;
    let artistas = pares(
        &conn,
        "SELECT p.artista_id, count(*) AS n FROM historial h JOIN pistas p ON p.id = h.pista_id
         WHERE p.artista_id IS NOT NULL GROUP BY p.artista_id ORDER BY n DESC, p.artista_id LIMIT 10",
    )?;
    drop(conn);

    let ids: Vec<i64> = canciones.iter().map(|f| f.0).collect();
    let top_canciones = biblioteca::resumenes(db, &ids)?
        .into_iter()
        .map(|pista| {
            let n = canciones
                .iter()
                .find(|f| f.0 == pista.id)
                .map_or(0, |f| f.1);
            PistaEscuchada {
                pista,
                reproducciones: n as u32,
            }
        })
        .collect();
    let top_albumes = albumes
        .iter()
        .filter_map(|(id, _)| biblioteca::album(db, *id).transpose())
        .collect::<NsResult<Vec<_>>>()?;
    let top_artistas = artistas
        .iter()
        .filter_map(|(id, _)| biblioteca::artista(db, *id).transpose())
        .collect::<NsResult<Vec<_>>>()?;

    Ok(Perfil {
        reproducciones: reproducciones as u32,
        pistas_distintas: pistas_distintas as u32,
        pistas_en_biblioteca: pistas_en_biblioteca as u32,
        artistas_distintos: artistas_distintos as u32,
        albumes_distintos: albumes_distintos as u32,
        segundos_escuchados,
        anio_favorito,
        hora_pico,
        escuchas_hoy: escuchas_hoy as u32,
        artistas_hoy,
        dias_del_mes,
        top_canciones,
        top_albumes,
        top_artistas,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sin_historial_todo_esta_a_cero() {
        let db = BaseDeDatos::en_memoria().unwrap();
        let p = perfil(&db).unwrap();
        assert_eq!(p.reproducciones, 0);
        assert_eq!(p.anio_favorito, None);
        assert_eq!(p.hora_pico, None);
        assert!((28..=31).contains(&p.dias_del_mes.len()));
    }

    #[test]
    fn el_historial_da_la_identidad_la_actividad_y_los_tops() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'a', 'a'), (2, 'b', 'b');
                 INSERT INTO albumes (id, artista_id, titulo, clave) VALUES (10, 1, 'x', 'x');
                 INSERT INTO pistas (id, album_id, artista_id, titulo, ruta, duracion_seg, anio) VALUES
                     (1, 10, 1, 'uno', 'a', 100, 2020), (2, NULL, 2, 'dos', 'b', 200, 1999);
                 INSERT INTO historial (pista_id, escuchado_seg, reproducida_en) VALUES
                     (1, NULL, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                     (1, 50, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                     (2, NULL, '2000-01-01T00:00:00Z');",
            )
            .unwrap();
        let p = perfil(&db).unwrap();
        assert_eq!(
            (p.reproducciones, p.pistas_distintas, p.pistas_en_biblioteca),
            (3, 2, 2)
        );
        assert_eq!((p.artistas_distintos, p.albumes_distintos), (2, 1));
        assert_eq!(p.segundos_escuchados, 350.0, "sin dato, cuenta la duración");
        assert_eq!(p.anio_favorito, Some(2020));
        assert_eq!(p.escuchas_hoy, 2);
        assert_eq!(p.artistas_hoy[0].nombre, "a");
        assert_eq!(p.dias_del_mes.iter().sum::<u32>(), 2);
        assert_eq!(p.top_canciones[0].pista.id, 1);
        assert_eq!(p.top_canciones[0].reproducciones, 2);
        assert_eq!(p.top_artistas[0].id, 1);
    }

    #[test]
    fn resumen_escucha_filtra_por_periodo_y_calcula_radar_y_mapa_calor() {
        let db = BaseDeDatos::en_memoria().unwrap();
        db.conexion()
            .unwrap()
            .execute_batch(
                "INSERT INTO artistas (id, nombre, clave) VALUES (1, 'A & B', 'ab'), (2, 'C', 'c');
                 INSERT INTO albumes (id, artista_id, titulo, clave) VALUES (10, 1, 'X', 'x');
                 INSERT INTO pistas (id, album_id, artista_id, titulo, ruta, duracion_seg) VALUES
                     (1, 10, 1, 'Canción <1>', 'a', 180),
                     (2, NULL, 2, 'Dos', 'b', 240);
                 INSERT INTO rasgos (pista_id, bpm, energia, bailabilidad, valencia, calma, para_la_noche, oscuridad, melancolia, version)
                 VALUES
                     (1, 128.0, 0.8, 0.9, 0.7, 0.2, 0.3, 0.1, 0.1, '1'),
                     (2, 90.0, 0.3, 0.4, 0.2, 0.8, 0.7, 0.6, 0.9, '1');
                 INSERT INTO historial (pista_id, escuchado_seg, reproducida_en) VALUES
                     (1, 180, '2026-03-15T15:00:00Z'),
                     (1, 120, '2026-03-16T15:00:00Z'),
                     (2, 240, '2025-11-10T15:00:00Z');",
            )
            .unwrap();

        let todo = resumen_escucha(&db, None).unwrap();
        assert_eq!(todo.periodo, "todo");
        assert!(todo.periodos_disponibles.contains(&"todo".to_owned()));
        assert!(todo.periodos_disponibles.contains(&"2026".to_owned()));
        assert!(todo.periodos_disponibles.contains(&"2026-03".to_owned()));
        assert_eq!(todo.reproducciones, 3);
        assert_eq!(todo.pistas_distintas, 2);
        assert_eq!(todo.mapa_calor.len(), 168);
        assert_eq!(todo.mapa_calor.iter().sum::<u32>(), 3);
        assert!(todo.radar.energia > 0.5 && todo.radar.energia < 0.7);

        let marzo = resumen_escucha(&db, Some("2026-03")).unwrap();
        assert_eq!(marzo.periodo, "2026-03");
        assert_eq!(marzo.reproducciones, 2);
        assert_eq!(marzo.pistas_distintas, 1);
        assert_eq!(marzo.segundos_escuchados, 300.0);
        assert!((marzo.radar.energia - 0.8).abs() < 1e-6);

        let anio_2025 = resumen_escucha(&db, Some("2025")).unwrap();
        assert_eq!(anio_2025.reproducciones, 1);
        assert_eq!(anio_2025.top_canciones[0].pista.id, 2);

        assert!(resumen_escucha(&db, Some("2026-13")).is_err());
        assert!(resumen_escucha(&db, Some("invalido")).is_err());

        let svg = tarjeta_svg(&marzo, "Nathan <NB>");
        assert!(svg.starts_with("<svg"));
        assert!(svg.contains("Marzo 2026"));
        assert!(svg.contains("Nathan &lt;NB&gt;"));
        assert!(svg.contains("A &amp; B"));
        assert!(svg.contains("Canción &lt;1&gt;"));

        let ruta = std::env::temp_dir().join(format!("nb-sound-test-{}.svg", std::process::id()));
        exportar_tarjeta(&db, Some("2026-03"), &ruta).unwrap();
        let leido = std::fs::read_to_string(&ruta).unwrap();
        let _ = std::fs::remove_file(&ruta);
        assert!(leido.contains("<polygon"));
    }
}
