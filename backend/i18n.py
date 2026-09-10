"""
Language support for the advisor (English, French, Arabic).

The UI carries its own string tables (frontend/static/i18n.js); this module
only supplies the instruction that tells the lead agent which language to
answer in, and a small helper the API uses to validate the requested locale.
"""

from __future__ import annotations

SUPPORTED = ("en", "fr", "ar")

LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French (français)",
    "ar": "Arabic (العربية)",
}

_DIRECTIVES = {
    "en": "Write the entire answer in clear English.",
    "fr": "Rédige l'intégralité de la réponse en français clair et professionnel. "
    "Conserve les titres de section suivants, traduits : « Lecture de la situation », "
    "« Ce que disent les données probantes », « Leviers recommandés », "
    "« Réserves et lacunes de données ». Garde les citations tel quel "
    "(p. ex. « Pathways for Peace, 2018, p. 277 »).",
    "ar": "اكتب الإجابة بالكامل باللغة العربية الفصحى الواضحة. "
    "استخدم العناوين التالية مترجمةً: «قراءة الوضع»، «ما تقوله الأدلة»، "
    "«الأدوات الموصى بها»، «التحفّظات والفجوات في البيانات». "
    "أبقِ الاستشهادات المرجعية كما هي بالإنجليزية (مثل: «Pathways for Peace, 2018, p. 277»).",
}


def normalize(lang: str | None) -> str:
    if not lang:
        return "en"
    code = lang.strip().lower()[:2]
    return code if code in SUPPORTED else "en"


def language_directive(lang: str | None) -> str:
    return _DIRECTIVES[normalize(lang)]
