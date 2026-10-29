"""
Diccionarios reutilizables para copy/UI.
"""

from __future__ import annotations

import random
from datetime import datetime


SALUDOS_MANANA = [
    "Buenos días, {nombre}. Tu música ya está lista.",
    "Arranca el día con una buena selección, {nombre}.",
    "Buenos días, {nombre}. Tu biblioteca te estaba esperando.",
    "Hoy puede empezar con algo que ya conoces, {nombre}.",
    "Buen día, {nombre}. Hay música pendiente por retomar.",
    "{nombre}, empieza por una canción que marque el ritmo.",
    "La mañana suena mejor cuando eliges bien, {nombre}.",
    "Tu biblioteca tiene buen material para hoy, {nombre}.",
    "{nombre}, vuelve a lo que estabas escuchando.",
    "Buenos días, {nombre}. Elige el primer tono del día.",
    "Hay una sesión esperando por ti, {nombre}.",
    "{nombre}, tienes favoritos listos para volver a sonar.",
    "Buen día, {nombre}. Tu biblioteca está en orden.",
    "{nombre}, abre la mañana con algo tuyo.",
    "La primera canción puede cambiar el ritmo, {nombre}.",
    "Buenos días, {nombre}. Revisa qué suena mejor ahora.",
]

SALUDOS_TARDE = [
    "Buenas tardes, {nombre}. Tu próxima escucha está cerca.",
    "Pausa musical, {nombre}. Hay mucho por retomar.",
    "Buenas tardes, {nombre}. Dale play a algo que te mueva.",
    "Tu tarde puede seguir con buena música, {nombre}.",
    "Que no decaiga el ritmo, {nombre}.",
    "{nombre}, una buena playlist ordena cualquier tarde.",
    "Tu biblioteca tiene opciones para esta hora, {nombre}.",
    "Hora perfecta para redescubrir favoritos, {nombre}.",
    "Buenas tardes, {nombre}. Dale espacio a una canción distinta.",
    "{nombre}, esta tarde puede sonar con más intención.",
    "{nombre}, vuelve a esas canciones que dejaste a medias.",
    "Tu biblioteca tiene justo lo que necesitas ahora, {nombre}.",
    "Buenas tardes, {nombre}. Hay álbumes que merecen otra vuelta.",
    "{nombre}, elige algo familiar o prueba otra ruta.",
    "La tarde está lista para una sesión corta, {nombre}.",
    "{nombre}, tus artistas frecuentes están esperando.",
]

SALUDOS_NOCHE = [
    "Buenas noches, {nombre}. Hora de escuchar sin prisa.",
    "Buenas noches, {nombre}. Tu música puede bajar el ritmo.",
    "Cierra el día con la canción correcta, {nombre}.",
    "Que suene algo bien elegido esta noche, {nombre}.",
    "Baja el ritmo, {nombre}, y deja que suene tu biblioteca.",
    "{nombre}, esta noche merece una selección fina.",
    "Modo nocturno, {nombre}. Mejor con una selección tranquila.",
    "Buenas noches, {nombre}. El mejor cierre del día empieza con play.",
    "{nombre}, deja que una buena canción haga el resto.",
    "Es tu momento, {nombre}: calma, ritmo y buena música.",
    "Que la noche encuentre una canción precisa, {nombre}.",
    "{nombre}, ponle música a este tramo del día.",
    "Buenas noches, {nombre}. Hay álbumes para escuchar con calma.",
    "{nombre}, vuelve a tus canciones de confianza.",
    "La noche pide una escucha más cuidada, {nombre}.",
    "Buenas noches, {nombre}. Tu biblioteca sigue despierta.",
]

SALUDOS_SIN_NOMBRE = [
    "¿Qué quieres escuchar hoy?",
    "Dale play a algo que acompañe este momento.",
    "Tu próxima canción favorita puede empezar ahora.",
    "Hoy es un gran día para descubrir nueva música.",
    "Tu biblioteca está lista: solo falta que elijas.",
    "Haz que este momento suene mejor.",
    "Explora algo nuevo: una canción puede sorprenderte.",
    "Elige un ritmo y deja que todo encaje.",
    "¿Listo para una sesión que valga la pena?",
    "Pulsa play: aquí empiezan los buenos descubrimientos.",
    "Tu soundtrack de hoy te está esperando.",
    "Una buena canción siempre llega a tiempo.",
    "Dale una oportunidad a ese tema que aún no has escuchado.",
    "Prueba una selección distinta sin salir de tu biblioteca.",
    "Hoy también puede sonar increíble.",
    "Abre la sesión: hay música para cada momento.",
    "Vuelve a lo que estabas escuchando.",
    "Hay favoritos listos para sonar de nuevo.",
    "Tu biblioteca tiene algo para esta hora.",
    "Elige una canción y deja que la sesión avance.",
    "Redescubre un álbum que no escuchas hace rato.",
    "Hay artistas esperando otra vuelta.",
    "Tu música local tiene mucho por mostrar.",
]


def saludo_inicio(nombre_usuario: str | None = None) -> str:
    """Retorna un saludo creativo de inicio, con o sin nombre."""
    nombre = (nombre_usuario or "").strip()
    if not nombre:
        return random.choice(SALUDOS_SIN_NOMBRE)

    hora = datetime.now().hour
    if hora < 12:
        plantilla = random.choice(SALUDOS_MANANA)
    elif hora < 19:
        plantilla = random.choice(SALUDOS_TARDE)
    else:
        plantilla = random.choice(SALUDOS_NOCHE)
    return plantilla.format(nombre=nombre)
