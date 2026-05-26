from speech.estimate_functions import MaximumLikelihoodEstimate

mle = MaximumLikelihoodEstimate()
print(mle.mle("My cat is white"))
print(mle.mle("my cat is white as"))