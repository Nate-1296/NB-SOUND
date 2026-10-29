"""
audio_features.py
-----------------
Análisis de audio ligero usando librosa.

Responsabilidades:
    - Extraer features acústicas y emocionales sobre un archivo de audio.
    - Computar proxies de alto nivel (danceability, energy, valence, etc.)
      a partir de descriptores espectrales y temporales.
    - Derivar vibe tags textuales a partir de los proxies.

Diseño:
    - El análisis es local: no requiere red ni modelos externos.
    - En modo 'light', carga solo un segmento inicial del archivo
      (configurable con AUDIO_FEATURES_SEGMENT_SECONDS) para minimizar
      el tiempo de análisis durante la importación.
    - Los proxies son heurísticas normalizadas [0, 1]; no son valores
      de referencia MIR sino estimaciones de utilidad práctica para
      discovery y clasificación.
    - La versión del analizador se almacena en cada resultado para
      soportar re-análisis selectivo al actualizar la heurística.

Threading:
    - AudioFeatureAnalyzer.analyze() es stateless y puede llamarse
      desde múltiples hilos sin sincronización adicional.
"""

from __future__ import annotations
import json, time, hashlib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
import numpy as np
from infra.logger import obtener_logger

_log = obtener_logger('audio_features')
ANALYZER_VERSION='audio_features_v1'

@dataclass
class AudioFeatureResult:
    """
    Resultado completo de un análisis de audio ligero.

    Campos de identidad:
        track_id:         Identificador de pista en la base de datos.
        file_path:        Ruta absoluta del archivo analizado.
        file_hash:        SHA-256 del archivo (detecta cambios en el contenido).
        analyzer_version: Versión de la heurística aplicada; se persiste para
                          poder invalidar análisis cuando la heurística cambie.
        analysis_mode:    'light' (segmento inicial) o 'standard'/'full' (archivo completo).
        analysis_status:  'ready' | 'failed'.

    Campos acústicos objetivos:
        duration_sec:               Duración total del segmento analizado, en segundos.
        sample_rate:                Tasa de muestreo usada (22050 Hz en modo light).
        channels:                   Canales del audio cargado (siempre 1, mono forzado).
        bpm:                        Tempo estimado por beat_track de librosa, en BPM.
        beat_count:                 Número de beats detectados en el segmento.
        onset_rate:                 Densidad media de onsets (eventos de ataque), u.a.
        rms_mean / rms_std:         Media y desviación de la energía RMS por frame.
        loudness_proxy:             Igual a rms_mean; proxy de loudness percibida.
        spectral_centroid_mean:     Centroide espectral medio en Hz. Correlaciona con brillo.
        spectral_bandwidth_mean:    Ancho de banda espectral medio en Hz.
        spectral_rolloff_mean:      Frecuencia de rolloff espectral (85%) media en Hz.
        zero_crossing_rate_mean:    Tasa media de cruces por cero. Alta en voces y
                                    percusión; baja en tonos puros.

    Campos perceptuales derivados (proxies [0, 1]):
        brightness:         Centroide normalizado a 4 kHz; alta = brillante/agudo.
        darkness_proxy:     1 - brightness.
        key_name:           Nota fundamental estimada por chroma_cqt (C, C#, ..., B).
        mode:               'major' o 'minor' por heurística de escala.
        danceability_proxy: Combinación de tempo (normalizado a 140 BPM) y onset_rate.
        energy:             RMS normalizado, proxy de intensidad sonora percibida.
        valence_proxy:      Estimación de positividad emocional; combina brillo y arousal.
        arousal_proxy:      Nivel de activación; combina energía y tempo.
        aggressiveness_proxy: Energía + ZCR; alta en metal/hardcore.
        calmness_proxy:     Complemento del arousal.
        melancholy_proxy:   Valence invertida modulada por calma.
        focus_score_proxy:  Calma + estabilidad RMS + baja ZCR; útil para trabajo/estudio.
        workout_score_proxy: Energía + tempo + onsets; útil para entrenamiento.
        party_score_proxy:  Dance + energía + valence.
        night_score_proxy:  Oscuridad + melancolía; útil para selección nocturna.

    Metadatos de ejecución:
        raw_basic_json:  JSON auxiliar con notas del análisis.
        error_code / error_message: Código y descripción del error si analysis_status='failed'.
        started_at / analyzed_at: Timestamps ISO 8601 UTC del inicio y fin del análisis.
    """
    track_id: str
    file_path: str
    file_hash: str
    analyzer_version: str = ANALYZER_VERSION
    analysis_mode: str = 'light'
    analysis_status: str = 'ready'
    duration_sec: Optional[float]=None
    sample_rate: Optional[int]=None
    channels: Optional[int]=None
    bpm: Optional[float]=None
    beat_count: Optional[int]=None
    onset_rate: Optional[float]=None
    rms_mean: Optional[float]=None
    rms_std: Optional[float]=None
    loudness_proxy: Optional[float]=None
    spectral_centroid_mean: Optional[float]=None
    spectral_bandwidth_mean: Optional[float]=None
    spectral_rolloff_mean: Optional[float]=None
    zero_crossing_rate_mean: Optional[float]=None
    brightness: Optional[float]=None
    darkness_proxy: Optional[float]=None
    key_name: str='unknown'
    mode: str='unknown'
    danceability_proxy: Optional[float]=None
    energy: Optional[float]=None
    valence_proxy: Optional[float]=None
    arousal_proxy: Optional[float]=None
    aggressiveness_proxy: Optional[float]=None
    calmness_proxy: Optional[float]=None
    melancholy_proxy: Optional[float]=None
    focus_score_proxy: Optional[float]=None
    workout_score_proxy: Optional[float]=None
    party_score_proxy: Optional[float]=None
    night_score_proxy: Optional[float]=None
    raw_basic_json: str='{}'
    error_code: str=''
    error_message: str=''
    started_at: str=''
    analyzed_at: str=''

    def to_dict(self):
        return asdict(self)


