from .parsing import Passage


def chunk_passages(passages: list[Passage], size: int = 2400) -> list[Passage]:
    """Keep reference boundaries intact; preserve line offsets for repository files."""
    result = []
    for passage in passages:
        offset = 0
        while offset < len(passage.text):
            end = min(offset + size, len(passage.text))
            if end < len(passage.text):
                boundary = passage.text.rfind(" ", offset + size // 2, end)
                if boundary > offset:
                    end = boundary
            reference = dict(passage.reference)
            if "line_start" in reference:
                reference["line_start"] += passage.text[:offset].count("\n")
                reference["line_end"] = reference["line_start"] + passage.text[offset:end].count(
                    "\n"
                )
            raw = passage.text[offset:end]
            leading = len(raw) - len(raw.lstrip())
            reference["char_start"] = passage.reference.get("char_start", 0) + offset + leading
            reference["char_end"] = reference["char_start"] + len(raw.strip())
            reference["offset_unit"] = "unicode_codepoints"
            text = raw.strip()
            if text:
                result.append(Passage(text, reference))
            offset = end
    if len(result) > 1200:
        raise ValueError("Source exceeds the 1200-chunk limit. Split it into smaller resources.")
    return result
