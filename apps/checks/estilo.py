"""Aplicación determinista de las reglas de docs/estilo.md."""

from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path

_RULES_PATH = Path(__file__).resolve().parents[2] / "docs" / "estilo.md"

_SECTION_RE = re.compile(
    r"^##\s+(EST-\d+)[^\n]*\n(.*?)(?=^##\s+|\Z)",
    re.MULTILINE | re.DOTALL,
)
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]*")
_WORD_RE = re.compile(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")

_TITLE_STOPWORDS = {
    "a",
    "al",
    "como",
    "con",
    "de",
    "del",
    "el",
    "en",
    "es",
    "la",
    "las",
    "le",
    "les",
    "lo",
    "los",
    "más",
    "o",
    "para",
    "por",
    "que",
    "se",
    "sin",
    "sobre",
    "son",
    "su",
    "sus",
    "u",
    "un",
    "una",
    "unas",
    "unos",
    "y",
}

_GENERIC_CLOSINGS = (
    "en conclusión",
    "en resumen",
    "en definitiva",
    "en general",
    "sin duda",
    "por todo ello",
    "a modo de cierre",
)


def _section_bodies(markdown: str) -> dict[str, str]:
    return {
        match.group(1): match.group(2)
        for match in _SECTION_RE.finditer(markdown)
    }


def _parse_word_list(body: str) -> list[str]:
    lines = body.splitlines()
    intro = next(
        (index for index, line in enumerate(lines) if line.rstrip().endswith(":")),
        None,
    )
    if intro is None:
        remaining = lines
    else:
        remaining = [lines[intro].split(":", 1)[1], *lines[intro + 1:]]

    words = re.split(r"[,\n]+", "\n".join(remaining))
    return [word.strip().lower() for word in words if word.strip()]


def _parse_phrase_list(body: str) -> list[str]:
    return [
        line.strip()[2:]
        for line in body.splitlines()
        if line.strip().startswith("- ")
    ]


def _parse_quote_chars(body: str) -> list[str]:
    chars: list[str] = []
    for code in re.findall(r"U\+([0-9A-Fa-f]{4,6})", body):
        char = chr(int(code, 16))
        if char not in chars:
            chars.append(char)
    return chars or ["\u201c", "\u201d", "\u2018", "\u2019"]


def _parse_int(body: str, pattern: str, default: int) -> int:
    match = re.search(pattern, body, re.IGNORECASE)
    return int(match.group(1)) if match else default


@lru_cache(maxsize=8)
def cargar_reglas(ruta: str | Path | None = None) -> dict:
    """Carga las listas y umbrales desde docs/estilo.md."""
    path = Path(ruta) if ruta is not None else _RULES_PATH
    markdown = path.read_text(encoding="utf-8")
    sections = _section_bodies(markdown)

    return {
        "palabras_vetadas": _parse_word_list(sections.get("EST-001", "")),
        "frases_vetadas": _parse_phrase_list(sections.get("EST-002", "")),
        "comillas_curvas": _parse_quote_chars(sections.get("EST-003", "")),
        "parrafo_max_palabras": _parse_int(
            sections.get("EST-006", ""),
            r"Párrafos de más de\s+(\d+)\s+palabras",
            70,
        ),
        "frase_max_palabras": _parse_int(
            sections.get("EST-006", ""),
            r"Frases de más de\s+(\d+)\s+palabras",
            40,
        ),
        "diferencia_parrafos": _parse_int(
            sections.get("EST-006", ""),
            r"diferencia menor al\s+(\d+)%",
            15,
        ),
        "negritas_max": _parse_int(
            sections.get("EST-005", ""),
            r"Más de\s+(\d+)\s+negritas",
            2,
        ),
        "negritas_por_palabras": _parse_int(
            sections.get("EST-005", ""),
            r"por cada\s+(\d+)\s+palabras",
            300,
        ),
    }


def _problem(
    rule: str,
    severity: str,
    position: int,
    message: str,
    suggestion: str,
) -> dict:
    return {
        "regla": rule,
        "severidad": severity,
        "posicion": position,
        "mensaje": message,
        "sugerencia": suggestion,
    }


def _normalize_preserving_length(text: str) -> str:
    return "".join(
        " " if char in "\r\n\t" else char.lower()
        for char in text
    )


def _paragraphs(text: str) -> list[tuple[int, str]]:
    paragraphs: list[tuple[int, str]] = []
    offset = 0
    for part in re.split(r"(\n[ \t]*\n)", text):
        if part and not re.fullmatch(r"\n[ \t]*\n", part):
            content = part.strip()
            if content:
                start = offset + part.find(content)
                paragraphs.append((start, content))
        offset += len(part)
    return paragraphs


def verificar_estilo(texto: str) -> list[dict]:
    """Aplica las reglas de docs/estilo.md y devuelve los problemas."""
    rules = cargar_reglas()
    problems: list[dict] = []

    for word in rules["palabras_vetadas"]:
        pattern = re.compile(rf"(?<!\w){re.escape(word)}(?!\w)", re.IGNORECASE)
        for match in pattern.finditer(texto):
            problems.append(
                _problem(
                    "EST-001",
                    "alta",
                    match.start(),
                    f'Palabra vetada: "{word}".',
                    "Sustituye la palabra por un término concreto.",
                )
            )

    normalized = _normalize_preserving_length(texto)
    for expression in rules["frases_vetadas"]:
        pattern = re.compile(expression, re.IGNORECASE)
        for match in pattern.finditer(normalized):
            problems.append(
                _problem(
                    "EST-002",
                    "alta",
                    match.start(),
                    f'Frase vetada: "{match.group(0).strip()}".',
                    "Reescribe la frase con una formulación directa.",
                )
            )

    for quote in rules["comillas_curvas"]:
        start = 0
        while True:
            position = texto.find(quote, start)
            if position == -1:
                break
            problems.append(
                _problem(
                    "EST-003",
                    "alta",
                    position,
                    f"Comilla curva U+{ord(quote):04X} detectada.",
                    "Sustitúyela por una comilla recta.",
                )
            )
            start = position + 1

    for match in _SENTENCE_RE.finditer(texto):
        sentence = match.group(0)
        if sentence.count(",") == 2 and re.search(r"\by\b", sentence, re.IGNORECASE):
            problems.append(
                _problem(
                    "EST-004",
                    "media",
                    match.start(),
                    "Posible enumeración de tres elementos.",
                    "Comprueba si los tres elementos son necesarios o reescribe la enumeración.",
                )
            )

    for match in re.finditer(
        r"^[ \t]*[-*+][ \t]+\*\*[^*\n]+\*\*[ \t]*:",
        texto,
        re.MULTILINE,
    ):
        problems.append(
            _problem(
                "EST-005",
                "media",
                match.start(),
                "Elemento de lista con negrita y dos puntos.",
                "Reescribe el elemento como una frase normal.",
            )
        )

    for match in re.finditer(r"^#{2,6}[ \t]+(.+?)[ \t]*$", texto, re.MULTILINE):
        heading = match.group(1)
        words = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", heading)
        lowercase_words = [
            word
            for word in words
            if word.lower() not in _TITLE_STOPWORDS and not word[0].isupper()
        ]
        if lowercase_words:
            problems.append(
                _problem(
                    "EST-005",
                    "media",
                    match.start(),
                    f'Subtítulo sin Title Case: "{heading}".',
                    "Escribe con mayúscula inicial las palabras principales del subtítulo.",
                )
            )

    word_count = len(_WORD_RE.findall(texto))
    bold_matches = list(re.finditer(r"\*\*[^*\n]+\*\*", texto))
    allowed_bold = max(
        1, math.ceil(word_count / rules["negritas_por_palabras"])
    ) * rules["negritas_max"]
    if len(bold_matches) > allowed_bold:
        problems.append(
            _problem(
                "EST-005",
                "media",
                bold_matches[allowed_bold].start(),
                (
                    f"Hay {len(bold_matches)} negritas; el máximo para "
                    f"{word_count} palabras es {allowed_bold}."
                ),
                "Reduce el uso de negritas.",
            )
        )

    for match in re.finditer(
        r"^[ \t]*(?:en conclusión|en resumen)\b",
        texto,
        re.MULTILINE | re.IGNORECASE,
    ):
        problems.append(
            _problem(
                "EST-005",
                "media",
                match.start(),
                f'Cierre vetado: "{match.group(0).strip()}".',
                "Termina con una idea concreta en lugar de una fórmula de cierre.",
            )
        )

    paragraphs = _paragraphs(texto)
    paragraph_counts = [
        len(_WORD_RE.findall(content)) for _, content in paragraphs
    ]
    for (position, _), count in zip(paragraphs, paragraph_counts):
        if count > rules["parrafo_max_palabras"]:
            problems.append(
                _problem(
                    "EST-006",
                    "baja",
                    position,
                    (
                        f"Párrafo de {count} palabras; el máximo es "
                        f"{rules['parrafo_max_palabras']}."
                    ),
                    "Divide el párrafo en bloques más cortos.",
                )
            )

    for index in range(len(paragraph_counts) - 2):
        window = paragraph_counts[index:index + 3]
        largest = max(window)
        smallest = min(window)
        if largest > 0 and (largest - smallest) / largest < (
            rules["diferencia_parrafos"] / 100
        ):
            problems.append(
                _problem(
                    "EST-006",
                    "baja",
                    paragraphs[index][0],
                    "Tres párrafos consecutivos tienen longitudes muy parecidas.",
                    "Varía la extensión de los párrafos.",
                )
            )

    for match in _SENTENCE_RE.finditer(texto):
        count = len(_WORD_RE.findall(match.group(0)))
        if count > rules["frase_max_palabras"]:
            problems.append(
                _problem(
                    "EST-006",
                    "baja",
                    match.start(),
                    (
                        f"Frase de {count} palabras; el máximo es "
                        f"{rules['frase_max_palabras']}."
                    ),
                    "Acorta la frase.",
                )
            )

    if paragraphs:
        final_position, final_content = paragraphs[-1]
        final_sentences = [
            match.group(0).strip()
            for match in _SENTENCE_RE.finditer(final_content)
            if match.group(0).strip()
        ]
        if len(final_sentences) == 1 and final_sentences[0].lower().startswith(
            _GENERIC_CLOSINGS
        ):
            problems.append(
                _problem(
                    "EST-006",
                    "baja",
                    final_position,
                    "El párrafo final es una sola frase genérica.",
                    "Cierra con una idea concreta y verificable.",
                )
            )

    problems.sort(key=lambda problem: (problem["posicion"], problem["regla"]))
    return problems
