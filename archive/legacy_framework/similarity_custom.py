# This file is configured as SIMILARITY_MODULE = "similarity_custom" in the .env file
# This Similarity class uses lsa models trained using custom modules
# custom language models are trained on the all-senate_speeches.txt corpus

from language_models.custom.read_model import MatrixModel
from language_models.custom.read_model import SentenceProcessor
import logging

class Similarity:
    def __init__(self, model_filename):
        """
        model_filename contains the relative path of the model name to be used
        Matrix model needs two files: .pkl and .json. Both with the same name.
        pkl, a non-human readable, contains the model as a matrix.
        json, human- readable, contains information about the model generation.
        """
        self.logger = logging.getLogger('__main__.' + __class__.__name__)
        self.sp = SentenceProcessor(MatrixModel(model_filename))

    def similarity(self, real_answer : str, given_answer : str):
        return self.sp.get_sentence_match(real_answer, given_answer)
