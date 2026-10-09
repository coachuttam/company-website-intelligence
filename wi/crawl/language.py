"""B-85 (PRD Section 9 "Non-English site: attempt extraction and flag the language", AC-05): a small,
dependency-free guess at whether the text sent to the model is English. Flag only: nothing here
changes which pages are crawled, cleaned or sent, or what is extracted.

How it decides, conservatively:
  - Too little text to judge -> "unknown".
  - Mostly non-Latin letters (Japanese, Chinese, Cyrillic, Arabic ...) -> "non-en".
  - Common English function words make up a normal share of the words -> "en".
  - "non-en" for Latin-script text needs POSITIVE evidence: the function words of Spanish, French,
    German, Portuguese, Italian or Dutch must be common AND clearly outnumber the English ones. A
    mere lack of English function words (an English pricing page that is mostly product names,
    prices or code) gives "unknown", never "non-en".
  - Anything in between -> "unknown".
The thresholds below were set from the test fixtures in tests/test_language.py, not from saved runs.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

EN_WORDS = frozenset(
    "the and of to a in is for with on our your you we that this are be by it as at from or an can "
    "more all will not have has their its about how what when who which into than then also".split()
)
# Short, very common function words that are not also common English words.
OTHER_WORDS = frozenset(
    # Spanish
    "el la los las del que y en un una por para con es se su sus al lo como más pero "
    # French
    "le les des du et est une pour dans sur qui pas vous nous avec sont ce cette au aux "
    # German
    "der die das und ist ein eine mit für auf dem den nicht sie wir ihr zu von im sich auch "
    # Portuguese
    "os da do das dos em não uma com são mais você nosso nossa "
    # Italian
    "il di che è per gli della delle sono non con una "
    # Dutch
    "het een van en voor met zijn niet ook wij uw".split()
) - EN_WORDS

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# Thresholds (see the module docstring and tests/test_language.py).
MIN_WORDS = 40            # fewer words than this (and few letters) is too little to judge
MIN_LETTERS = 200
NON_LATIN_MAX_LATIN = 0.5 # below this share of Latin letters the text is non-English script
EN_MIN_RATIO = 0.10       # share of words that are English function words for a confident "en"
OTHER_MIN_RATIO = 0.10    # share of words that are other-language function words for "non-en"
OTHER_OVER_EN = 1.5       # ...and they must outnumber the English ones by this factor
# How these were chosen, from the fixtures in tests/test_language.py: English prose measures an
# English-word ratio of ~0.38 and other-language ratio 0.0; Spanish/German prose ~0.29-0.32
# other-language and 0.02-0.03 English; English pricing/code pages 0.02-0.06 English and at most
# 0.05 other-language. So 0.10 sits well clear of both groups for each ratio. For mixed text the
# other/English ratio is ~0.84 for an even English/Spanish split and ~1.9 for 3 parts Spanish to 1
# English; 1.5 flags only a clear majority (about two-thirds) of non-English text. (A first value
# of 3.0 missed the 3:1 Spanish fixture; it was re-derived from these measurements, not from runs.)


def _is_latin(ch: str) -> bool:
    return ord(ch) < 0x0250   # Basic Latin through Latin Extended-B


def text_language(text: str) -> Dict[str, object]:
    """Measurements and a guess ("en", "non-en" or "unknown") for one piece of text."""
    text = text or ""
    letters = [ch for ch in text if ch.isalpha()]
    words = [w.lower() for w in _WORD_RE.findall(text)]
    latin = sum(1 for ch in letters if _is_latin(ch)) / len(letters) if letters else 0.0
    en = sum(1 for w in words if w in EN_WORDS) / len(words) if words else 0.0
    other = sum(1 for w in words if w in OTHER_WORDS) / len(words) if words else 0.0
    if len(letters) < MIN_LETTERS:
        guess = "unknown"
    elif latin < NON_LATIN_MAX_LATIN:
        guess = "non-en"
    elif len(words) < MIN_WORDS:
        guess = "unknown"
    elif other >= OTHER_MIN_RATIO and other >= OTHER_OVER_EN * en:
        guess = "non-en"
    elif en >= EN_MIN_RATIO:
        guess = "en"
    else:
        guess = "unknown"
    return {"guess": guess, "words": len(words), "letters": len(letters),
            "latin_ratio": round(latin, 3), "en_ratio": round(en, 3), "other_ratio": round(other, 3)}


def declared_language(html: Optional[str]) -> Optional[str]:
    """The primary code of <html lang="..."> ("es-MX" -> "es"), lowercased, or None."""
    if not html:
        return None
    tag = BeautifulSoup(html, "lxml").find("html")
    lang = (tag.get("lang") or tag.get("xml:lang") or "").strip() if tag else ""
    code = re.split(r"[-_]", lang)[0].lower() if lang else ""
    return code if re.fullmatch(r"[a-z]{2,3}", code) else None


def site_language(texts: List[str], start_html: Optional[str] = None) -> Dict[str, object]:
    """The site-level flag from every page of text sent to the model, weighted by length (the
    texts are judged together). site_language is "en", "unknown", or for non-English text the
    start page's declared <html lang> code when it names a non-English language, else "non-en".
    non_english is true only for a clear "non-en" guess."""
    measured = text_language("\n".join(t for t in texts if t))
    declared = declared_language(start_html)
    if measured["guess"] == "non-en":
        if declared and declared != "en":
            return {"site_language": declared, "site_language_source": "text + html lang",
                    "non_english": True, "measured": measured, "declared_lang": declared}
        return {"site_language": "non-en", "site_language_source": "text",
                "non_english": True, "measured": measured, "declared_lang": declared}
    return {"site_language": measured["guess"], "site_language_source": "text",
            "non_english": False, "measured": measured, "declared_lang": declared}
