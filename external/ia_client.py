# =============================================================================
# external/ia_client.py
#
# Cliente de desempate inteligente usando un modelo de lenguaje economico.
#
# ROL EN EL PIPELINE
# ──────────────────────────────────────────────────────────────────────────────
# La IA entra SOLO cuando el scoring determinista no puede decidir con
# seguridad: cuando el gap entre los dos mejores candidatos es menor que
# IA_TIEBREAK_MIN_GAP y el puntaje esta en la zona de ambiguedad.
#
# La IA NO es creativa aqui: solo puede:
#   a) Elegir uno de los candidatos proporcionados.
#   b) Devolver "revision_manual" si ninguno es adecuado.
#
# Nunca inventa albumes, artistas ni releases. La respuesta se valida
# contra la lista de candidatos: si el release_id no existe en ella,
# la respuesta se descarta y el archivo va a revision manual.
#
# FORMATO DE SALIDA
# La IA devuelve UNICAMENTE un JSON con este esquema fijo:
#   {
#     "decision":   "album" | "single" | "ep" | "revision_manual",
#     "release_id": "<id del release elegido>" | null,
#     "confianza":  0.0 - 1.0,
#     "razones":    ["razon breve 1", "razon breve 2"]
#   }
#
# Proveedores soportados: Anthropic (Claude) | OpenAI (ChatGPT)
# Se selecciona en config/settings.py con el campo IA_PROVEEDOR.
#
# Dependencias opcionales:
#   pip install anthropic   (para Anthropic)
#   pip install openai      (para OpenAI)
# =============================================================================

import json
import re
from typing import Optional

from config.settings import (
    ANTHROPIC_API_KEY_RESOLVED,
    OPENAI_API_KEY_RESOLVED,
    ENABLE_IA_TIEBREAK,
    IA_PROVEEDOR,
    IA_TIEBREAK_MODEL,
    IA_MAX_TOKENS,
    IA_TIMEOUT_SEG,
)
from domain.models import (
    CandidatoMB,
    DecisionIA,
    MetadataNormalizada,
    ResultadoShazam,
    ResultadoAcoustID,
)
from infra.logger import obtener_logger

_log = obtener_logger("ia_client")

# Intentar importar librerias de forma opcional
try:
    import anthropic as _anthropic_lib
    _ANTHROPIC_DISPONIBLE = True
except ImportError:
    _ANTHROPIC_DISPONIBLE = False

try:
    import openai as _openai_lib
    _OPENAI_DISPONIBLE = True
except ImportError:
    _OPENAI_DISPONIBLE = False

# Prompt del sistema: instrucciones invariantes pasadas una sola vez
_SYSTEM_PROMPT = """Eres un sistema de clasificacion musical de alta precision.
Tu unica funcion es elegir el release correcto de MusicBrainz para una cancion dada,
o indicar que ninguno es adecuado.

REGLAS ABSOLUTAS:
1. Solo puedes elegir un candidato de la lista proporcionada. Nunca inventes releases.
2. Si ningun candidato es adecuado, devuelve revision_manual en el campo decision.
3. Prefiere SIEMPRE releases con status Official sobre los demas.
4. Evita compilaciones, lives, remixes y bootlegs salvo que sean la unica opcion clara.
5. El artista principal del release debe coincidir con el artista del archivo.
6. En caso de duda real, devuelve revision_manual. Es mejor que un error.
7. Responde UNICAMENTE con el JSON solicitado, sin texto adicional, sin markdown."""

_SYSTEM_PROMPT_DISCOGRAPHY = """Eres un asistente de organización discográfica.
Solo puedes clasificar releases existentes en buckets permitidos.
Nunca inventes release_id ni estructuras nuevas.
Si no estás seguro, usa bucket 'revisar' con baja confianza.
Responde únicamente JSON válido."""


