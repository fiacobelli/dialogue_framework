from strings import MSG


class NLUWeb:
    """Minimal NLU for web/text chat: extract the user's text. The LLM does the understanding."""

    def __init__(self, info_state=None, llm_provider=None):
        self.info_state = info_state
        self.llm_provider = llm_provider

    def check(self, msg: dict) -> bool:
        """Parse user input and populate the message dict with the raw text."""
        possible = msg.get(MSG.POSSIBLE_RESPONSES, [])
        if not possible:
            return False
        text = possible[0][1] if isinstance(possible[0], tuple) else possible[0]
        if not text.strip():
            return False
        msg[MSG.ORIG_TEXT] = text
        msg[MSG.ORIG_TEXT_LOWER] = text.lower()
        msg[MSG.TOKENS] = text.lower().split()
        return True
