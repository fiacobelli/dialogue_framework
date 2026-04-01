# Overview of an Information State Dialogue System

A Dialogue system is the core of this project. This system listens to the user, processes the input and generates the response on the basis of the state of the conversation. It should create a proper conversation and continue it until the user want to end it.

At its most basic level, a dialogue system consists of a Natural language understanding module (NLU), a dialogue manager (DM), and a natural language generation (NLG) module. Perhaps a speech interface is hooked to the NLU, the user speaks, the message is transcribed and passed to the DM, the system plans a response and gives the NLG a plan of what to say. Then the NLG, connected to a TTS device may speak the response. 

For example, an Alexa/Google home may be connected for both speech detection and production.

A dialogue manager can have many architectures. In this project we use Traum and Larssen's 2003 Information State architecture.

The architecture of dialogue system is comprised of different modules. They interact with each other to receive the input, process it and send the response. It is based on the information state dialogue system (Traum and Larsson, 2003) The modules are as follows :

![Dialog system architecture](https://github.com/fiacobelli/tutoring_system/blob/main/resources/docs/dialogueSystem.png)

### Natural Language Understanding (NLU) 
When a user asks a query, it is converted to text by Google Home and it is received by the dialogue system as text input. The NLU module processes the input received by the dialog system. It applies various custom filters such as stemmer, stop-word removal, etc. 
Rules
This module defines and applies different rules on text input. The rules define the action to be taken at a particular point of conversation. There can be several rules in a conversation. For example, there can be a rule that conversation will start after the dialogue system greets the user and user greets the dialogue system in reply. The other rule can specify when the conversation should end. For example, conversation should be ended if user said “Goodbye”.
          
### Information State (IS)
This module stores the important information and current state of the dialogue.There are two types of information stored - Beliefs (IS.Beliefs) and Common Ground (IS.CommonGround). Beliefs are bits of information that the system believes to be true. For example, the mood of the interlocutor. Common Ground are facts established throughout the dialogue. For example, the name of a person. 
Goals

A conversation can have several *goals*. For example, greeting the user, then convince the user to do something, and finally end the conversation politely. Within each goal there might be several *tasks*. For example: If we have a goal to book a flight, then there can be tasks such as extract the time and destination of flight, to ask if it is a round trip or one way trip etc. Each of these tasks need to be accomplished to achieve the goal of booking the flight.

### Natural Language Generation(NLG)
This module applies custom filters on information that is internal to the dialogue system, in order to generate a textual response that can be understood by the user.

### Dialogue Manager (DM)
This module is the coordinator between the other modules. It passes a textual message to the NLU. Once the NLU completes filtering it, the DM passes the results of this filtering  to the Rules module. Once the rules are processed, information is stored in the IS. Then the DM activates the appropriate Goal and generates the appropriate response. Lastly the DM passes this response to the NLG module to produce the final utterance from the dialogue. See Figure 1


## Understanding the architecture with an Example
Consider the following dialogue:

User: Why is my arm swollen
System: If you experience swelling, please contact your doctor. It could be lymphedema.

#### Understanding the user input
Initially, the DM is listening for user input. When this input arrives (Why is my arm swelling) the DM passes it to the NLU module. The NLU module applies filters and extracts information from this text input. There can be different filters applied to this input. For example, stemming -- which is to reduce the words to their root form (why is my arm swell) . Then a Message object (Figure 2, box (a) ) with the original input and the stemmed input is created and passed to the DM. 
Next, the DM passes this Message object (Figure 2, box (b) ) to the Rules module which applies custom rules (Figure 2, box (c) ) to it and saves the output to the IS module as key-value pairs. A simple rule could be as follows:

If (Message.input = “Bye”) then add {intention:end} to IS.CommonGround.

In the current implementation we have defined two rules to be processed: First, a rule to determine whether the user wants to end a conversation (adding {done:yes} to the IS.CommonGround) and the Second rule checks whether the user is asking a regular question. If true, then {query:yes} is added to the  IS.CommonGround. See Figure 2.

![Processing Input](https://github.com/fiacobelli/tutoring_system/blob/main/resources/docs/processInput.png)
Figure 2. Processing and understanding of the utterance: “Why is my arm swelling?” and storing important information in the Information State.

The system has now understood the user input. We should now generate the response for it.
#### Generating a reply:
After the rules are applied and information state is updated, DM calls the Goal module to activate the goal. In the current implementation we have one goal which is to reply the user based on the input message. There are two tasks to be completed to achieve this goal - to greet the user and ask for the query(AskQuestionTask) and to answer the question of user(AnswerTask). They are activated on the basis of information state. We can set various conditions such as:

if(IS.CommonGround:query = “No”) then activate GreetTask

if(IS.CommonGround:query = “Yes” and IS.CommonGround:done = “No”) then activate AnswerTask

In our example user has asked a question, therefore our task is to get the answer for this question. Therefore AnswerTask is activated and it applies natural language processing algorithms on the Message object and retrieve the most appropriate answer. The Message object is updated to hold the reply and is passed to the DM which then passes it to NLG module. See Figure 3
                                                                                                                                       
![check goals and tasks and generate response](https://github.com/fiacobelli/tutoring_system/blob/main/resources/docs/checkGoalsAndGenReply.png)
Figure 3. Generating the reply for the question by the task GetAnswerTask of Goal module, based on the information state

NLG module applies custom filter to formulate the text response from the Message.This response is sent to the Google Home assistant which converts this text to speech and speaks to the user.



## Objects of Dialog System

![Objects of the dialogue system](https://github.com/fiacobelli/tutoring_system/blob/main/resources/docs/finalObjects.png)

Figure 4. Objects of Dialogue System

Dialog system is developed using Object Oriented Programming. The important objects are :

### Message
The constructor of this class receives text as input. It has methods getProperty() and setProperty() which are like hashmap/properties object.The other methods is getMessageText(), which gets the message text in String form.

### MessageFilter
NLU passes message through MessageFilter.This class extend Filter class. There can be several message filters based on the application.They have processFilter(Message) method which processes the message.We have used StemmerFilter which applies the stemming algorithm and converts message text to stemmed text.

### Rules 
We can override this class to write our own rules. It has access to the information state variables.It has a process() method which we can override and it processes the rules written in the class. We have used BCRules class which extend the Rules class. The rules are implemented using methods findQuestion(text) and isDone(text).

### Information state
Every time *DM* calls the *Rules* are processed *DM* asks the *InformationState* to update the variables like commonGround and conversationBeliefs.

### Goals
Each goal has access to InformationState variables. It also has init() method which initializes variables and set different tasks to the goal. We have two tasks in our application. First is the AskQuestion Task which is activated at the start of the conversation. It updates the Information State variable (IS.outfield) to hold the text message from the dialogue system which requests the user to ask the query. Second task is the GetAnswer Task which is activated once the user has asked the question. This task calls the Cosine Similarity algorithm to find the appropriate answer. It updates the Information State variable (IS.outfield) to hold the answer.
  Goals also has update() and getConfidence() methods which updates the goal if needed and give the confidence level of the goal which is the priority score of that goal. We have only 1 goal and hence the confidence is set to 1.It has the method createMessage() which updates the response property of message text according to IS.outfield and create a reply.This message is sent to NLG.

NLG receives this message and it applies the filter to format the message and formulate the response.

## Cosine Similarity 
Cosine similarity is an important concept which measures the similarity between two non-zero vectors. It calculates the cosine of the angle between them. The cosine of 0° is 1, and it is less than 1 for any other angle. Vectors have both magnitude and orientation but cosine similarity judges only the orientation. The angle between two vectors in the same direction is 0° and have  a cosine similarity of 1, two vectors at 90° have a similarity of 0, and two vectors diametrically opposed have a similarity of -1, independent of their magnitude.
The formula to find Cosine Similarity between to 2 vectors is :

cos(a,b) =  ab||a|| ||b||

where, 
a∙b = x=1naxbx
||a|| is the length of the vector a = x=1naₓ²


Cosine similarity is used in the project to find the similarity between the User’s query and potential Question/Answers(reply) present in the JSON file for dialogue system. Both query and the reply are considered as the documents. Two documents are similar if they have some of the same terms. But there are some terms that are common in almost of the documents, for eg. words like is, the etc. So we cannot rely on these terms to get the similarity between documents. To resolve this issue, there are few important concepts that help in finding the similarity. These concepts are :

Term Frequency (TF) : This measures how frequently a term appears in a document. It is basically the number of times a term is present in the document. Since every document differs in the length, it is possible that a term is present more times in a longer document than the short ones. Therefore term frequency is mostly divided the document length for the normalization. 

Example 1
If a document is -  I have blurred vision
Term Frequency of word “have” will be calculated as :
Number of times “have” appear in the document = 1
Total number of words in the document = 4
Term Frequency = ¼ = 0.25
The below table gives the Term Frequency of all the terms in above document.

Term
I
have
blurred
vision
Term Frequency
0.25
0.25
0.25
0.25


Document Frequency (DF) : This measures the number of documents in a set where any given term t appears. For example if we have 3 documents :
Why do I have blurred vision
Why do I have arm swelling
Why do I feel dizzy and tired
The Document frequency of “Why”, “do” and “I” is 3, because they present in all 3 documents but the Document frequency of “dizzy” is 1 because it only occurred in one document(Document 3). 
The below tables gives the Document Frequency for the terms in above documents.

Term
Document Frequency
Why
3
do
3
I
3
have
2
blurred, vision, arm, swelling, feel, dizzy, and, tired 
1


Inverse Document Frequency (IDF) : This term measures how important the term is. TF will be high for any term which occurs multiple times in a document but that term may not be of much importance to the document, for eg. is,the and are. Therefore it is needed to have a measure that weighs down the terms that occur frequently in all the documents and increase the weight for terms that are less frequent. IDF is calculated as:

Example 2
The IDF value for the terms “why” and “vision” in the example of DF can be calculated as below :
Document Frequency of “why” = 3
Total number of documents = 3
IDF of “why” = 1+log(3/3)  = 1+log 1 = 1+0 = 0 { value of Log 1 = 0}
IDF of “why” = 1

Document Frequency of “vision” = 1
Total number of documents = 3   
IDF of “vision” = 1+log(3/1)  = 1+log 3
                                             = 1+0.477 ( Log 3 = 0.477)
IDF of “vision” = 1.477

The IDF value is high for the rare terms and is more likely low for the high frequency terms. In above example too why is the high frequency word and its IDF value is low.

TF-IDF Value : We have seen above the TF for high frequency terms is high and IDF for them is low. TF-IDF is the measure of how important a term is for a document in a set of documents. The concept for this measure is that, if any term appears frequently in a document, then it should be important and should be given a high score. But if a word appears in most of the other documents, it’s probably not a unique identifier, therefore should be assigned a lower score. The formula to calculate TF-IDF value is :
TFIDF(w,d,D) = TF(w,d)IDF(w,D)

Where TF(w,d) is the Term Frequency of word w in a document d
IDF(w,d,D) is the Inverse Document Frequency of the word for a set of documents D.

Example 3
TF-IDF value for term “why” in Example 2 can be calculated as :
TF of “why” in Document 1 of Example 2 = 6
IDF of “why” calculated in Example 2 = 1
TF-IDF value = (6)(1) = 6

Cosine Similarity Algorithm

When the users asks the question, Google actions API converts speech to text and sends it to the dialogue system. Then we find the cosine similarity bwetween user’s query and potential question/answer. To do this, we need to transform the text to its vector representation.This is done in two steps:

Step 1
The questions and answers are the data for our dialogue system. They are stored in a JSON (Javascript Object Notation) file. Dialogue system reads this JSON file and applies stemming algorithm on the text of both questions and answers to get the root words and removes the punctuations. It then stores the read data in a matrix that contain following columns :
Id : Question/ Answer id present in JSON
Text : Text of Question/Answer
Q/A : Value Q or A, which determines the text is question or answer
Cosine Score : Cosine Similarity measure between Question/Answer and the user query. This is initially 0 and later updated after the calculation.

A sample matrix looks like :

Id
Text
Q/A
Cosine Score
10
Why cant I see
Q
0
10
Notice if you have decrease in your vision you must contact your optomologist
A
0
20
Why do I have arm swell
Q
0



Step 2
The user query passes through a custom filter by NLU module which applies stemming algorithm and get the root words. The stemmed words are converted to an array of words using the split method of Java API. Then we find the Term frequency (TF) and Inverse Document Frequency (IDF) for all the words. Product of TF and IDF values(TF-IDF value) is then stored as a vector which is represented as the array in Java program. Same process is applied to the questions/answers text of the matrix created in Step 1. 

The structure of TFIDF vector is like below :
[0.0,0.0,0.0,1.54,0.0,0.5]

Then the formula for cosine similarity is applied between the query and each of the questions and answers :


This gives the cosine similarity of all the questions/answers and the user’s query. The question/answer with the cosine score greater than 0.5 is selected as the reply. If there is no question/answer with the cosine score greater than 0.5 then below message is sent as the reply :

“Please rephrase the question”

This means that the question asked by user has no good match with the JSON data and hence dialogue system request the user to ask different question.