def _construir_prompt_usuario(
    norm: MetadataNormalizada,
    candidatos: list[CandidatoMB],
    resultado_shazam: Optional[ResultadoShazam] = None,
    resultado_acoustid: Optional[ResultadoAcoustID] = None,
) -> str:
    """
    Construye el mensaje de usuario para el modelo de desempate.

    El prompt incluye tres secciones:
      1. Contexto del archivo: metadata local (titulo, artista, album, ISRC,
         duracion), fuente de cada campo (tag original, Shazam, etc.) y
         datos de fuentes externas si estan disponibles (Shazam, AcoustID).
      2. Lista cerrada de candidatos: solo los campos relevantes para la
         decision, incluyendo el puntaje del sistema y su desglose.
      3. Esquema de respuesta JSON esperado: la instruccion de formato
         va al final del prompt de usuario para maximizar adherencia.

    De AcoustID solo se incluyen los primeros 3 recording_ids para no
    inflar el prompt innecesariamente.
    """
    # Contexto del archivo
    contexto_archivo = {
        "metadata_local": {
            "titulo":   norm.titulo,
            "artista":  norm.artista_principal,
            "album":    norm.album or None,
            "anio":     norm.anio,
            "duracion_seg": norm.duracion_seg,
            "isrc":     norm.isrc,
        },
        "fuente_titulo":  norm.fuente_titulo.value,
        "fuente_artista": norm.fuente_artista.value,
    }

    if resultado_shazam and resultado_shazam.identificado:
        contexto_archivo["shazam"] = {
            "titulo":  resultado_shazam.titulo,
            "artista": resultado_shazam.artista,
            "album":   resultado_shazam.album,
            "isrc":    resultado_shazam.isrc,
        }

    if resultado_acoustid and resultado_acoustid.recording_ids:
        contexto_archivo["acoustid"] = {
            "recording_ids": resultado_acoustid.recording_ids[:3],
            "mejor_score":   resultado_acoustid.mejor_score,
        }

    # Lista de candidatos (solo datos relevantes para la decision)
    candidatos_json = []
    for c in candidatos:
        candidatos_json.append({
            "release_id":      c.release_id,
            "recording_id":    c.recording_id,
            "titulo":          c.titulo_oficial,
            "artista":         c.artista_principal,
            "album":           c.album_oficial,
            "tipo":            c.tipo_release,
            "status":          c.status_release,
            "anio":            c.anio_release,
            "duracion_seg":    c.duracion_seg,
            "isrc":            c.isrc,
            "es_compilacion":  c.es_compilacion,
            "score_sistema":   round(c.puntaje_total, 4),
            "detalle_score":   {k: round(v, 3) for k, v in c.puntaje_detalle.items()},
            "penalizaciones":  c.penalizaciones,
        })

    prompt = (
        "CONTEXTO DEL ARCHIVO A IDENTIFICAR:\n"
        + json.dumps(contexto_archivo, ensure_ascii=False, indent=2)
        + "\n\nCANDIDATOS DISPONIBLES (elige uno o devuelve revision_manual):\n"
        + json.dumps(candidatos_json, ensure_ascii=False, indent=2)
        + "\n\nResponde UNICAMENTE con este JSON:\n"
        + '{"decision": "album|single|ep|revision_manual", '
        + '"release_id": "<id o null>", '
        + '"confianza": 0.0, '
        + '"razones": ["razon1", "razon2"]}'
    )
    return prompt


