# This file is configured as SIMILARITY_MODULE = "similarity" in the .env file
# This Similarity class uses language models trained using the gensim library
# gensim trained language models are the default


from gensim.corpora.dictionary import Dictionary
from gensim.models import LsiModel
from gensim import matutils
import re
import logging

class Similarity:
    def __init__(self, model_fname) -> None:
        self.logger = logging.getLogger('__main__.' + __class__.__name__)
        self.model = LsiModel.load('language_models/gensim/resources/' + model_fname)
        self.dictionary =  Dictionary.load('language_models/gensim/resources/dictionary_' + model_fname)  

    def get_words(self, text):
        return re.findall(r'\b\w+\b', text.lower())   

    def similarity(self, s1, s2):
            vec1 = self.model[self.dictionary.doc2bow(self.get_words(s1))]
            vec2 = self.model[self.dictionary.doc2bow(self.get_words(s2))]
            return matutils.cossim(vec1, vec2)


