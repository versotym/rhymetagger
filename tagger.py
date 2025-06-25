import re
import os
import ujson
import string
import nltk
from subprocess import check_output
from collections import defaultdict
from ast import literal_eval as make_tuple


class RhymeTagger:
    '''
    Collocation-driven method of discovering rhymes in a corpus of poetic texts
    --------------------------------------------------------------        
    For details see Plecháč, P. (2018). A Collocation-Driven Method of 
    Discovering Rhymes (in Czech, English, and French Poetry). In M. Fidler, 
    V. Cvrček (eds.), Taming the Corpus. From Inflection and Lexis to 
    Interpretation. Cham: Springer, 79–95.)    
    '''
    
    def __init__(self, snds_tab = []):
        '''
        Initialize tagger
        --------------------------------------------------------------        
        '''
        
        # Check if NLTK punkt available otherwise download it
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt')
        
        # Get regexp corresponding to syllable peaks in IPA transcription
        self.define_syll_peaks()
        
        # Get regexp corresponding to punctuation
        self.define_punctuation()

        self.snds_tab_ = snds_tab
                
    def define_syll_peaks(self):
        '''
        Define syllable peaks by means of regexp
        --------------------------------------------------------------
        '''
        
        # Any vowel-char followed by optional length mark
        vowels = '[iyɨʉɯuɪʏʊeøɤoəɘɵɛœʌɔæɐaăɶɑɒɜ][ːˑ]?'

        # Modifier indicating multichar phonemes
        tiechar = '_' 
        
        # Modifier indicating syllabicity of consonant
        syllchar = chr(809)

        # Peak defined as vowel-tie-vowel OR vowel OR syllabic consonant
        self.syllable_peaks = '{0}{1}{0}|{0}|.{2}'.format(
            vowels, tiechar, syllchar
        )
        

    def define_punctuation(self):
        '''
        Define punctuation by means of regexp
        --------------------------------------------------------------
        '''
        
        self.punctuation = '[' + string.punctuation + '¿«»¡…“”"\(\)\[\]–—’' + ']'
        

    def new_model(self, lang, transcribed=False, window=5, syll_max=2,
        stress=True, vowel_length=True, ngram=1, ngram_length=3, same_words=True,
        t_score_min=3.078, frequency_min=3, stanza_limit=False,
        prob_ipa_min=0.95, prob_ngram_min = 0.95, max_iter=20, 
        verbose=True, length_penalty=0, fast_ipa=True, radif=2):
        '''
        Initialize new model
        --------------------------------------------------------------     
        :lang           = [string]  language code as required by eSpeak
        :transcribed    = [boolean] whether transcription will also be passed
        :window         = [int]     how many lines forward to look for rhymes
        :syll_max       = [int]     maximum number of syllables taken into account
        :stress         = [boolean] whether to focus only on sounds after las stress
        :same_words     = [boolean] whether two same words may rhyme
        :vowel_length   = [boolean] whether vowel length should be taken into account
        :ngram          = [int]     upon which iteration to start taking n-grams into account
                                    (one-based indexing, 0 = diregard n-grams completely)
        :ngram_length   = [int]     length of the n-grams
        :t_score_min    = [float]   minimum value of t-score to add pair to train set
        :frequency_min  = [int]     minimum number of pair occurences to add to train set
        :stanza_limit   = [boolean] whether rhymes can only appear within the same stanza
        :prob_ipa_min   = [float]   minimum ipa-based probability to treat pair as rhyme
        :prob_ngram_min = [float]   minimum ngram-based probability to treat pair as rhyme
        :max_iter       = [int]     maximum number of train iteratations (epochs)
        :verbose        = [boolean] should progress be printed out?
        :length_penalty = [float]   penalty when reduplicant lengths mismatch (0 = no penalty, 1 = max penalty)
        :fast_ipa       = [boolean] True: transcribe entire poem (use separator), False: transcribe line by line
        :del_radif      = [float]/False If this proportion of lines or more ends with the same word, such word is disregarded
        '''
        
        # Parameters
        self.lang = lang
        self.transcribed    = transcribed
        self.window         = window
        self.syll_max       = syll_max
        self.stress         = stress
        self.same_words     = same_words
        self.vowel_length   = vowel_length        
        self.ngram          = ngram
        self.ngram_length   = ngram_length
        self.t_score_min    = t_score_min
        self.frequency_min  = frequency_min
        self.stanza_limit   = stanza_limit
        self.prob_ipa_min   = prob_ipa_min
        self.prob_ngram_min = prob_ngram_min
        self.max_iter       = max_iter
        self.verbose        = verbose
        self.length_penalty = length_penalty
        self.fast_ipa       = fast_ipa
        self.radif          = radif
        
        # Slots to hold current stanza and poem id
        self.stanza_id = 0
        self.poem_id = 0

        # Container for dataset. Items correspond to a single line
        # and hold a tuple (rhyme_word, poem_id, stanza_id)
        self.data = list()
        
        # Container for vocabulary. Each key is a rhyme_word found in
        # the dataset and holds a tuple ([components], final_ngram)
        self.rhyme_vocab = dict()

        # Container for overall frequencies of words, ngrams and components
        self.f = defaultdict(lambda: defaultdict(int))
        self.n = defaultdict(int)

        # Container for training set
        self.train_set = defaultdict(lambda: defaultdict(int))

        # Container for probabilities derived from training set
        self.probs = defaultdict(dict)

        # Raise exception if language is not specified and
        # transcription is not provided
        if not self.lang and not self.transcribed:
            raise Exception(
                'Language code must be specified when transcribed == False'
            )        

        # Raise exception if length penalty is outside (0,1)
        if self.length_penalty < 0 or self.length_penalty > 1:
            raise Exception(
                'Length penalty must be between (0,1)'
            )      

        # Define line separator and get its IPA
        if not self.transcribed:
            self.lineseparator = ' {.SEPARATORLINER.} '
            self.lineseparator_ipa = self._transcription(self.lineseparator)

        # Print info if required
        if self.verbose:
            print('\nNew model initialized\n')
        

    def add_to_model(self, poem):
        '''
        Add new poem to the model
        --------------------------------------------------------------
        :poem  = [list] either a list of lines OR list of lists (stanzas >
                 lines), each item may be either string hold text of the line
                 OR ipa transcription (tagging only) OR dict holding both 
                 orthography and ipa transcription {'text': ..., 'ipa': ...}
        '''
        
        if hasattr(self, 'radif') and self.radif <= 1:
            poem = self._delete_radif(poem)
        
        if self.fast_ipa:
            self._add_to_model_fast(poem)
        else:
            self._add_to_model_slow(poem)

    def _delete_radif(self, poem):
        '''
        Get rid of radif
        (repeating words at the end of lines which follow the actual rhyme)
        Can't be used with self.transcribed=True
        --------------------------------------------------------------
        :poem  = [list] either a list of lines OR list of lists (stanzas >
                 lines), each item may be either string hold text of the line
                 OR ipa transcription (tagging only) OR dict holding both 
                 orthography and ipa transcription {'text': ..., 'ipa': ...}
        '''
        
        tokenized = []
        for element in poem:
            if isinstance(element, list):
                for l in element:
                    tokens = nltk.tokenize.word_tokenize(l)
                    tokens = [x for x in tokens if not re.match(self.punctuation+'+$', x)]
                    tokenized.append(tokens)  
            else: 
                tokens = nltk.tokenize.word_tokenize(element)
                tokens = [x for x in tokens if not re.match(self.punctuation+'+$', x)]
                tokenized.append(tokens)            

        radif_done = False
        if len(tokenized) <= 2 and self.radif <= 0.5:
            self.radif = 0.51
        
        while not radif_done:
            radif_done = True
            fin_words_f = defaultdict(int)
            for l in tokenized:
                if len(l) > 0:
                    fin_words_f[l[-1]] += 1/len(tokenized)
            for w in fin_words_f:
                if fin_words_f[w] >= self.radif:
                    radif_done = False
                    for i,l in enumerate(tokenized):
                        if tokenized[i][-1] == w:
                            tokenized[i] = tokenized[i][:-1]
        it = 0
        for i,element in enumerate(poem):
            if isinstance(element, list):
                for j,l in enumerate(element):
                    poem[i][j] = ' '.join(tokenized[it])
                    it += 1
            else:
                poem[i] = ' '.join(tokenized[it])
                it += 1
        
        return poem


    def _add_to_model_fast(self, poem):
        '''
        (FAST) Add new poem to the model
        --------------------------------------------------------------
        :poem  = [list] either a list of lines OR list of lists (stanzas >
                 lines), each item may be either string hold text of the line
                 OR ipa transcription (tagging only) OR dict holding both 
                 orthography and ipa transcription {'text': ..., 'ipa': ...}
        '''

        if self.verbose:
            print('  ...adding poem #{}'.format(self.poem_id+1)+' '*10, end='\r')

        # Transcribe poem and-line final words if transcription not provided
        if not self.transcribed:
            if isinstance(poem[0], list):
                flat_poem = [x for y in poem for x in y]
            else:
                flat_poem = poem
            flat_poem = [re.sub('\n', ' ', x) for x in flat_poem]
            flat_poem = [re.sub(self.punctuation[:-1] + ' ]+$', '', x) for x in flat_poem]            
            raw_text = self.lineseparator.join(flat_poem)
            self.ipa = self._transcription(raw_text).split(self.lineseparator_ipa)
            self.ipa = [x.strip() for x in self.ipa]
            
            self.rhyme_words = [ self._get_rhyme_word(l) for l in flat_poem ]
            raw_rhyme_words = self.lineseparator.join([x if x else '' for x in self.rhyme_words])
            self.rhyme_words_ipa = self._transcription(raw_rhyme_words).split(self.lineseparator_ipa)
            self.rhyme_words_ipa = [x.strip() for x in self.rhyme_words_ipa]

        # Parse lines
        self.stanza_id = 0
        self.line_id = 0
        for x in poem: 
            if isinstance(x, list):
                for l in x:
                    self._parse_line_fast(l)
                    self.line_id += 1
                self.stanza_id += 1                
            else:
                self._parse_line_fast(x)
                self.line_id += 1
        self.poem_id += 1
                

    def _parse_line_fast(self, line):
        '''
        (FAST) Parse line into a tuple ([sound components], final-word, n-gram, 
        poem_id, stanza_id) and append it to dataset
        --------------------------------------------------------------
        :line  = [string|dict] Text of line OR dict holding both 
                 orthography and ipa transcription {'text': ..., 'ipa': ...}
        '''

        # Extract line-final word and copy IPA
        if not self.transcribed:
            rhyme_word = self.rhyme_words[self.line_id]
            ipa_line = self.ipa[self.line_id]
            #print('(',self.line_id,')', ipa_line)
        else:        
            if self.lang in ('cmn') and len(line['text']) > 0:
                rhyme_word = line['text'][-1]
            else:
                rhyme_word = self._get_rhyme_word(line['text'])
            ipa_line = line['ipa']
            
        # Append it to the dataset along with poem_id and rhyme_id
        rhyme_snds, reduplicant_length = self._split_ipa_components(ipa_line)
        #print(rhyme_snds)
        self.data.append((
            rhyme_word, self.poem_id, self.stanza_id, rhyme_snds, reduplicant_length, ipa_line, 
        ))
            
        # If this word has not been seen yet, get it's components
        # and ngram and store it into vocabular
        if rhyme_word and rhyme_word not in self.rhyme_vocab:
            if not self.transcribed:
                ipa = self.rhyme_words_ipa[self.line_id]     
                rhyme_snds, _ = self._split_ipa_components(ipa)
            else:
                final_ipa = nltk.tokenize.word_tokenize(line['ipa'])[-1]
                rhyme_snds, _ = self._split_ipa_components(final_ipa)
            ngram = self._final_ngram(rhyme_word)
            self.rhyme_vocab[rhyme_word] = (rhyme_snds, ngram)


    def _add_to_model_slow(self, poem):
        '''
        (SLOW) Add new poem to the model
        --------------------------------------------------------------
        :poem  = [list] either a list of lines OR list of lists (stanzas >
                 lines), each item may be either string hold text of the line
                 OR ipa transcription (tagging only) OR dict holding both 
                 orthography and ipa transcription {'text': ..., 'ipa': ...}
        '''
        
        if self.verbose:
            print('  ...adding poem #{}'.format(self.poem_id+1)+' '*10, end='\r')

        self.stanza_id = 0
        for x in poem: 
            if isinstance(x, list):
                for l in x:
                    l = re.sub(self.punctuation[:-1] + ' ]+$', '', l) 
                    self._parse_line_slow(l)
                self.stanza_id += 1                
            else:
                self._parse_line_slow(x)
                x = re.sub(self.punctuation[:-1] + ' ]+$', '', x)                 
        self.poem_id += 1
                

    def _parse_line_slow(self, line):
        '''
        (SLOW) Parse line into a tuple ([sound components], final-word, n-gram, 
        poem_id, stanza_id) and append it to dataset
        --------------------------------------------------------------
        :line  = [string|dict] Text of line OR dict holding both 
                 orthography and ipa transcription {'text': ..., 'ipa': ...}
        '''

        # Extract the line-final word
        if not self.transcribed:
            rhyme_word = self._get_rhyme_word(line)
            ipa_line = self._transcription(line)      

        else:      
            ipa_line = line['ipa']
            rhyme_word = self._get_rhyme_word(line['text'])


        rhyme_snds, reduplicant_length = self._split_ipa_components(ipa_line)
        self.data.append(( 
            rhyme_word, self.poem_id, self.stanza_id, rhyme_snds, reduplicant_length, ipa_line,
        ))             

        # If this word has not been seen yet, get it's components
        # and ngram and store it into vocabulary
        if rhyme_word and rhyme_word not in self.rhyme_vocab:
            if not self.transcribed:
                ipa = self._transcription(rhyme_word)      
                rhyme_snds, _ = self._split_ipa_components(ipa)
            else:
                final_ipa = nltk.tokenize.word_tokenize(line['ipa'])[-1]
                rhyme_snds, _ = self._split_ipa_components(final_ipa)
            ngram = self._final_ngram(rhyme_word)
            self.rhyme_vocab[rhyme_word] = (rhyme_snds, ngram)


    def _get_rhyme_word(self, text):
        '''
        Get final word of the line
        --------------------------------------------------------------
        :text  = [string] in specified language        
        '''
        
        # Tokenize the line
        tokens = nltk.tokenize.word_tokenize(text)
        
        # Remove punctuation
        tokens = [x for x in tokens if not re.match(self.punctuation+'+$', x)]
                
        # If line ends with a word preceded by apostrophe, merge last two
        # words and clean them from puncuation (this is done to preserve)
        # cases such as nape's, John's etc. and not only 's
        if re.search("'[^ "+string.punctuation+"]+$", text) and len(tokens) > 1:
            rhyme_word = re.sub(self.punctuation, '', ''.join(tokens[-2:]).lower())
            return rhyme_word

        # Return empty string if there's no word at all
        elif len(tokens) == 0:
            return None

        # Otherwise return rhyme word            
        else:
            rhyme_word = re.sub(self.punctuation, '', tokens[-1].lower())
            return rhyme_word
        
        
    def _transcription(self, text):
        '''
        Transcribe a text to IPA using eSpeak
        --------------------------------------------------------------
        :raw_text  = [string] poem lines joined by self.lineseparator
        '''

        text = re.sub('\.+', '.', text)
        text = re.sub('^ *\-+', '', text)
        text = re.sub('/', ' ', text)

        # Transcribe text with eSpeak NG
        ipa = check_output([
            "espeak-ng", "-q", "--ipa=2", '--punct=""', '--tie=_', '-v', self.lang, text
        ]).decode('utf-8').strip().replace('\n', '')

        ipa = re.sub('ˌ', '', ipa)

        if self.lang == 'bn':
            ipa = re.sub('[.ʰ]', '', ipa)
            ipa = re.sub('ã', 'a', ipa)

        if len(self.snds_tab_) > 0:
            for snds in self.snds_tab_:
                ipa = ipa.replace(snds[0], snds[1])

        # Remove feoreign language marks
        ipa = re.sub('\([^\)]+\)', '', ipa)
            
        return ipa
        
        
    def _split_ipa_components(self, ipa):
        '''
        Split IPA transcription to the list of relevant components 
        (syllable peaks and consonant clusters)
        --------------------------------------------------------------
        :ipa  = [string] in IPA
        '''

        # Delete vowel-length marks if required
        if not self.vowel_length:
            ipa = re.sub('[ːˑ]', '', ipa)            

        # Delete stress marks if required
        if not self.stress:
            ipa = re.sub('ˈ', '', ipa)       

        # Delete blankspaces
        ipa = re.sub(' ', '', ipa)    
        
        # Remove all before the final stress (if not already deleted)
        ipa = ''.join(ipa.split('ˈ')[-1])
                     
        # Split transcription into components
        components = re.split('('+self.syllable_peaks+')', ipa)
        
        # Remove first component if empty
        if not components[0]:
            components = components[1:]
            
        # Length of reduplicant
        reduplicant_length = len(components)/2
            
        # Reduce to required number of components
        if len(components) > self.syll_max:
            components = components[-self.syll_max*2:]
        
        # Reverse order of components
        components.reverse()

        return components, reduplicant_length


    def _final_ngram(self, word):
        '''
        Extract line final ngram from a word
        --------------------------------------------------------------
        :word  = [string]
        '''        
        if len(word) >= self.ngram_length:
            word = word[-self.ngram_length:]

        return word
        
        
    def train_model(self):
        '''
        Train model
        --------------------------------------------------------------        
        '''

        # Check if model exists and if contains some data
        if not hasattr(self, 'data') or len(self.data) == 0:
            raise Exception('You need to feed the model with poems first')

        # Count overall frequencies
        if self.verbose:
            print ('Counting overall frequencies...')
        self._overall_frequencies()

        # Get collocations
        if self.verbose:
            print('Detecting collocations...')
        self._collocations()
        
        # Perform required number of iterations
        for iteration in range(self.max_iter):
            
            if self.verbose:
                print ('Learning iteration #{}...  '.format(iteration+1))            
        
            # Calculate probabilities
            improved = self._probabilities()

            # If no improvement on probabilities, print the message
            # and break the iterations    
            if not improved:
                print('\n\nSystem has reached equilibrium')
                break

            # If there's still improvement even in the last iteration,
            # Print the message and break the iteration so we don't 
            # build another train set for no reason
            if iteration == self.max_iter - 1 and improved:
                print('\n\nSystem has not reached equilibrium')
                break
            
            # Rebuild the training set
            if self.ngram and iteration + 1 >= self.ngram:
                self._detect_rhymes(ngram=True, update_train_set=True)
            else:
                self._detect_rhymes(ngram=False, update_train_set=True)
    

    def _overall_frequencies(self):
        '''
        Calculate frequencies of words, word-pairs, n-grams and rhyme 
        components in the entire corpus
        --------------------------------------------------------------
        '''
        
        # Iterarate over lines in dataset
        for i,l in enumerate(self.data):
            
            # Skip if no word at all in line
            if not l[0]:
                continue
            
            # Increase frequency of rhyme word
            self.f['w'][l[0]] += 1
            
            # Increase frequency of final n-gram
            ngram = self.rhyme_vocab[l[0]][1]
            self.f['g'][ngram] += 1
            self.n['g'] += 1
        
            # Inrease frequency of each component and total for each position
            components = self.rhyme_vocab[l[0]][0]
            for j,s in enumerate(components):
                self.f[j][s] += 1
                self.n[j] += 1                
                
            # Iterate forward over lines that are in specified window
            for j in range(i+1, i+self.window+1):
                
                # Skip if 
                # (1) end of dataset was reached OR
                # (2) end of poem was reached OR
                # (3) end of stanza was reached and inter-stanza rhymes are forbidden
                if (
                    j > len(self.data) - 1 or
                    l[1] != self.data[j][1] or
                    ( self.stanza_limit and l[2] != self.data[j][2] )
                ):
                    continue

                # Skip if no word at all in j-line
                if not self.data[j][0]:
                    continue            

                # Increase frequency of word-pair
                word_pair = tuple(sorted([ l[0], self.data[j][0] ]))
                self.f['wp'][word_pair] += 1
                self.n['wp'] += 1


    def _collocations(self):
        '''
        Detect relevant collocations among the rhyme words
        --------------------------------------------------------------
        '''        

        # Iterate over pairs and calculate their T-scores
        for w1, w2 in self.f['wp']:

            # Skip if both words are the same and same-rhymes are forbidden
            if not self.same_words and w1 == w2:
                continue
            
            fxy = self.f['wp'][(w1,w2)]
            fx = self.f['w'][w1]
            fy = self.f['w'][w2]
            n = len(self.data)
            t_score = (fxy - (fx * fy / n)) / (fxy ** 0.5) 
                                               
            # If both T-score and pair's frequency are high enough,
            # add pair to the training set
            if t_score > self.t_score_min and fxy > self.frequency_min:
                self._add_to_train_set(w1, w2)


    def _add_to_train_set(self, w1, w2):
        '''
        Add pair to the training set (both ngram- and individual 
        component-pairs)
        --------------------------------------------------------------
        :w1  = [string] rhyme word #1
        :w2  = [string] rhyme word #2
        '''    
        
        components1 = self.rhyme_vocab[w1][0]
        components2 = self.rhyme_vocab[w2][0]
        ngram1 = self.rhyme_vocab[w1][1]
        ngram2 = self.rhyme_vocab[w2][1]
        occurrences = self.f['wp'][(w1, w2)]
                
        # Add ngram-pair
        pair = tuple(sorted([ngram1,ngram2]))
        self.train_set['g'][pair] += occurrences
               
        # Add individual component-pairs
        for i,c in enumerate(components1):
            if i >= len(components2):
                continue
            pair = tuple(sorted([components1[i], components2[i]]))
            self.train_set[i][pair] += occurrences
            
            
    def _probabilities(self):
        '''
        Calculate probabilities with which pair of items (ngrams, components)
        indicate that two words rhyme.
        Store copy of probabilities from previous iterations so that
        it may be compared and found if there is improvement or not
        --------------------------------------------------------------
        '''
        
        # Store copy of probabilities from precious iterations
        self.probs_previous = self.probs.copy()
        
        # Empty the container for new probabilities
        self.probs.clear()
        
        # Iterate over types in train set (ngrams, components 1...n)        
        for x in self.train_set:
        
            # Total occurrences of this particular type in train set
            nt = sum(self.train_set[x].values())
            
            # Iterate over pairs of values in train set
            for a, b in self.train_set[x]:

                # Relative frequency of pair in train set
                ft_ab = self.train_set[x][(a,b)] / nt

                # Relative frequency of both pair's items in the entire corpus
                fca = self.f[x][a] / self.n[x]
                fcb = self.f[x][b] / self.n[x]
                
                # Get the probability that A and B rhyme based on 
                # co-occurrence of a and b
                self.probs[x][tuple(sorted([a,b]))] = ft_ab / (ft_ab + fca * fcb)
                
        # Compare both sets of probabilities and return if there was improvement
        if self.probs != self.probs_previous:
            return True
        else:
            return False


    def _detect_rhymes(self, ngram=True, update_train_set=True):        
        '''
        Count rhyme-scores for pairs of lines that are within a 
        specified window
        --------------------------------------------------------------
        :ngram             = [boolean] whether to take into account n-grams
        :update_train_set  = [boolean] whether to update train set or to return
                             list of rhymes
        '''
        
        rhymes_detected = defaultdict(set)
        
        # Iterarate over lines in dataset
        for i,l in enumerate(self.data):           

            # Skip if no word at all in i-line
            if not self.data[i][0]:
                continue            
                                        
            # Iterate forward over lines that are in specified window
            for j in range(i+1, i+self.window+1):
                
                # Skip if 
                # (1) end of dataset was reached OR
                # (2) end of poem was reached OR
                # (3) end of stanza was reached and inter-stanza rhymes are forbidden
                # (4) both words are the same and same-rhymes are forbidden
                if (
                    j > len(self.data) - 1 or
                    l[1] != self.data[j][1] or
                    ( self.stanza_limit and l[2] != self.data[j][2] ) or
                    ( not self.same_words and l[0] == self.data[j][0] )
                ):
                    continue
                
                # Skip if no word at all in j-line
                if not self.data[j][0]:
                    continue            
                
                # Get rhyme score based on components 
                ipa_score = self._rhyme_score(l[3], self.data[j][3],
                                              l[4], self.data[j][4])
                
                #print(self.data[j][3], self.data[j][4], ipa_score)

                # If score is high enough
                if ipa_score > self.prob_ipa_min:

                    # Add j to i-line and i to j-line 
                    rhymes_detected[i].add(j)
                    rhymes_detected[j].add(i)

                    # Annotate distant rhymes
                    for k in rhymes_detected[i]:
                        if k != j:
                            rhymes_detected[k].add(j)
                            rhymes_detected[j].add(k)
                            
            # If ngrams should be used and no rhymes were found for i-line,
            # iterate over window once again and perform ngram-based recognition
            if not ngram:
                continue
            if i in rhymes_detected:
                continue
            for j in range(i+1, i+self.window+1):
                if (
                    j > len(self.data) - 1 or
                    l[1] != self.data[j][1] or
                    ( self.stanza_limit and l[2] != self.data[j][2] ) or
                    ( not self.same_words and l[0] == self.data[j][0] ) or
                    j in rhymes_detected
                ):
                    continue

                # Skip if no word at all in j-line
                if not self.data[j][0]:
                    continue            
            
                ngram_score = self._ngram_score(l[0], self.data[j][0],
                                                l[4], self.data[j][4])
                if ngram_score > self.prob_ngram_min:
                    rhymes_detected[i].add(j)
                    rhymes_detected[j].add(i)

        # Update train set if required (training)
        if update_train_set:
            for i in rhymes_detected:
                for j in rhymes_detected[i]:
                    if i > j:
                        continue
                    self._add_to_train_set(self.data[i][0], self.data[j][0])

        # Otherwise format output and return                    
        else:
            output = self.output(rhymes_detected)
            return output
            

    def output(self, rhymes_detected):
        '''
        Return output in required format
        --------------------------------------------------------------
        :rhymes_detected  = [dict] dict holding rhymes (keys are lines indices
                            values are lists holding indices of rhyming 
                            counterparts)
        '''
        
                
        # (1) List of lists where elements of main list correspond to 
        # particular lines and sub-lists hold indices or its rhyming counterparts
        if self.output_format == 1:
            output = []

            # Iterate over all lines
            for i in range(len(self.data)):

                # If there are some rhymes, append them to the output
                if i in rhymes_detected:
                    output.append(sorted(list(rhymes_detected[i])))

                # Otherwise append empty list
                else:
                    output.append([])                    

            return output

        # (2|3) 2: Rhyme-chains; list of lists where each sub-list hold
        #          indices of lines that rhyme
        #       3: ABBA-like scheme; a unique index is assigned to each rhyme
        #          chain, the output is a list where each element corresponds
        #          to single line and holds this unique index
        elif self.output_format in(2,3):
            output = []

            # Iterate over lines that rhyme with something
            for i in rhymes_detected:

                # Append the list of rhymes + index of current line to the output
                output.append(sorted(list(rhymes_detected[i])+[i]))

            # Make the list of lists unique
            output = [list(x) for x in set(tuple(x) for x in output)]

            # Sort it by first element of each sublist
            output = sorted(output, key=lambda x: x[0])
            
                
            # (2) Return a list of rhyme-chains
            if self.output_format == 2:
                return output     

            # (3) Return ABBA-like scheme
            else:
                output_abba = []
                for i in range(len(self.data)):
                    output_abba.append(next((
                        idx+1 for idx,elem in enumerate(output) if i in elem
                    ), None))
                return(output_abba)
                    

    def _rhyme_score(self, w1, w2, length1=None, length2=None):        
        '''
        Calculate overall score based on probabilities of particular
        component-pairs
        --------------------------------------------------------------
        :w1  =     [string] rhyme word #1
        :w2  =     [string] rhyme word #2
        :length1 = [int] length of reduplicant #1
        :length2 = [int] length of reduplicant #2        
        '''
        
        score = [1,1]
        components1 = w1
        components2 = w2
        if len(components1) > len(components2):
            components1 = components1[:len(components2)]
        elif len(components2) > len(components1):
            components2 = components2[:len(components1)]
                        
        if length1 % 2 != length2 % 2:
            length_coef = 1 - self.length_penalty
        else:
            length_coef = 1
                        
        # If all components are the same, simply return score = 1
        if components1 == components2:
            return 1 * length_coef                      
                        
        # Otherwise iterate over components
        for i,c in enumerate(components1):
            if i >= len(components2):
                continue
            
            # If probability of components pair is known, get its prob
            if tuple(sorted([components1[i], components2[i]])) in self.probs[i]:
                p = self.probs[i][tuple(sorted([components1[i], components2[i]]))]

            # Otherwise if both components are the same, assign it 0.9
            elif components1[i] == components2[i]:
                p = 0.99

            # Otherwise assign it 0.0001
            else:
                p = 0.0001

            # Multiply components of formula by current values
            score[0] *= p
            score[1] *= (1-p)

        # Return overall probability
        if ( score[0] + score[1] ) > 0:
            return (length_coef * score[0])/ ( score[0] + score[1])
        else:
            return 0
            
            
    def _ngram_score(self, w1, w2, length1, length2):        
        '''
        Calculate score based on probabilities of ngrams
        --------------------------------------------------------------
        :w1  = [string] rhyme word #1
        :w2  = [string] rhyme word #2
        :length1 = [int] length of reduplicant #1
        :length2 = [int] length of reduplicant #2                
        '''
        
        ngram1 = self.rhyme_vocab[w1][1]
        ngram2 = self.rhyme_vocab[w2][1]
        if length1 % 2 != length2 % 2:
            length_coef = 1 - self.length_penalty
        else:
            length_coef = 1        
                                    
        # If probability of ngrams pair is known, return its prob
        if tuple(sorted([ngram1, ngram2])) in self.probs['g']:
            return self.probs['g'][tuple(sorted([ngram1, ngram2]))] * length_coef

        # Otherwise if both ngrams are the same, return 0.9
        elif ngram1 == ngram2:
            return 0.99 * length_coef

        # Otherwise assign it 0.0001
        else:
            return 0.0001


    def save_model(self, file):
        '''
        Save model into json for future use
        --------------------------------------------------------------
        :file  = [string] path to a json file where model will be stored
        '''
        
        model = {
            'settings': {
                'lang':           self.lang,
                'window':         self.window,
                'syll_max':       self.syll_max,
                'vowel_length':   self.vowel_length,
                'stress':         self.stress,
                'same_words':     self.same_words,
                'ngram':          self.ngram_length,
                'ngram_length':   self.ngram_length,
                't_score_min':    self.t_score_min,
                'frequency_min':  self.frequency_min,
                'stanza_limit':   self.stanza_limit,
                'prob_ipa_min':   self.prob_ipa_min,
                'prob_ngram_min': self.prob_ngram_min,
                'max_iter':       self.max_iter,
                'length_penalty': self.length_penalty,
                'fast_ipa':       self.fast_ipa,
                'radif':          self.radif,
            },
            'probs': self.probs,
        }
        
        if not file.endswith('.json'):        
            file += '.json'
        with open(file, 'w') as f:
            f.write(ujson.dumps(model, indent=2))
        
    
    def load_model(self, model=None, verbose=True):
        '''
        Load model from json file
        --------------------------------------------------------------
        :model  = [string] either a name of one of the pretreained models or 
                  path to a JSON file containing custom model
        '''        

        if model.endswith('.json'):
            with open(model, 'r') as f:
                model = ujson.load(f)
        else:
            parent = os.path.dirname(__file__)
            with open(os.path.join(parent, 'models', model+'.json'), 'r') as f:
                model = ujson.load(f)            
                

        self.lang           = model['settings']['lang']
        self.window         = model['settings']['window']
        self.syll_max       = model['settings']['syll_max']
        self.stress         = model['settings']['stress']
        self.same_words     = model['settings']['same_words']
        self.vowel_length   = model['settings']['vowel_length']
        self.ngram          = model['settings']['ngram']
        self.ngram_length   = model['settings']['ngram_length']
        self.t_score_min    = model['settings']['t_score_min']
        self.frequency_min  = model['settings']['frequency_min']
        self.stanza_limit   = model['settings']['stanza_limit']
        self.prob_ipa_min   = model['settings']['prob_ipa_min']
        self.prob_ngram_min = model['settings']['prob_ngram_min']
        self.max_iter       = model['settings']['max_iter']
        self.length_penalty = model['settings']['length_penalty']
        self.fast_ipa       = model['settings']['fast_ipa'] 
        if 'radif' in model['settings']:
            self.radif          = model['settings']['radif']                
            
        # Load probabilities (needs to get tuples back from strings)
        probs = model['probs']
        self.probs = defaultdict(dict)
        for x in probs:
            for y in probs[x]:    
                if re.search('^[0-9]$', x):
                    self.probs[int(x)][make_tuple(y)] = probs[x][y]
                else:
                    self.probs[x][make_tuple(y)] = probs[x][y]
            
        # Print info
        if verbose:
            print('='*36)
            print('Model loaded with following settings:')
            print('='*36)
            maxlen = max(len(x) for x in model['settings'])
            for x in sorted(model['settings']):
                print('{}:'.format(x).rjust(maxlen+2), model['settings'][x])
            print('='*36)
            
        
    def tag(self, poem, transcribed=False, output_format=1, **kwargs):
        '''
        Perform tagging
        --------------------------------------------------------------     
        :poem           = [list] either a list of lines OR list of lists (stanzas >
                          lines), each item may be either string hold text of the line
                          OR ipa transcription (tagging only) OR dict holding both 
                          orthography and ipa transcription {'text': ..., 'ipa': ...}
        :transcribed    = [boolean] whether transcription will also be passed
        :output_format  = [int] 1: returns list of indices for each line
                                2: returns list of indices for each rhyme-
                                3: returns classic ABBA list where ints instead of letters

        [following may be passed to modify settings inherited from the model]

        :lang           = [string]  language code as required by eSpeak
        :window         = [int]     how many lines forward to look for rhymes
        :same_words     = [boolean] whether two same words may rhyme
        :ngram          = [int]     upon which iteration to start taking n-grams into account
                                    (one-based indexing, 0 = disregard n-grams completely)
        :t_score_min    = [float]   minimum value of t-score to add pair to train set
        :frequency_min  = [int]     minimum number of pair occurences to add to train set
        :stanza_limit   = [boolean] whether rhymes can only appear within the same stanza
        :prob_ipa_min   = [float]   minimum ipa-based probability to treat pair as rhyme
        :prob_ngram_min = [float]   minimum ngram-based probability to treat pair as rhyme
        '''

        # Check if model is loaded
        if not hasattr(self, 'probs'):
            raise Exception('No model loaded. Please run load_model() first.')
        
        # Parameters
        self.transcribed = transcribed        
        self.output_format = output_format
        
        if 'lang' in kwargs:
            self.lang = kwargs['lang']
        if 'window' in kwargs:
            self.window = kwargs['window']
        if 'same_words' in kwargs:
            self.same_words = kwargs['same_words']
        if 'ngram' in kwargs:
            self.ngram = kwargs['ngram']
        if 't_score_min' in kwargs:
            self.t_score_min = kwargs['t_score_min']
        if 'frequency_min' in kwargs:
            self.frequency_min = kwargs['frequency_min']
        if 'stanza_limit' in kwargs:
            self.stanza_limit = kwargs['stanza_limit']
        if 'prob_ipa_min' in kwargs:
            self.prob_ipa_min = kwargs['prob_ipa_min']
        if 'prob_ngram_min' in kwargs:
            self.prob_ngram_min = kwargs['prob_ngram_min']
        if 'length_penalty' in kwargs:
            self.length_penalty = kwargs['length_penalty']            
        if 'fast_ipa' in kwargs:
            self.fast_ipa = kwargs['fast_ipa']     
        if 'radif' in kwargs:
            self.radif = kwargs['radif']                          

        # Slots to hold current stanza and poem id
        self.stanza_id = 0
        self.poem_id = 0
        # Line separator for fast IPA
        if not self.transcribed:
            self.lineseparator = ' {.SEPARATORLINER.} '
            self.lineseparator_ipa = self._transcription(self.lineseparator)

        # Container for dataset. Items correspond to a single line
        # and hold a tuple (rhyme_word, poem_id, stanza_id)
        self.data = list()
        
        # Container for vocabulary. Each key is a rhyme_word found in
        # the dataset and holds a tuple ([components], final_ngram)
        self.rhyme_vocab = dict()     

        # Perform tagging        
        self.verbose = False        
        self.add_to_model(poem)
        rhymes = self._detect_rhymes(ngram=self.ngram, update_train_set=False)
        
        return rhymes