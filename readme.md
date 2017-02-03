See <a href="http://versologie.cz/talks/aseees2016/">presentation</a> from <a href="http://aseees.org/convention">ASEEES2016</a> for details.

#### Datasets

Czech dataset comes from the <a href="versologie.cz">Corpus of Czech Verse</a>, English & French ones are based on those provided by <a href="https://github.com/sravanareddy/rhymedata">Sravana Reddy</a>


(1) Create new instance of RhymeTagger
```python
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


```
