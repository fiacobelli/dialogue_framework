from speech import support_functions as sf
from speech.api_functions import SpeechFunctions
import pyttsx3 as tts
import logging

# Audio recording parameters
STREAMING_LIMIT = sf.STREAMING_LIMIT
SAMPLE_RATE = 16000
CHUNK_SIZE = int(SAMPLE_RATE / 10)  # 100ms

# Used in the termcolor package to make the console display specific colors
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[0;33m'


RATE = 150
VOLUME = 1.0
GENDER = 1 # 0 = male, 1 = female

class SpeechInterface:
    def __init__(self, cloudspeech_fname):
        self.logger = logging.getLogger('__main__.' + __class__.__name__)
        self.is_partial_listen = False
        self.cloudspeech_fname = cloudspeech_fname

    def listen(self):
        api = SpeechFunctions(self.cloudspeech_fname)
        return api.partial_listen()

    def speak(self, reply):
        engine = tts.init()
        engine.setProperty('rate', RATE)
        engine.setProperty('volume', VOLUME)
        # voices = engine.getProperty('voices')
        # print(voices)
        engine.setProperty('voice', "com.apple.speech.synthesis.voice.samantha")

        engine.say(reply)
        engine.runAndWait()
