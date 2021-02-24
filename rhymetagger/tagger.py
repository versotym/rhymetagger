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
    
    def __init__(self):
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
        
        
    def define_syll_peaks(self):
        '''
        Define syllable peaks by means of regexp
        --------------------------------------------------------------
        '''
        
        # Any vowel-char followed by optional length mark
        vowels = '[iyɨʉɯuɪʏʊeøɤoəɘɵɛœʌɔæɐaăɶɑɒ][ːˑ]?'

        # Modifier indicating multichar phonemes
        tiechar = chr(865) 
        
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
        
        self.punctuation = '[' + string.punctuation + '¿«»¡…“”\(\)\[\]–—’' + ']'
        

    def new_model(self, lang, transcribed=False, window=5, syll_max=2,
        stress=True, vowel_length=True, ngram=1, ngram_length=3, same_words=True,
        t_score_min=3.078, frequency_min=3, stanza_limit=False,
        prob_ipa_min=0.95, prob_ngram_min = 0.95, max_iter=20, 
        verbose=True):
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
        
        if self.verbose:
            print('  ...adding poem #{}'.format(self.poem_id+1)+' '*10, end='\r')

        self.stanza_id = 0
        for x in poem: 
            if isinstance(x, list):
                for l in x:
                    self._parse_line(l)
                self.stanza_id += 1                
            else:
                self._parse_line(x)
        self.poem_id += 1
                

    def _parse_line(self, line):
        '''
        Parse line into a tuple ([sound components], final-word, n-gram, 
        poem_id, stanza_id) and append it to dataset
        --------------------------------------------------------------
        :line  = [string|dict] Text of line OR dict holding both 
                 orthography and ipa transcription {'text': ..., 'ipa': ...}
        '''

        # Extract the line-final word
        if not self.transcribed:
            rhyme_word = self._get_rhyme_word(line)
        else:        
            rhyme_word = self._get_rhyme_word(line['text'])

        # Append it to the dataset along with poem_id and rhyme_id
        self.data.append(( 
            rhyme_word, self.poem_id, self.stanza_id
        ))        

        # If this word has not been seen yet, get it's components
        # and ngram and store it into vocabular
        if rhyme_word and rhyme_word not in self.rhyme_vocab:
            if not self.transcribed:
                ipa = self._transcription(rhyme_word)      
                rhyme_snds = self._split_ipa_components(ipa)
            else:
                final_ipa = nltk.tokenize.word_tokenize(line['ipa'])[-1]
                rhyme_snds = self._split_ipa_components(final_ipa)
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
        :text  = [string] in specified language
        '''
        
        # Transcribe entire line with eSpeak        
        ipa = check_output([
            "espeak", "-q", "--ipa=1", '-v', self.lang, text
        ]).decode('utf-8').strip()
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
            
        # Reduce to required number of components
        if len(components) > self.syll_max:
            components = components[-self.syll_max*2:]
        
        # Reverse order of components
        components.reverse()

        return components


    def _final_ngram(self, word):
        '''
        Extract line final ngram from a word
        --------------------------------------------------------------
        :word  = [string]
        '''        

        if len(word) > self.ngram_length:
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

            # If no improvement on probabilities, print the meassage
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
                ipa_score = self._rhyme_score(l[0], self.data[j][0])

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
            
                ngram_score = self._ngram_score(l[0], self.data[j][0])
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
                    

    def _rhyme_score(self, w1, w2):        
        '''
        Calculate overall score based on probabilities of particular
        component-pairs
        --------------------------------------------------------------
        :w1  = [string] rhyme word #1
        :w2  = [string] rhyme word #2
        '''
        
        score = [1,1]
        components1 = self.rhyme_vocab[w1][0]
        components2 = self.rhyme_vocab[w2][0]
                        
        # If all components are the same, simply return score = 1
        if components1 == components2:
            return 1                        
                        
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
            return score[0] / ( score[0] + score[1])
        else:
            return 0
            
            
    def _ngram_score(self, w1, w2):        
        '''
        Calculate score based on probabilities of ngrams
        --------------------------------------------------------------
        :w1  = [string] rhyme word #1
        :w2  = [string] rhyme word #2
        '''
        
        ngram1 = self.rhyme_vocab[w1][1]
        ngram2 = self.rhyme_vocab[w2][1]
                                    
        # If probability of ngrams pair is known, return its prob
        if tuple(sorted([ngram1, ngram2])) in self.probs['g']:
            return self.probs['g'][tuple(sorted([ngram1, ngram2]))]

        # Otherwise if both ngrams are the same, return 0.9
        elif ngram1 == ngram2:
            return 0.99

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
                                    (one-based indexing, 0 = diregard n-grams completely)
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
            
        # Slots to hold current stanza and poem id
        self.stanza_id = 0
        self.poem_id = 0

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