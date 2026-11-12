"""Comprobaciones SEO deterministas, sin llamadas a modelos."""

from __future__ import annotations

import re

_SEVERIDAD = "alta"

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_H1_MARKDOWN_RE = re.compile(r"^\s{0,3}#[ \t]+\S", re.MULTILINE)
_H1_HTML_RE = re.compile(r"<h1\b[^>]*>", re.IGNORECASE)
_WORD_RE = re.compile(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]*")

_VOWELS = "aeiouáéíóúü"
_STRONG_VOWELS = "aeoáéó"
_ACCENTED_WEAK_VOWELS = "íú"

_STOPWORDS = {
    "a",
    "al",
    "algo",
    "ante",
    "como",
    "con",
    "contra",
    "cual",
    "cuando",
    "de",
    "del",
    "desde",
    "donde",
    "el",
    "ella",
    "ellas",
    "ellos",
    "en",
    "entre",
    "era",
    "es",
    "esa",
    "ese",
    "eso",
    "esta",
    "este",
    "esto",
    "fue",
    "ha",
    "hasta",
    "la",
    "las",
    "lo",
    "los",
    "más",
    "me",
    "mi",
    "mis",
    "no",
    "o",
    "para",
    "pero",
    "por",
    "que",
    "se",
    "sin",
    "sobre",
    "son",
    "su",
    "sus",
    "también",
    "te",
    "tu",
    "tus",
    "un",
    "una",
    "uno",
    "unos",
    "unas",
    "y",
    "ya",
}


def _count_syllables(word: str) -> int:
    """Cuenta núcleos vocálicos con una heurística para español."""
    word = word.lower()
    total = 0
    index = 0
    while index < len(word):
        if word[index] not in _VOWELS:
            index += 1
            continue

        total += 1
        cursor = index
        while cursor + 1 < len(word) and word[cursor + 1] in _VOWELS:
            current = word[cursor]
            following = word[cursor + 1]
            if (
                current in _ACCENTED_WEAK_VOWELS
                or following in _ACCENTED_WEAK_VOWELS
            ):
                break
            if current in _STRONG_VOWELS and following in _STRONG_VOWELS:
                break
            cursor += 1
        index = cursor + 1
    return total


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def _split_sentences(text: str) -> list[str]:
    return [
        match.group(0).strip()
        for match in _SENTENCE_RE.finditer(text)
        if match.group(0).strip()
    ]


def _inflesz_score(text: str) -> float:
    """Aproxima el índice INFLESZ (Szigriszt-Pazos) del texto."""
    words = _WORD_RE.findall(text)
    sentences = _split_sentences(text)
    if not words or not sentences:
        return 0.0

    syllables = sum(_count_syllables(word) for word in words)
    syllables_per_100 = syllables / len(words) * 100
    sentences_per_100 = len(sentences) / len(words) * 100
    return round(206.84 - 0.60 * syllables_per_100 - 1.02 * sentences_per_100, 2)


def _keyword_density(text: str, keyword: str) -> float:
    words = _WORD_RE.findall(text)
    if not words:
        return 0.0

    parts = [re.escape(part) for part in keyword.lower().split()]
    pattern = re.compile(
        r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)",
        re.IGNORECASE,
    )
    occurrences = len(pattern.findall(text))
    return occurrences / len(words) * 100


def _problem(rule: str, message: str, suggestion: str) -> dict:
    return {
        "regla": rule,
        "severidad": _SEVERIDAD,
        "mensaje": message,
        "sugerencia": suggestion,
    }


def verificar_seo(
    titulo: str,
    meta: str,
    slug: str,
    texto: str,
    keyword: str,
) -> list[dict]:
    """Devuelve los problemas SEO del contenido, sin usar modelos."""
    problems: list[dict] = []
    title_length = len(titulo.strip())
    meta_length = len(meta.strip())

    if title_length > 60:
        problems.append(
            _problem(
                "SEO-001",
                f"El título tiene {title_length} caracteres; el máximo es 60.",
                "Acorta el título sin perder la keyword principal.",
            )
        )

    if not 140 <= meta_length <= 155:
        problems.append(
            _problem(
                "SEO-002",
                (
                    f"La meta descripción tiene {meta_length} caracteres; "
                    "debe tener entre 140 y 155."
                ),
                "Ajusta la meta descripción al rango de 140 a 155 caracteres.",
            )
        )

    h1_count = len(_H1_MARKDOWN_RE.findall(texto)) + len(
        _H1_HTML_RE.findall(texto)
    )
    if h1_count != 1:
        problems.append(
            _problem(
                "SEO-003",
                f"Se encontraron {h1_count} etiquetas H1; debe haber exactamente una.",
                "Deja un solo H1 y usa H2 o H3 para el resto de secciones.",
            )
        )

    if not slug:
        problems.append(
            _problem(
                "SEO-004",
                "El slug está vacío.",
                "Usa minúsculas, guiones y elimina las palabras vacías.",
            )
        )
    else:
        if slug != slug.lower():
            problems.append(
                _problem(
                    "SEO-004",
                    "El slug debe estar en minúsculas.",
                    "Usa minúsculas, guiones y elimina las palabras vacías.",
                )
            )
        if len(slug) > 60:
            problems.append(
                _problem(
                    "SEO-004",
                    f"El slug tiene {len(slug)} caracteres; el máximo es 60.",
                    "Acorta el slug manteniendo la keyword principal.",
                )
            )
        tokens = [token for token in slug.split("-") if token]
        stopwords = sorted({token for token in tokens if token in _STOPWORDS})
        if stopwords:
            problems.append(
                _problem(
                    "SEO-004",
                    "El slug contiene palabras vacías: " + ", ".join(stopwords) + ".",
                    "Elimina las palabras vacías del slug.",
                )
            )
        if slug == slug.lower() and not _SLUG_RE.fullmatch(slug):
            problems.append(
                _problem(
                    "SEO-004",
                    "El slug contiene caracteres no permitidos.",
                    "Usa solo minúsculas, números y guiones simples.",
                )
            )

    keyword = keyword.strip()
    if not keyword:
        problems.append(
            _problem(
                "SEO-005",
                "La keyword principal está vacía.",
                "Indica la keyword principal del contenido.",
            )
        )
    elif _word_count(texto) == 0:
        problems.append(
            _problem(
                "SEO-005",
                "El texto no tiene palabras para calcular la densidad.",
                "Añade contenido antes de comprobar la densidad.",
            )
        )
    else:
        density = _keyword_density(texto, keyword)
        if density < 0.5 or density > 2.0:
            problems.append(
                _problem(
                    "SEO-005",
                    (
                        f"La densidad de '{keyword}' es {density:.2f}%; "
                        "debe estar entre 0,5% y 2%."
                    ),
                    "Ajusta las menciones de la keyword principal.",
                )
            )

    score = _inflesz_score(texto)
    if score < 55:
        problems.append(
            _problem(
                "SEO-006",
                f"El índice INFLESZ es {score:.2f}; debe ser igual o mayor a 55.",
                "Acorta las frases y usa palabras más sencillas.",
            )
        )

    return problems
