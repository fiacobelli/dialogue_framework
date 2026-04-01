# Welcome to the Tutoring System wiki!

The Tutoring System is comprised of three modules: Pauses in Voice, Model Generation and Dialogue System. The operation of the overall Tutoring System is covered below in Module integration within Dialogue System.

# Pauses in Voice
While existing transcription systems process user speech following pauses, the Pauses in Voice module allows speakers to speak more completely if their speech is marked by pauses.

The Pauses in Voice module is listed as the speech folder in the main tutoring_system folder and may be run as its own independent project. Pauses in Voice listens for user voice input and provides an array of possible transcriptions. Listening occurs continuously until a pause is detected in the user's speech, at which time estimates are made of the likelihood that the user has finished speaking. For each possible transcription, the Pauses in Voice module generates a maximum likelihood estimate that the pause correlates with the end of a sentence given the words the pause follows. The Pauses in Voice module uses the external module spacy and its own selected corpora to generate a language model. The language model is based on trigrams, or three unit sequences. The units, or grams, are words or any selected punctuation. The maximum likelihood estimate may be seen as an estimate of the likeliness that the pause corresponds to a period (or some other sentence final punctuation), given the two units preceding it.

# Model Generation
The Model Generation module is listed as the nlu_helper folder in the main tutoring_system folder and also may be run as its own independent project. Where the language model in Pauses in Voice looks at pauses and sentence termination, the language model in Model Generation is used to look at the similarity of sentences. The Model Generation module centers around two main tasks: building and saving a language model and reading that model.

To build a language model a matrix is made from the frequency of a word in a document for each document in a corpus. The words are drawn from a bag of words containing all the words in the corpus. The frequency values are further processed using Latent Semantic Analysis. Latent Semantic Analysis is a fully automatic mathematical/statistical technique for extracting and inferring relations of expected contextual usage of words in passages of discourse. LSA yields higher values for words which, though they are different, occur in similar contexts. LSA also yields lower values for different words when they are not used in similar expected contexts. (Should I mention SVD? --DS). The resulting language model needs to be generated just once and is saved to a file for later reading.

Once the language model has been saved, it may be loaded from the file into which it was saved and a MatrixModel object created. This object contains the values for comparing words across documents. The Model Generation module uses these values to generate a similarity score for two sentences presumably not in the original corpus. For each sentence, a vector representation of that sentence is made by looking up the value of each word of that sentence in the MatrixModel object. A similarity score for two sentences is yielded by using those vectors in the Cosine Similarity Formula (explained in OverviewInfoState: Overview of an Information State Dialogue System). 

# Dialogue System
The Dialogue System is comprised of the folders and files of the main tutoring_system folder minus the speech and nlu_helper folders (note: not strictly true--needs rephrasing--DS). The Dialogue System module is covered in detail on the OverviewInfoState page (Overview of an Information State Dialogue System).

# Module integration within Dialogue System

The Dialogue System moves through goals by engaging users by voice in a question and answer dialogue. Goals may be conversational or content related. Conversational goals include greeting the user and terminating the dialogue and content goals are the satisfactory demonstration of knowledge around a topic. For content goals, units and topics are drawn from a file loaded into the Dialogue System's knowledge base. The Dialogue System selects a topic to be completed and a "paragraph" from within that topic. "Paragraphs" constitute the contents of each topic and each paragraph contains a question, a text and keywords drawn from the text (plus any intro/outro texts, alternative questions and alternative texts). 

The Dialogue System asks the user a question retrieved from a paragraph of the selected topic and then awaits the return of input from the Pauses in Voice module. The Pauses in Voice module listens for a user response until a pause is detected and returns an array of possible transcriptions. The Dialogue System then selects the most highly ranked transcription _along with_ the likeliness that that response constitutes a completed sentence (the italicized is a hedge: completeness mle is queried from Pause in Voice separately since we are interested in concatenated texts rather than texts in between pauses --DS). If that likeliness is below a set threshold, that response will be concatenated to the next response and control is sent back to the Pauses in Voice module. If that likeliness is equal to or above that threshold the response is processed.

The processed response is sent to the rules component which returns a message that helps determine what next step to take. If the rules message to continue that processed response is compared to elements of a paragraph.

The processed response is compared to two elements of the paragraph: text and keywords. For keyword comparison, the system checks if there is a match between the keywords for that paragraph and the processed response, i.e., can each keyword be found in the response? The Tutoring System also compares the processed response and the paragraph text to determine a similarity value. The Dialogue System queries the Model Generation module what the Cosine Similarity between the two texts is. The Model Generation module returns a value between 0.0 and 1.0. The Dialogue System stores keyword matches and similarity scores for any given paragraph in the system's information state in order to record user progress. If that similarity value is above or equal to a set threshold and there is a keyword match, the topic for that paragraph is marked as complete and a new topic is selected.

In case there isn't both a keyword match and a sufficiently high similarity score, the user response is compared against the other paragraphs belonging to the same topic from which the original paragraph was drawn. The above process is repeated for each of those paragraphs until the topic can be marked complete. When the topic remains incomplete, the Dialogue System provides feedback and continues to ask questions from the selected topic and passes onto a new topic after a set number of attempts to complete that topic.

Users may quit the dialogue by saying "quit" at any point while the Pauses in Voice module is listening. Control is then sent back to the dialogue system where the rules component detects "quit" in the user response and a message is returned to exit the dialogue. The Dialogue System then speaks a concluding message to the user to end the session and the Tutoring System saves the current information state to a file.


 



  

