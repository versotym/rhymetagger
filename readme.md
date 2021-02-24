
# RhymeTagger

A simple collocation-driven  **recognition of rhymes**. Contains pre-trained models for **Czech, Dutch, English, German, Russian,** and **Spanish** poetry.

Details in P. Plecháč (2018). [A Collocation-Driven Method of Discovering Rhymes (in Czech, English, and French Poetry)](https://doi.org/10.1007/978-3-319-98017-1_). In Taming the Corpus: From Inflection and Lexis to Interpretation. Cham: Springer, 79-95.

## Installation

```console
pip install rhymetagger
```

or

```console
pip3 install rhymetagger
```

## Usage

To annotate poems with one of the pre-trained models:
```python
from rhymetagger import RhymeTagger

poem = [
	"Tell me not, in mournful numbers,",
	"Life is but an empty dream!",
	"For the soul is dead that slumbers,",
	"And things are not what they seem.",
	"Life is real! Life is earnest!",
	"And the grave is not its goal;",
	"Dust thou art, to dust returnest,",
	"Was not spoken of the soul.",
	"Not enjoyment, and not sorrow,",
	"Is our destined end or way;",
	"But to act, that each tomorrow",
	"Find us farther than today.",
]

rt = RhymeTagger()
rt.load_model(model='en')

rhymes = rt.tag(poem, output_format=3) 
print(rhymes)

>> [1, 2, 1, 2, 3, 4, 3, 4, 5, 6, 5, 6]
```

```python
poem = [
	"Über allen Gipfeln",
	"Ist Ruh’,",
	"In allen Wipfeln",
	"Spürest du",
	"Kaum einen Hauch;",
	"Die Vögelein schweigen im Walde.",
	"Warte nur, balde",
	"Ruhest du auch.",
]

rt = RhymeTagger()
rt.load_model(model='de')

rhymes = rt.new_model(poem, output_format=3) 
print(rhymes)

>> [1, 2, 1, 2, 3, 4, 4, 3]
```

To train your own model:

```python
from rhymetagger import RhymeTagger

rt = RhymeTagger()
rt.new_model(lang=ISO_CODE)

for poem in YOUR_CORPUS:
	rt.add_to_model(poem)

rt.train_model()
rt.save_model(PATH_TO_FILE)
```


## Pre-trained models

model | description
----- | -----
**cs** | Czech model (trained with [Corpus of Czech Verse](http://versologie.cz/v2/web_content/corpus.php?lang=en); 80k poems)
**de** | German model (trained with [Metricalizer](https://metricalizer.de/); 50k poems)
**en** | English model (trained with [Guttenberg poetry corpus](https://gutentag.sdsu.edu/); 85k poems)
**es** | Spanish model (trained with [DISCO](https://github.com/pruizf/disco); 9k poems)
**nl** | Dutch model (trained with [Meertens Song Collection](https://github.com/fbkarsdorp/meertens-song-collection); 28k poems)
**ru** | Russian model (trained with [Poetic subcorpus of Russian National Corpus](http://ruscorpora.ru); 18k poems)


## Methods

###  RhymeTagger.load_model(model, verbose=False)
Load one of the pre-trained models or a custom model stored in JSON file

**Parameters**
>**model**: string
>> either a name of one of the pre-trained models or path to a JSON file containing custom model

>**verbose**:string
>> whether to print out info on model settings

###  RhymeTagger.tag(poem, transcribed=False, output_format=1, \*\*kwargs)
Perform rhyme recognition

**Parameters**

> **poem**: list
>>either a list of lines OR list of lists (stanzas > lines), each item may be either string holding text of the line OR ipa transcription (```transcribed``` must be ```True```) OR dict holding both orthography and ipa transcription {'text': ..., 'ipa': ...} (```transcribed``` must be ```True```)

> **transcribed**: boolean 
>> whether ipa transcription is passed
        
>**output_format**: int
>>1: returns list of indices for each line
>>2: returns list of indices for each rhyme
>>3: returns classic ABBA list where ints instead of letters

>> e.g. a limerick with a rhyme scheme a-a-b-b-a would be encoded as
>>>1: [ [1,4], [0,4], [2], [3], [0,1] ]
>>>2: [ [0,1,4], [2,3] ]
>>>3: [ 1,1,2,2,1 ]

>**\*\*kwargs**
>>Parameters that may be used to override settings inherited from the model
>>(```window, same_words, ngram, t_score_min, frequency_min, stanza_limit, prob_ipa_min, prob_ngram_min```

** Returns **

>**rhymes**: list
>>a list of rhymes in the requested format, see ```output_format```

###  RhymeTagger.new_model(lang, transcribed=False, window=5, syll_max=2, stress=True, vowel_length=True, ngram=1, ngram_length=3, same_words=True, t_score_min=3.078, frequency_min=3, stanza_limit=False, prob_ipa_min=0.95, prob_ngram_min = 0.95, max_iter=20, verbose=True)
Initialize new model

**Parameters**

>**lang**: string
>>ISO language code as required by eSpeak

> **transcribed**: boolean 
>> whether ipa transcription is passed

>**window**: int
>>how many lines forward to look for rhymes

>**syll_max**: int
>>maximum number of syllables taken into account

>**stress**: boolean
>>whether to focus only on sounds following after the last stress

>**vowel_length**: boolean
>>whether vowel length should be taken into account

>**same_words**: boolean
>>whether repetition of the same word counts as rhyme

>**ngram**: int
>> upon which iteration to start taking character n-grams into account (one-based indexing, 0 = disregard n-grams completely)

>**ngram_length**: int
>> length of the character n-grams

>**t_score_min**: float
>>minimum value of t-score to add pair to train set

>**frequency_min**:  int
>>minimum number of pair occurences to add to train set

>**stanza_limit**: boolean
>> whether rhymes can only appear within the same stanza

>**prob_ipa_min**: float
>>minimum ipa-based probability to treat pair as rhyme

>**prob_ngram_min**: float
>>minimum ngram-based probability to treat pair as rhyme

>**max_iter**: int
>>maximum number of training iteratations

>**verbose**: boolean
>>should progress be printed out?

### RhymeTagger.add_to_model(poem)
Feed the model with a poem

**Parameters**

> **poem**: list
>>either a list of lines OR list of lists (stanzas > lines), each item may be either string holding text of the line OR dict holding both orthography and ipa transcription {'text': ..., 'ipa': ...} (```transcribed``` must be ```True```)

### RhymeTagger.train_model()
Train the model fed with poems 


### RhymeTagger.save_model(file)
Save the model to a JSON file

**Parameters**

> **file**: string
>>file path

