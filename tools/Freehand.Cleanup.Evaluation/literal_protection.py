"""Protocol mirror of Freehand.Cleanup.LiteralProtectionMask; no dictionary editing."""
import hashlib
import re

MARKER_PREFIX = "[[FREEHAND_LITERAL_"
TOKEN_FAMILY = "FREEHAND_LITERAL_TOKEN_"
TOKEN_SUFFIX = "_END"


class LiteralProtectionMask:
    def __init__(self, masked_text: str, token_prefix: str, blocks: list[str]):
        self.masked_text = masked_text
        self.token_prefix = token_prefix
        self.blocks = tuple(blocks)

    @classmethod
    def create(cls, text: str):
        if TOKEN_FAMILY in text:
            raise ValueError("Transcript contains a reserved cleanup literal identifier")
        prefix = TOKEN_FAMILY + hashlib.sha256(text.encode('utf-8')).hexdigest()[:32] + '_'
        blocks, keys, output = [], set(), []
        scan = copied = 0
        block_start = -1
        open_key = None
        while True:
            start = text.find(MARKER_PREFIX, scan)
            if start < 0:
                break
            body_at = start + len(MARKER_PREFIX)
            end = text.find(']]', body_at)
            if end < 0:
                raise ValueError("A cleanup literal marker is incomplete")
            body = text[body_at:end]
            opening = body.endswith('_START')
            if not opening and not body.endswith('_END'):
                raise ValueError("A cleanup literal marker is malformed")
            key = body[:-6] if opening else body[:-4]
            if not re.fullmatch(r'(?:[0-9a-fA-F]+|[0-9a-fA-F]{32}_[0-9]+)', key):
                raise ValueError("A cleanup literal marker identifier is invalid")
            if opening:
                if open_key is not None or key in keys:
                    raise ValueError("Cleanup literal blocks must be unnested and uniquely named")
                keys.add(key)
                open_key, block_start = key, start
            else:
                if open_key is None or key != open_key:
                    raise ValueError("Cleanup literal blocks are unmatched or out of order")
                output.extend((text[copied:block_start], prefix + str(len(blocks)) + TOKEN_SUFFIX))
                after = end + 2
                blocks.append(text[block_start:after])
                copied, open_key = after, None
            scan = end + 2
        if open_key is not None:
            raise ValueError("A cleanup literal block is incomplete")
        output.append(text[copied:])
        return cls(''.join(output), prefix, blocks)

    def restore(self, edited_text: str) -> str:
        if MARKER_PREFIX in edited_text:
            raise ValueError("Cleanup returned unexpected literal-marker framing")
        output, copied, expected = [], 0, 0
        while True:
            start = edited_text.find(TOKEN_FAMILY, copied)
            if start < 0:
                break
            if not edited_text.startswith(self.token_prefix, start):
                raise ValueError("Cleanup returned an unknown literal identifier")
            digits_at = start + len(self.token_prefix)
            end = digits_at
            while end < len(edited_text) and '0' <= edited_text[end] <= '9':
                end += 1
            digits = edited_text[digits_at:end]
            if (not digits or (len(digits) > 1 and digits[0] == '0') or len(digits) > 10
                    or not edited_text.startswith(TOKEN_SUFFIX, end)):
                raise ValueError("Cleanup changed the protected literal identifiers or their order")
            index = int(digits)
            if index != expected or index >= len(self.blocks):
                raise ValueError("Cleanup changed the protected literal identifiers or their order")
            output.extend((edited_text[copied:start], self.blocks[index]))
            copied, expected = end + len(TOKEN_SUFFIX), expected + 1
        if expected != len(self.blocks):
            raise ValueError("Cleanup removed a protected literal identifier")
        output.append(edited_text[copied:])
        return ''.join(output)
