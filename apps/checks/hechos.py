"""Verificador determinista de anclaje de hechos (FCT-001)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Iterable

_RULE = "FCT-001"
_SEVERITY = "alta"

_NUMBER_RE = re.compile(r"(?<!\w)\d+(?:[.,]\d+)*(?!\w)")
_NAME_RE = re.compile(
    r"(?<![\wÁÉÍÓÚÜÑáéíóúüñ])"
    r"[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑa-záéíóúüñ'’\-]{1,}"
    r"(?![\wÁÉÍÓÚÜÑáéíóúüñ])"
)

EXCLUSION_POR_DEFECTO: tuple[str, ...] = (
    "El",
    "La",
    "Los",
    "Las",
    "Un",
    "Una",
    "Unos",
    "Unas",
    "Este",
    "Esta",
    "Estos",
    "Estas",
    "Ese",
    "Esa",
    "Esos",
    "Esas",
    "Aquel",
    "Aquella",
    "Aquellos",
    "Aquellas",
    "Su",
    "Sus",
    "Mi",
    "Mis",
    "Tu",
    "Tus",
    "Nuestro",
    "Nuestra",
    "Además",
    "Sin",
    "Pero",
    "Aunque",
    "Cuando",
    "Como",
    "Donde",
    "También",
    "Por",
    "Para",
    "Con",
    "Según",
    "Tras",
    "Entre",
    "No",
    "Sí",
    "Ya",
    "Hoy",
    "Ayer",
    "Mañana",
    "Ahora",
    "Después",
    "Antes",
    "Durante",
    "En",
    "Al",
    "Del",
    "De",
    "Y",
    "O",
    "U",
    "Que",
    "Se",
    "Es",
    "Son",
    "Fue",
    "Hay",
    "Ha",
    "Han",
    "He",
)


def _normalize_number(raw: str) -> str:
    """Devuelve una representación canónica de una cifra."""
    text = raw.strip()
    dot = text.rfind(".")
    comma = text.rfind(",")

    if dot != -1 and comma != -1:
        decimal_separator = "." if dot > comma else ","
        thousands_separator = "," if decimal_separator == "." else "."
        text = text.replace(thousands_separator, "").replace(
            decimal_separator, "."
        )
    elif dot != -1 or comma != -1:
        separator = "." if dot != -1 else ","
        parts = text.split(separator)
        if len(parts) > 2 or (len(parts[-1]) == 3 and len(parts[0]) <= 3):
            text = "".join(parts)
        else:
            text = f"{parts[0]}.{parts[1]}"

    try:
        value = Decimal(text)
    except InvalidOperation:
        return text

    plain = format(value.normalize(), "f")
    if "." in plain:
        plain = plain.rstrip("0").rstrip(".")
    return plain


def _is_sentence_start(text: str, position: int) -> bool:
    """Indica si la entidad empieza una frase, un titular o un elemento."""
    prefix = text[:position].rstrip()
    if not prefix:
        return True

    if prefix[-1] in ".!?;:\n\r\"'«»“”‘’¡¿([{":
        return True

    line_start = text.rfind("\n", 0, position) + 1
    marker = text[line_start:position]
    return not marker.strip() or bool(
        re.fullmatch(r"[#>*+\-–—•\d.)\s]+", marker)
    )


def _extract_names(text: str) -> list[dict]:
    return [
        {
            "tipo": "nombre",
            "valor": match.group(0),
            "normalizado": match.group(0).casefold(),
            "posicion": match.start(),
        }
        for match in _NAME_RE.finditer(text)
    ]


def _extract_numbers(text: str) -> list[dict]:
    return [
        {
            "tipo": "cifra",
            "valor": match.group(0),
            "normalizado": _normalize_number(match.group(0)),
            "posicion": match.start(),
        }
        for match in _NUMBER_RE.finditer(text)
    ]


def anclar_hechos(
    original: str,
    reescrito: str,
    excluir: Iterable[str] | None = None,
) -> dict:
    """Detecta cifras y nombres propios nuevos en la reescritura.

    ``excluir`` es la lista configurable de palabras que no deben bloquear
    cuando aparecen con mayúscula al inicio de una frase. Si se pasa una lista
    vacía, se desactiva el filtro y se marcan todas las entidades nuevas.
    """
    exclusions = (
        {word.strip().casefold() for word in EXCLUSION_POR_DEFECTO}
        if excluir is None
        else {word.strip().casefold() for word in excluir if word.strip()}
    )

    original_names = {
        match.group(0).casefold() for match in _NAME_RE.finditer(original)
    }
    original_numbers = {
        _normalize_number(match.group(0))
        for match in _NUMBER_RE.finditer(original)
    }

    candidates = sorted(
        [*_extract_names(reescrito), *_extract_numbers(reescrito)],
        key=lambda entity: entity["posicion"],
    )

    entities: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for candidate in candidates:
        kind = candidate["tipo"]
        normalized = candidate["normalizado"]

        if kind == "nombre":
            if normalized in original_names:
                continue
            if (
                _is_sentence_start(reescrito, candidate["posicion"])
                and normalized in exclusions
            ):
                continue
        elif normalized in original_numbers:
            continue

        key = (kind, normalized)
        if key in seen:
            continue
        seen.add(key)
        entities.append(candidate)

    blocked = bool(entities)
    return {
        "regla": _RULE,
        "severidad": _SEVERITY if blocked else None,
        "bloquea": blocked,
        "entidades": entities,
        "mensaje": (
            "La reescritura introduce cifras o nombres propios ausentes en el "
            "original."
            if blocked
            else "La reescritura no introduce entidades nuevas."
        ),
        "sugerencia": (
            "Revisa cada entidad nueva y contrástala con una fuente fiable "
            "antes de publicar."
            if blocked
            else ""
        ),
    }