def _hash(path: Path) -> str:
    """SHA-256 del archivo en bloques de 64 KB para no cargar el archivo completo en memoria."""
    h=hashlib.sha256()
    with path.open('rb') as f:
        for c in iter(lambda:f.read(65536),b''): h.update(c)
    return h.hexdigest()

def _clip01(x): return float(max(0.0,min(1.0,x)))

class AudioFeatureAnalyzer:
    def analyze(self, track_id:str, file_path:Path, mode:str='light') -> AudioFeatureResult:
        """
        Analiza un archivo de audio y retorna su AudioFeatureResult.

        El análisis incluye:
            1. Carga del audio en mono a 22050 Hz (segmento o completo según mode).
            2. Extracción de descriptores temporales: BPM, beats, onsets, RMS, ZCR.
            3. Extracción de descriptores espectrales: centroid, bandwidth, rolloff.
            4. Estimación de tonalidad por chroma_cqt.
            5. Cómputo de proxies perceptuales normalizados [0, 1].

        Args:
            track_id:  Identificador de la pista en base de datos.
            file_path: Ruta al archivo de audio.
            mode:      'light' carga solo el segmento inicial definido en settings;
                       cualquier otro valor carga el archivo completo.

        Returns:
            AudioFeatureResult con status 'ready' si el análisis fue exitoso,
            o 'failed' con error_code/error_message si ocurrió una excepción.

        Nota: librosa se importa localmente para no bloquear el arranque si no
        está instalado en el entorno.
        """
        started=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        try:
            import librosa
            from config import settings as _settings
            segment_duration = _settings.AUDIO_FEATURES_SEGMENT_SECONDS if mode == 'light' else None
            y, sr = librosa.load(str(file_path), sr=22050, mono=True, duration=segment_duration)
            duration=float(librosa.get_duration(y=y, sr=sr))
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
            tempo_arr = np.asarray(tempo).reshape(-1)
            tempo_value = float(tempo_arr[0]) if tempo_arr.size else 0.0
            rms=librosa.feature.rms(y=y)[0]
            centroid=librosa.feature.spectral_centroid(y=y,sr=sr)[0]
            bandwidth=librosa.feature.spectral_bandwidth(y=y,sr=sr)[0]
            rolloff=librosa.feature.spectral_rolloff(y=y,sr=sr)[0]
            zcr=librosa.feature.zero_crossing_rate(y)[0]
            onset_env=librosa.onset.onset_strength(y=y,sr=sr)
            chroma=librosa.feature.chroma_cqt(y=y,sr=sr)
            chroma_mean=chroma.mean(axis=1)
            key_idx=int(np.argmax(chroma_mean));keys=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
            key=keys[key_idx]
            bright=_clip01(float(np.mean(centroid))/4000)
            energy=_clip01(float(np.mean(rms))*3)
            arousal=_clip01(0.6*energy+0.4*_clip01(tempo_value/180))
            calm=_clip01(1-arousal)
            valence=_clip01(0.5*bright+0.5*(1-calm))
            melancholy=_clip01((1-valence)*0.7+calm*0.3)
            dance=_clip01(0.5*_clip01(tempo_value/140)+0.5*_clip01(np.mean(onset_env)/5))
            party=_clip01(0.4*dance+0.4*energy+0.2*valence)
            workout=_clip01(0.5*energy+0.3*_clip01(tempo_value/160)+0.2*_clip01(np.mean(onset_env)/6))
            focus=_clip01(0.5*calm+0.3*(1-float(np.std(rms)))+0.2*(1-float(np.mean(zcr))*5))
            night=_clip01(0.6*(1-bright)+0.4*melancholy)
            aggress=_clip01(0.5*energy+0.5*float(np.mean(zcr))*5)
            analyzed=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            payload={"heuristics":True,"note":"proxies 0-1"}
            return AudioFeatureResult(track_id=track_id,file_path=str(file_path),file_hash=_hash(file_path),analysis_mode=mode,duration_sec=duration,sample_rate=sr,channels=1,bpm=tempo_value or None,beat_count=int(len(beats)),onset_rate=float(np.mean(onset_env)),rms_mean=float(np.mean(rms)),rms_std=float(np.std(rms)),loudness_proxy=float(np.mean(rms)),spectral_centroid_mean=float(np.mean(centroid)),spectral_bandwidth_mean=float(np.mean(bandwidth)),spectral_rolloff_mean=float(np.mean(rolloff)),zero_crossing_rate_mean=float(np.mean(zcr)),brightness=bright,darkness_proxy=_clip01(1-bright),key_name=key,mode='minor' if key in {'A','E','B','F#','C#','G#','D#'} else 'major',danceability_proxy=dance,energy=energy,valence_proxy=valence,arousal_proxy=arousal,aggressiveness_proxy=aggress,calmness_proxy=calm,melancholy_proxy=melancholy,focus_score_proxy=focus,workout_score_proxy=workout,party_score_proxy=party,night_score_proxy=night,raw_basic_json=json.dumps(payload,ensure_ascii=False),started_at=started,analyzed_at=analyzed)
        except Exception as e:
            # Códigos específicos para diagnóstico: la UI muestra cuántos
            # archivos fallaron por categoría, y al usuario le queda claro
            # si necesita instalar dependencias o si el problema es por
            # archivo.
            error_code = 'analysis_error'
            mensaje = str(e)
            mensaje_lower = mensaje.lower()
            if isinstance(e, ModuleNotFoundError) or 'no module named' in mensaje_lower:
                if 'librosa' in mensaje_lower:
                    error_code = 'librosa_missing'
                elif 'soundfile' in mensaje_lower:
                    error_code = 'soundfile_missing'
                elif 'audioread' in mensaje_lower:
                    error_code = 'audioread_missing'
                else:
                    error_code = 'dependency_missing'
            elif isinstance(e, FileNotFoundError) or 'no such file' in mensaje_lower:
                error_code = 'file_not_found'
            elif 'codec' in mensaje_lower or 'format' in mensaje_lower or 'decode' in mensaje_lower:
                error_code = 'codec_error'
            elif 'memory' in mensaje_lower:
                error_code = 'memory_error'
            _log.warning('Audio features falló en %s [%s]: %s', file_path, error_code, e)
            return AudioFeatureResult(track_id=track_id,file_path=str(file_path),file_hash=_hash(file_path) if file_path.exists() else '',analysis_status='failed',analysis_mode=mode,error_code=error_code,error_message=mensaje[:300],started_at=started,analyzed_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))


