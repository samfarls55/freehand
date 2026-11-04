"""Mirror of Freehand.Cleanup.SpecialistLiteralMask, protocols compact-v2/v3/v4.

This protects exact Core literal blocks and paired quoted wording. It does not
correct language or decide which words are meaningful. Native results retain
both the model's raw identifiers and the strictly restored application text.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

from literal_protection import LiteralProtectionMask, TOKEN_SUFFIX


TOKEN_FAMILY = "FHX_"
PROTOCOL = "specialist-compact-v3"
SINGLE_QUOTE_PROTOCOL = "specialist-compact-v4"


def _trim_end_length(text: str) -> int:
    """Match .NET char.IsWhiteSpace rather than Python's extra C0 separators."""
    end = len(text)
    while end > 0 and (text[end - 1] in "\t\n\v\f\r\x85"
                       or unicodedata.category(text[end - 1]) in ("Zs", "Zl", "Zp")):
        end -= 1
    return end


def _escaped(text: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def _quote_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    opening = None
    closing = None
    for index, character in enumerate(text):
        if character not in ('"', '“', '”') or _escaped(text, index):
            continue
        if opening is not None:
            if character == closing:
                spans.append((opening, index + 1))
                opening = closing = None
        elif character in ('"', '“'):
            opening = index
            closing = '"' if character == '"' else '”'
    return spans


def _word_at(text: str, index: int) -> bool:
    if not 0 <= index < len(text):
        return False
    # The new table is loaded only on the explicit v4 path, never for v3.
    from specialist_literal_word_ranges import is_word
    return is_word(ord(text[index]))


def _quote_spans_v4(text: str) -> list[tuple[int, int]]:
    spans, closing = [], []
    opening = -1
    paired_single_families = bare_possessive_families = 0
    leading_elision_families = 0

    def push(character):
        if len(closing) >= 64:
            raise ValueError("Specialist literal v4 quote nesting is too deep")
        closing.append(character)

    for index, character in enumerate(text):
        if character not in ('"', '“', '”', "'", '‘', '’') or _escaped(text, index):
            continue
        single = character in ("'", '‘', '’')
        before, after = _word_at(text, index - 1), _word_at(text, index + 1)
        if single and before and after:
            continue
        if character in ("'", '’') and not before and _leading_elision(text, index):
            if not closing:
                leading_elision_families |= 1 if character == "'" else 2
            continue
        if closing and character == closing[-1]:
            if character in ('"', "'") and not before and after:
                push(character)
                continue
            closing.pop()
            if single:
                paired_single_families |= 1 if character == "'" else 2
            if not closing:
                spans.append((opening, index + 1))
            continue
        if character in ('”', '’'):
            if character == '’' and before and '’' not in closing:
                if not closing and _ambiguous_terminal_apostrophe(text, index):
                    bare_possessive_families |= 2
                continue
            raise ValueError("Specialist literal v4 found unmatched or crossing quote delimiters")
        if character == "'" and before:
            if not closing and _ambiguous_terminal_apostrophe(text, index):
                bare_possessive_families |= 1
            continue
        if not closing:
            opening = index
        push({'“': '”', '‘': '’'}.get(character, character))
    if closing or (paired_single_families | leading_elision_families) & bare_possessive_families:
        raise ValueError("Specialist literal v4 found an unmatched or ambiguous quote boundary")
    return spans


def _leading_elision(text: str, index: int) -> bool:
    end = index + 1
    while _word_at(text, end):
        end += 1
    if end < len(text) and text[end] == text[index]:
        return False
    word = text[index + 1:end]
    return word.isascii() and word.lower() in ('cause', 'em', 'tis')


def _ambiguous_terminal_apostrophe(text: str, index: int) -> bool:
    suffix = text[max(0, index - 2):index]
    if suffix.isascii() and suffix.lower() == 'in':
        return False
    after = index + 1
    while after < len(text) and (text[after] in "\t\n\v\f\r\x85"
                               or unicodedata.category(text[after]) in ('Zs', 'Zl', 'Zp')):
        after += 1
    return not _word_at(text, after)


class SpecialistLiteralMask:
    def __init__(self, masked_text: str, legacy: LiteralProtectionMask,
                 tokens: list[str], payloads: list[str], terminal_quote_token: str | None = None):
        self.masked_text = masked_text
        self.legacy = legacy
        self.tokens = tuple(tokens)
        self.payloads = tuple(payloads)
        self.terminal_quote_token = terminal_quote_token

    @classmethod
    def create(cls, text: str, remove_added_quote_period: bool = True, *, protocol: str = PROTOCOL):
        if protocol not in (PROTOCOL, SINGLE_QUOTE_PROTOCOL):
            raise ValueError("Unsupported specialist literal protocol")
        if protocol == SINGLE_QUOTE_PROTOCOL:
            if remove_added_quote_period is not True:
                raise ValueError("Specialist literal v4 includes terminal quote normalization")
            # Reject lone surrogates instead of inventing replacement bytes.
            text.encode("utf-8")
        if TOKEN_FAMILY in text:
            raise ValueError("Transcript contains a reserved specialist literal identifier")
        legacy = LiteralProtectionMask.create(text)
        source = legacy.masked_text
        quote_spans = _quote_spans_v4(source) if protocol == SINGLE_QUOTE_PROTOCOL else _quote_spans(source)
        quote_index = 0
        terminal_quote_token = None
        literal = re.compile(re.escape(legacy.token_prefix) + r"[0-9]+" + re.escape(TOKEN_SUFFIX))
        output, tokens, payloads = [], [], []
        known = set()
        scan = 0

        def protect(payload: str) -> str:
            nonce = 0
            while True:
                token = TOKEN_FAMILY + hashlib.sha256(
                    f"{len(tokens)}:{nonce}:{payload}".encode("utf-8")).hexdigest()[:8]
                if token not in known:
                    break
                nonce += 1
            known.add(token)
            tokens.append(token)
            payloads.append(payload)
            return token

        while scan < len(source):
            if quote_index < len(quote_spans) and quote_spans[quote_index][0] == scan:
                _, end = quote_spans[quote_index]
                payload = source[scan:end]
                token = protect(payload)
                output.append(token)
                if (remove_added_quote_period and end == _trim_end_length(source)
                        and len(payload) >= 2 and payload[-2] in ".?!"
                        and not (payload[-2] == "." and len(payload) >= 3 and payload[-3] == ".")):
                    terminal_quote_token = token
                scan = end
                quote_index += 1
                continue
            match = literal.match(source, scan)
            if match is not None:
                output.append(protect(match.group()))
                scan = match.end()
                continue
            output.append(source[scan])
            scan += 1
        return cls("".join(output), legacy, tokens, payloads, terminal_quote_token)

    def restore(self, edited_text: str) -> str:
        if self.terminal_quote_token is not None:
            end = _trim_end_length(edited_text)
            if edited_text[:end].endswith(self.terminal_quote_token + "."):
                edited_text = edited_text[:end - 1] + edited_text[end:]
        output = []
        copied = expected = 0
        while True:
            start = edited_text.find(TOKEN_FAMILY, copied)
            if start < 0:
                break
            if expected >= len(self.tokens) or not edited_text.startswith(self.tokens[expected], start):
                raise ValueError("Cleanup changed the specialist literal identifiers or their order")
            output.extend((edited_text[copied:start], self.payloads[expected]))
            copied = start + len(self.tokens[expected])
            expected += 1
        if expected != len(self.tokens):
            raise ValueError("Cleanup removed a specialist literal identifier")
        output.append(edited_text[copied:])
        return self.legacy.restore("".join(output))