def _extraer_json_obj(texto: str) -> Optional[dict]:
    match = re.search(r"\{.*\}", texto or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


# =============================================================================
# CLASE PRINCIPAL
# =============================================================================

class ClienteIA:
    """
    Cliente de desempate usando un modelo de lenguaje (LLM tiebreaker).

    Rol en el pipeline:
      El scoring determinista del matcher asigna puntajes a cada candidato de
      MusicBrainz. Cuando el gap entre los dos mejores candidatos es menor que
      IA_TIEBREAK_MIN_GAP y el puntaje esta en zona de ambiguedad, se invoca
      este cliente para que el modelo elija el candidato correcto.

    Restricciones de diseno (invariantes):
      - El modelo solo puede elegir de la lista cerrada de candidatos
        proporcionados. Nunca inventa releases, artistas ni albums.
      - Si el release_id retornado no esta en la lista de candidatos, la
        respuesta se descarta completamente y el archivo va a revision manual.
      - "revision_manual" es una respuesta valida y preferible a un error.

    Soporta Anthropic (Claude) y OpenAI (ChatGPT). El proveedor activo se
    configura en settings.py con IA_PROVEEDOR. Si el proveedor no esta
    disponible (libreria no instalada o API key ausente), el modulo se
    desactiva y el pipeline continua sin desempate por IA.

    No cachea respuestas: cada llamada genera una nueva consulta al LLM.

    Se instancia una vez por ejecucion del pipeline.
    """

    def __init__(self) -> None:
        self._proveedor = IA_PROVEEDOR.strip()
        self._activo    = False
        self._client    = None

        if not ENABLE_IA_TIEBREAK:
            return

        if self._proveedor == "Anthropic":
            self._activo = _ANTHROPIC_DISPONIBLE and bool(ANTHROPIC_API_KEY_RESOLVED)
            if self._activo:
                self._client = _anthropic_lib.Anthropic(
                    api_key=ANTHROPIC_API_KEY_RESOLVED,
                    timeout=IA_TIMEOUT_SEG,
                )
                _log.info(
                    f"Cliente IA inicializado — proveedor: Anthropic "
                    f"(modelo: {IA_TIEBREAK_MODEL})."
                )
            else:
                razones = []
                if not _ANTHROPIC_DISPONIBLE:
                    razones.append("anthropic no instalado (pip install anthropic)")
                if not ANTHROPIC_API_KEY_RESOLVED:
                    razones.append("ANTHROPIC_API_KEY no configurada en settings.py")
                _log.info(
                    f"Modulo IA desactivado (proveedor: Anthropic). "
                    f"Razones: {'; '.join(razones)}"
                )

        elif self._proveedor == "OpenAI":
            self._activo = _OPENAI_DISPONIBLE and bool(OPENAI_API_KEY_RESOLVED)
            if self._activo:
                self._client = _openai_lib.OpenAI(
                    api_key=OPENAI_API_KEY_RESOLVED,
                    timeout=IA_TIMEOUT_SEG,
                )
                _log.info(
                    f"Cliente IA inicializado — proveedor: OpenAI "
                    f"(modelo: {IA_TIEBREAK_MODEL})."
                )
            else:
                razones = []
                if not _OPENAI_DISPONIBLE:
                    razones.append("openai no instalado (pip install openai)")
                if not OPENAI_API_KEY_RESOLVED:
                    razones.append("OPENAI_API_KEY no configurada en settings.py")
                _log.info(
                    f"Modulo IA desactivado (proveedor: OpenAI). "
                    f"Razones: {'; '.join(razones)}"
                )

        elif self._proveedor in ("No", "no", "None", "Disabled", "disabled", ""):
            # Desactivacion explicita: no se intenta validar claves ni crear cliente.
            _log.info("Modulo IA desactivado por configuracion (IA_PROVEEDOR='No').")

        else:
            _log.warning(
                f"IA_PROVEEDOR '{self._proveedor}' no reconocido. "
                "Valores validos: 'Anthropic' | 'OpenAI' | 'No'. "
                "Modulo IA desactivado."
            )

    # ------------------------------------------------------------------
    # API PUBLICA
    # ------------------------------------------------------------------

    @property
    def activo(self) -> bool:
        """True si el modulo puede ejecutarse."""
        return self._activo

    def desempatar(
        self,
        norm: MetadataNormalizada,
        candidatos: list[CandidatoMB],
        resultado_shazam: Optional[ResultadoShazam] = None,
        resultado_acoustid: Optional[ResultadoAcoustID] = None,
    ) -> DecisionIA:
        """
        Solicita al modelo que elija entre los candidatos proporcionados.

        La llamada es sincrona y bloqueante. Los errores de API (timeout,
        error de red, respuesta invalida) se capturan y retornan un
        DecisionIA vacio (valida=False) sin propagar la excepcion, para
        garantizar que el pipeline nunca se rompa por fallo del LLM.

        La respuesta del modelo se valida estructuralmente antes de usarla:
        el release_id debe pertenecer a la lista de candidatos recibida.

        Args:
            norm:               Metadata normalizada del archivo local.
            candidatos:         Lista cerrada de candidatos de MusicBrainz
                                ya evaluados por el scorer determinista.
            resultado_shazam:   Enriquece el contexto del prompt si disponible.
            resultado_acoustid: Enriquece el contexto del prompt si disponible.

        Returns:
            DecisionIA con la eleccion del modelo y su nivel de confianza.
            Si el modulo esta inactivo o la respuesta es invalida, retorna
            DecisionIA con valida=False.
        """
        decision = DecisionIA()

        if not self._activo or not self._client:
            return decision

        if not candidatos:
            return decision

        prompt = _construir_prompt_usuario(
            norm, candidatos, resultado_shazam, resultado_acoustid
        )

        texto_respuesta = ""
        try:
            if self._proveedor == "Anthropic":
                texto_respuesta = self._llamar_anthropic(prompt)
            elif self._proveedor == "OpenAI":
                texto_respuesta = self._llamar_openai(prompt)
        except (TimeoutError, RuntimeError) as e:
            # Timeout o error de API documentado
            _log.warning(f"Error API timeout/runtime ({self._proveedor}) para desempate: {e}")
            return decision
        except Exception as e:
            # Error inesperado — registrar pero no colapsar
            _log.warning(f"Error inesperado consultando IA ({self._proveedor}): {type(e).__name__}: {e}")
            return decision

        decision.modelo_usado  = IA_TIEBREAK_MODEL

        decision = self._parsear_y_validar_respuesta(
            texto_respuesta, decision, candidatos
        )

        if decision.valida:
            _log.debug(
                f"IA desempato ({self._proveedor}): decision='{decision.decision}' "
                f"release_id='{decision.release_id}' "
                f"confianza={decision.confianza:.2f}"
            )
        else:
            _log.debug(
                f"IA ({self._proveedor}) no pudo desempatar: respuesta invalida o revision_manual. "
                f"Texto: {texto_respuesta[:200]}"
            )

        return decision

    # ------------------------------------------------------------------
    # LLAMADAS ESPECIFICAS POR PROVEEDOR
    # ------------------------------------------------------------------

    def _llamar_anthropic(self, prompt: str) -> str:
        """
        Realiza la llamada a la API de Anthropic (Messages API) y retorna el
        texto de la primera respuesta del asistente.

        El system prompt se pasa como parametro separado (no como mensaje de usuario)
        para que quede en el contexto de sistema del modelo, mejorando la adherencia
        a las restricciones. El timeout se configura en el cliente al inicializar.
        """
        respuesta = self._client.messages.create(
            model=IA_TIEBREAK_MODEL,
            max_tokens=IA_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        if respuesta.content:
            return respuesta.content[0].text if respuesta.content else ""
        return ""

    def _llamar_openai(self, prompt: str) -> str:
        """
        Realiza la llamada a la API de OpenAI (Chat Completions) y retorna el
        texto del primer mensaje del asistente.

        El system prompt se inyecta como mensaje con role='system'. El timeout
        se configura en el cliente al inicializar.
        """
        respuesta = self._client.chat.completions.create(
            model=IA_TIEBREAK_MODEL,
            max_tokens=IA_MAX_TOKENS,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )
        if respuesta.choices:
            return respuesta.choices[0].message.content or ""
        return ""

    # ------------------------------------------------------------------
    # PARSEO Y VALIDACION DE LA RESPUESTA
    # ------------------------------------------------------------------

    def _parsear_y_validar_respuesta(
        self,
        texto: str,
        decision: DecisionIA,
        candidatos: list[CandidatoMB],
    ) -> DecisionIA:
        """
        Parsea el JSON de respuesta del modelo y valida su integridad.

        Validaciones aplicadas:
          1. El texto contiene un bloque JSON valido (tolerante a texto
             decorativo que el modelo pueda agregar antes o despues).
          2. El campo 'decision' es uno de los valores permitidos:
             album, single, ep, revision_manual.
          3. Si la decision no es 'revision_manual', el release_id debe
             existir exactamente en el conjunto de candidatos proporcionados.
             Si no, la respuesta se descarta completamente (valida=False)
             para evitar que el modelo invente releases.
          4. La confianza se fuerza al rango [0.0, 1.0].

        Returns:
            El mismo objeto DecisionIA mutado con los valores parseados si
            la validacion pasa, o sin modificaciones (valida=False) si no.
        """
        # Extraer bloque JSON — el modelo a veces agrega texto decorativo
        datos = _extraer_json_obj(texto)
        if datos is None:
            _log.debug("IA: no se encontro JSON en la respuesta")
            return decision

        # Validar campos obligatorios
        decision_valor = datos.get("decision", "")
        release_id     = datos.get("release_id")
        confianza_raw  = datos.get("confianza", 0.0)
        razones        = datos.get("razones", [])
        try:
            confianza = float(confianza_raw)
        except (TypeError, ValueError):
            confianza = 0.0

        decisiones_validas = {"album", "single", "ep", "revision_manual"}
        if decision_valor not in decisiones_validas:
            _log.debug(f"IA: campo 'decision' invalido: '{decision_valor}'")
            return decision

        # Si no es revision_manual, el release_id debe existir en los candidatos
        ids_candidatos = {c.release_id for c in candidatos}
        if decision_valor != "revision_manual":
            if not release_id or release_id not in ids_candidatos:
                _log.debug(
                    f"IA: release_id '{release_id}' no esta en los candidatos. "
                    "Descartando respuesta."
                )
                return decision

        decision.decision   = decision_valor
        decision.release_id = release_id
        decision.confianza  = float(max(0.0, min(1.0, confianza)))
        decision.razones    = razones if isinstance(razones, list) else []
        decision.valida     = True

        return decision

    def organizar_discografia(self, artist: str, releases: list[dict]) -> list[dict]:
        """Pide sugerencia de buckets por release para reorganización conservadora."""
        if not self._activo or not self._client or not releases:
            return []
        prompt = (
            "Clasifica cada release_id en un bucket permitido.\n"
            "Buckets permitidos: albumes, singles_y_ep, otros, revisar.\n"
            f"artist={artist}\n"
            f"releases={json.dumps(releases, ensure_ascii=False)}\n"
            "Respuesta JSON: {\"items\":[{\"release_id\":\"...\",\"bucket\":\"...\",\"confidence\":0.0,\"reason\":\"...\"}]}"
        )
        try:
            if self._proveedor == "Anthropic":
                raw = self._client.messages.create(
                    model=IA_TIEBREAK_MODEL,
                    max_tokens=IA_MAX_TOKENS,
                    system=_SYSTEM_PROMPT_DISCOGRAPHY,
                    messages=[{"role": "user", "content": prompt}],
                )
                texto = raw.content[0].text if raw.content else ""
            else:
                raw = self._client.chat.completions.create(
                    model=IA_TIEBREAK_MODEL,
                    max_tokens=IA_MAX_TOKENS,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT_DISCOGRAPHY},
                        {"role": "user", "content": prompt},
                    ],
                )
                texto = raw.choices[0].message.content or "" if raw.choices else ""
        except (TimeoutError, RuntimeError) as e:
            # Timeout o error de API
            _log.debug(f"Error API en reorganización discografía ({self._proveedor}): {e}")
            return []
        except Exception as e:
            # Error inesperado
            _log.debug(f"Error inesperado IA reorganización discografía: {type(e).__name__}: {e}")
            return []

        parsed = _extraer_json_obj(texto)
        if parsed is None:
            return []
        items = parsed.get("items")
        return items if isinstance(items, list) else []