def derive_vibe_tags(features: AudioFeatureResult) -> list[dict]:
    """
    Genera vibe tags textuales a partir de los proxies del AudioFeatureResult.

    Una tag se incluye si su proxy de origen supera el umbral de 0.35.
    El campo 'source' es 'basic_rules' para distinguirlas de las tags
    generadas por modelos deep (source='deep_model').

    Tags disponibles:
        energetica    → energy proxy.
        tranquila     → calmness proxy.
        bailable      → danceability proxy.
        triste        → melancholy proxy.
        nocturna      → night_score proxy.
        entrenamiento → workout_score proxy.
        concentracion → focus_score proxy.
        fiesta        → party_score proxy.

    Returns:
        Lista de dicts con claves: track_id, tag, score, confidence,
        source, explanation, analyzer_version.
    """
    tags=[]
    def add(tag,score,exp):
        if score>=0.35: tags.append({"track_id":features.track_id,"tag":tag,"score":round(float(score),4),"confidence":round(float(score),4),"source":"basic_rules","explanation":exp,"analyzer_version":features.analyzer_version})
    e=features.energy or 0
    c=features.calmness_proxy or 0
    m=features.melancholy_proxy or 0
    d=features.danceability_proxy or 0
    add('energetica',e,'energía proxy alta')
    add('tranquila',c,'calma y baja activación')
    add('bailable',d,'tempo/onset + danceability')
    add('triste',m,'valence baja + calma')
    add('nocturna',features.night_score_proxy or 0,'brillo bajo + melancolía')
    add('entrenamiento',features.workout_score_proxy or 0,'energía + BPM')
    add('concentracion',features.focus_score_proxy or 0,'calma + baja agresividad')
    add('fiesta',features.party_score_proxy or 0,'danceability + energía')
    return tags
