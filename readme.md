See <a href="http://versologie.cz/talks/aseees2016/">presentation</a> from <a href="http://aseees.org/convention">ASEEES2016</a> for details.

#### Datasets

Czech dataset comes from the <a href="versologie.cz">Corpus of Czech Verse</a>, English & French ones are based on those provided by <a href="https://github.com/sravanareddy/rhymedata">Sravana Reddy</a>



```python
'''(1) Create new instance of RhymeTagger'''
tager= RhymeTagger (               # TAGGER ATTRIBUTES (optional arguments: default values)
    window = 4,                    # How many lines backwards to search for rhymes
    syllable_max = 2,              # Maximum number of syllables to check components match
    stress = True,                 # Check match only after last stressed syllable peak ?
    ngram = True,                  # Check the match of line final n-grams ?
    ngram_length = 3,              # Length of such n-grams
    t_score_min = 3.078,           # Minimum t-score to count pair as collocation
    frequency_min = 4,             # Minimum absolute frequency to coun pair as collocation
    stanza_limit = True,           # Mark only rhymes within one stanza
    probability_sampa_min = 0.95,  # Minimum probability based on sampa to count pair as rhyme
    probability_ngram_min = 0.95   # Minimum probability based on n-grams to count pair as rhyme
):

'''(2) Feed tagger with your corpus data'''
for i in your_data
    '''poem = list of following dicts: 
    { 'word': your_word, 'sampa': its_sampa, 'stanza': id_of_stanza_to_which_it_belongs }'''
    tagger.initial_frequencies(poem)

'''(3) Check for collocations'''
tagger.collocations()

'''(4) Tagging iterations'''
for iteration in range(1, maximum_number_of_iterations+1):
   for i in your_data
       '''poem = list of following dicts: 
        { 'word': your_word, 'sampa': its_sampa, 'stanza': id_of_stanza_to_which_it_belongs,
        'gold': oprional_gold_standard_set, 'class': optional_set_of_classes_to_evaluate_separately }''' 
        result = tagger.tagging(poem)
        '''rebuild training sett'''
    no_difference = tagger.rebuild_training_set()
    if no_difference:
        break
```
