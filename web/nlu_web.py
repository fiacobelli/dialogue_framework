from strings import MSG


class NLUWeb:
    """Simplified NLU for web/text chat."""

    def check(self, msg: dict) -> bool:
        """Parse user input and populate message dict with tokens."""
        possible = msg.get(MSG.POSSIBLE_RESPONSES, [])
        if not possible:
            return False
        text = possible[0][1] if isinstance(possible[0], tuple) else possible[0]
        if not text.strip():
            return False
        msg[MSG.ORIG_TEXT] = text
        msg[MSG.ORIG_TEXT_LOWER] = text.lower()
        msg[MSG.TOKENS] = text.lower().split()
        msg['nlu_frame'] = {
            'schema_version': 1,
            'source': 'web_nlu',
            'raw_text': text,
            'normalized_text': msg[MSG.ORIG_TEXT_LOWER],
            'tokens': msg[MSG.TOKENS],
            'turn_meta': msg.get('turn_meta') or {},
        }
        return True
