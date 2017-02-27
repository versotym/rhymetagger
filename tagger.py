import os, sys, sqlite3, re, json
from collections import defaultdict

class RhymeTagger:

  def __init__( self, 
                window = 4, 
                syllable_max = 2, 
                stress = True, 
                ngram = True, 
                ngram_length = 3,
                t_score_min = 3.078, 
                frequency_min = 4, 
                stanza_limit = False, 
                probability_sampa_min = 0.95, 
                probability_ngram_min = 0.95):

      self.syllable_peaks = "iye2E9{a&IYU1}@836Mu7oVOAQ0="
      self.sampa_dict = defaultdict(dict)
      self.word_f = defaultdict(int)
      self.word_gf = defaultdict(int)
      self.word_n = 0
      self.pair_f = defaultdict(lambda : defaultdict(int))
      self.components_cf = defaultdict(lambda : defaultdict(int))
      self.components_cn = defaultdict(int)
      self.components_tf = defaultdict(lambda : defaultdict(lambda : defaultdict(int)))
      self.components_tn = defaultdict(int)
      self.ngrams_cf = defaultdict(int)
      self.ngrams_cn = 0
      self.ngrams_tf = defaultdict(lambda : defaultdict(int))
      self.ngrams_tn = 0
      self.new_training_set = defaultdict(lambda : defaultdict(int))
      self.eval = defaultdict(lambda : defaultdict(int))
      self.settings = dict()

      arguments = locals()
      for key in arguments:
        if (key != 'self'):
          self.settings[key] = arguments[key]

#==============================================================================
# INITIAL FREQUENCIES
  
  def initial_frequencies(self, data):
    '''Get words and word-pairs frequencies'''
    for i, val in enumerate(data):
      self._word_f(data[i]['word'])
      self.sampa_dict[ data[i]['word'] ] = data[i]['sampa']
      self._components_cf( data[i]['sampa'])
      self._ngrams_cf( data[i]['word'])      
      
      for j in range(i-self.settings['window'], i):         
        if j < 0:
          continue
        if ( ( self.settings['stanza_limit'] == False or 
        data[i]['stanza'] == data[j]['stanza'] ) and
        data[i]['word'] != data[j]['word'] ):
          self.pair_f[ data[i]['word'] ][ data[j]['word'] ] += 1
          self.pair_f[ data[j]['word'] ][ data[i]['word'] ] += 1

  def _word_f(self, word):  
    '''Count word frequency in corpus'''
    self.word_f[ word ] += 1
    self.word_n += 1
      
  def _components_cf(self, sampa):
    '''Count components frequency in corpus'''
    components = self._split_to_components( sampa )
    for i, c in enumerate(components):
      self.components_cf[i][c] += 1
      self.components_cn[i] += 1   
                       
  def _split_to_components(self, sampa):
    ''' Split word to components(syllable peaks + consonant clusters) according to settings'''   
    sampa = sampa[::-1]
    if self.settings['stress']:
      sampa = re.sub(r"[^" + self.syllable_peaks + "]+ '", " '", sampa)
      sampa = sampa.split("'", 1)[0]
    sampa = re.sub(r"([" + self.syllable_peaks + "])", r'#\1#', sampa)
    sampa = sampa.replace('##', '').replace(' ','').replace("'", '')
    sampa = re.sub(r'#$', '', sampa)
    sampa = sampa.split('#')[:self.settings['syllable_max'] * 2]
    for i, c in enumerate(sampa):
      sampa[i] = re.sub(r"^$", r'#', sampa[i]) 
    return sampa
  
  def _ngrams_cf(self, word):
    '''Count n-grams frequency in corpus'''
    ngram = word[-self.settings['ngram_length']:]
    self.ngrams_cf[ngram] += 1
    self.ngrams_cn += 1  
  
#==============================================================================
# COLLOCATIONS
          
  def collocations(self):
    '''Get collocations'''
    type_token = [0,0]  
    for w1 in self.pair_f:
      for w2 in self.pair_f[w1]:
        t_score = ( self.pair_f[w1][w2] - (( self.word_f[w1] * self.word_f[w2]) / self.word_n))
        t_score /= ( self.pair_f[w1][w2] ** 0.5)

        if ( t_score > self.settings['t_score_min'] and 
        self.pair_f[w1][w2] >= self.settings['frequency_min'] ):
          self._add_to_training_set(w1, w2, self.pair_f[w1][w2])
          type_token[0] += 1
          type_token[1] += self.pair_f[w1][w2]          

    return type_token[0], type_token[1]

  def _add_to_training_set(self, w1, w2, occurences):
    '''Add words' components to training set'''
    length = self.settings['ngram_length']
    ngrams = [ w1[-length:], w2[-length:] ] 
    self.ngrams_tf[ngrams[0]][ngrams[1]] += occurences
    self.ngrams_tn += occurences
    
    sampas = [ self.sampa_dict[w1], self.sampa_dict[w2] ]
    c1 = self._split_to_components( sampas[0] )
    c2 = self._split_to_components( sampas[1] )

    for i, c in enumerate(c1):
      if i < len(c2):
        self.components_tf[i][ c1[i] ][ c2[i] ] += occurences
        self.components_tn[i] += occurences    
        
#==============================================================================
# TAGGING
  
  def tagging(self, data):
    '''Perform tagging'''
    rhymes = defaultdict(set)
    
    # Tag rhymes according to SAMPA
    for i, val in enumerate(data):
      for j in range(i-self.settings['window'], i):         
        if j < 0:
          continue
        if self.settings['stanza_limit'] and data[i]['stanza'] != data[j]['stanza']:
          continue
        score = self._rhyme_score(data[i]['sampa'], 
                                  data[j]['sampa'], 
                                  data[i]['word'], 
                                  data[j]['word'])

        if ( score > self.settings['probability_sampa_min'] and 
        data[i]['word'] != data[j]['word'] ):
          rhymes[i].add(j)   
            
          # Tag distant rhymes
          if rhymes[j]:
            for k in rhymes[j]:
              if ( ( self.settings['stanza_limit'] == False or 
              data[i]['stanza'] == data[k]['stanza'] ) and
              data[i]['word'] != data[k]['word'] ):
                rhymes[i].add(k)
                rhymes[k].add(i)
          rhymes[j].add(i)

    # Tag rest of rhymes according to n-grams
    if self.settings['ngram']:
      for i, val in enumerate(data):
        for j in range(i-self.settings['window'], i):         
          if ( j < 0  or rhymes[i] or rhymes[j] ):
            continue
          if self.settings['stanza_limit'] and data[i]['stanza'] != data[j]['stanza']:
            continue
          score = self._ngram_score(data[i]['word'], data[j]['word'])
          if ( score > self.settings['probability_ngram_min'] and 
          data[i]['word'] != data[j]['word'] ):
            rhymes[i].add(j)
            rhymes[j].add(i)
                  
    # Add rhymes to new training set
    for i in rhymes:
      for j in rhymes[i]:         
        if i > j:
          self.new_training_set[ data[i]['word'] ][ data[j]['word'] ] += 1
                          
    if 'gold' in data[0]:
      # Reduce gold standard (remove rhymes of same words and cross-stanza rhymes if forbidden)
      for i, val in enumerate(data):
        gold_reduced = set()
        for j in data[i]['gold']:
          if ( data[i]['word'] != data[j]['word'] and
          ( self.settings['stanza_limit'] == False or 
          data[i]['stanza'] == data[j]['stanza'] ) ):
            gold_reduced.add(j)
          data[i]['gold'] = gold_reduced.copy()
              
      # Perform evaluation
      self._eval(data, rhymes)
      return rhymes
                          
  def _rhyme_score(self, sampa1, sampa2, word1, word2):
    '''Probability of being rhyme based on SAMPA'''
    score = [1,1]
    c1 = self._split_to_components( sampa1 )
    c2 = self._split_to_components( sampa2 )
    if len(c1) > len(c2):
      c1 = c1[:len(c2)]
    elif len(c2) > len(c1):
      c2 = c2[:len(c1)]
   
    if c1 == c2:
      return 1
    else:
      for i, c in enumerate(c1):
        p = 0;
        if c1[i] in self.components_tf[i] and c2[i] in self.components_tf[i][c1[i]]:
          p1 = self.components_tf[i][ c1[i] ][ c2[i] ] / self.components_tn[i]
          p0 = self.components_cf[i][ c1[i] ] * self.components_cf[i][ c2[i] ]
          p0 /= self.components_cn[i] * self.components_cn[i]
          p = p1 / ( p1 + p0 )                    
        elif c1[i] == c2[i]:
          p = 0.9
        else:
          p = 0.0001
        score[0] *= p
        score[1] *= (1-p)
      if ( score[0] + score[1] ) > 0:
        return score[0] / ( score[0] + score[1])
      else:
        return 0
  
  def _ngram_score(self, word1, word2):
    '''Probability of being rhyme based on final n-grams'''
    ngrams = [ word1[-self.settings['ngram_length']:], word2[-self.settings['ngram_length']:] ]
    if ngrams[0] in self.ngrams_tf and ngrams[1] in self.ngrams_tf[ngrams[0]]:
      p1 = self.ngrams_tf[ ngrams[0] ][ ngrams[1] ] / self.ngrams_tn
      p0 = self.ngrams_cf[ ngrams[0] ] * self.ngrams_cf[ ngrams[1] ]
      p0 /= self.ngrams_cn * self.ngrams_cn
      return p1 / ( p1 + p0 )                    
    elif ngrams[0] == ngrams[1]:
      return 1
    else:
      return 0.0001
    
  def rebuild_training_set(self):
    '''Rebuild training set according to last tagging'''
    old_set = self.components_tf.copy()
    self.components_tf.clear()
    self.components_tn.clear()
    self.ngrams_tf.clear()
    self.ngrams_tn = 0
    for w1 in self.new_training_set:
      for w2 in self.new_training_set[w1]:
        self._add_to_training_set(w1, w2, self.new_training_set[w1][w2])
    self.new_training_set.clear()
    self.eval.clear()
    
    if ( old_set == self.components_tf):
      return True
    else:
      return False

#==============================================================================
# EVALUATION                   

  def _eval(self, data, rhymes):
    '''Evaluate current poem'''
    for i, val in enumerate(data):
      if 'class' in data[i]:
        data[i]['class'].add('*ALL*')
      else:
        data[i]['class'] = set('*ALL*')
        
      for c in data[i]['class']:  
        self.eval[c]['p'] += len( rhymes[i] )
        self.eval[c]['tp'] += len( data[i]['gold'].intersection( rhymes[i]) )
        self.eval[c]['r'] += len( data[i]['gold'] )
        
        if len(data[i]['gold']) > 0 or len(rhymes[i]) > 0:
          self.eval[c]['tot1'] += 1
        
        if len(data[i]['gold']) > 0:
          self.eval[c]['tot2'] += 1
          if len(rhymes[i]) > 0:
            correct = len ( data[i]['gold'].intersection( rhymes[i] ) )
            self.eval[c]['av_prec'] += correct / len( rhymes[i] )
            self.eval[c]['av_rec'] += correct / len( data[i]['gold'] )
              
  def eval_info(self):
    '''Get evaluation of entire tagging'''
    log = defaultdict(lambda : defaultdict(dict))
    for c in self.eval:
      if self.eval[c]['p'] > 0 and self.eval[c]['r'] > 0:
        log[c]['all']['prec'] = self.eval[c]['tp'] / self.eval[c]['p']
        log[c]['all']['rec']  = self.eval[c]['tp'] / self.eval[c]['r']        
        log[c]['av1']['prec'] = self.eval[c]['av_prec'] / self.eval[c]['tot1']
        log[c]['av1']['rec']  = self.eval[c]['av_rec'] / self.eval[c]['tot1']
        log[c]['av2']['prec'] = self.eval[c]['av_prec'] / self.eval[c]['tot2']
        log[c]['av2']['rec']  = self.eval[c]['av_rec'] / self.eval[c]['tot2']

        for x in log[c]:
          log[c][x]['F1'] = 2 * log[c][x]['prec'] * log[c][x]['rec']
          log[c][x]['F1'] /= log[c][x]['prec'] + log[c][x]['rec']
        
    return log
       
#==============================================================================
# MAIN FUNCTIONS

def connect_db():
  '''Connect DB'''
  dir = os.path.dirname(os.path.realpath(sys.argv[0]))
  db = sqlite3.connect( os.path.join( dir, 'db', 'rhymes.db' ), check_same_thread=False )
  db.row_factory = sqlite3.Row      
  return db

def query_db(query):
  '''Send query to DB'''
  cursor = db.execute(query)
  return cursor

def get_authors(lang):
  '''Get list of authors and periods'''
  cursor = query_db( "SELECT * FROM authors WHERE language='" + lang + "'" )
  authors = dict()
  periods = dict()
  for row in cursor:
    authors[ row['author_id'] ] = row['author_name']
    periods[ row['author_id'] ] = row['period']
  return authors, periods
    
def get_poems(author_id):
  '''Get list of poems'''
  cursor = query_db( "SELECT * FROM main WHERE author_id='" + str(author_id) + "'" )
  poems = defaultdict(list)
  for row in cursor:
    poems[ row['poem_id'] ].append( { 'word':   row['word'], 
                                      'sampa':  row['sampa'], 
                                      'stanza': row['stanza_id'] } )
  return poems

def store_eval(tagger, message, evaluation, lang):
  '''Write evaluation to log-file'''
  dir = os.path.dirname(os.path.realpath(sys.argv[0]))
  s = tagger.settings
  filename = ( lang + 
              "_st" + str( s['stanza_limit'] ) +
              "_S" + str( s['t_score_min'] ) +
              "_F" + str( s['frequency_min'] ) +
              "_w" + str( s['window'] ) +
              "_g" + str( s['ngram'] ) +
              "_stress" + str( s['stress'] ) +
              ".log"
             )
  with open( os.path.join( dir, 'eval', filename), 'w' ) as f:
    f.write( json.dumps(tagger.settings, indent=2, sort_keys=True ) )
    f.write( "\n-----------------------\n{}\n-----------------------\n".format(message))
    f.write( json.dumps(evaluation, indent=2, sort_keys=True ) )
  print("\n{}".format(message))

#==============================================================================
# MAIN 

if __name__ == '__main__':   
  lang = 'fr'             # Language to work with
  max_iter = 20           # Maximum number of iteration to perform
  tagger = RhymeTagger()  
  db = connect_db()       

  # Get list of authors
  authors, periods = get_authors(lang)
    
  # Get poems and count frequencies
  print ("  Counting frequencies in: ", end='')
  sys.stdout.flush()
  
  for author_id in authors:
    print ("[{}]".format(authors[author_id]), end='')
    sys.stdout.flush()
    poems = get_poems(author_id)  
    for key in poems:
      tagger.initial_frequencies(poems[key])

  # Get collocations
  types, tokens = tagger.collocations()
  print("\n  Training set built: r.types = {}, r.tokens = {}".format(types, tokens), end='')
  sys.stdout.flush()
  
  # Tagging iterations
  for iteration in range(1, max_iter+1):
    if iteration == 1:
      tagger.settings['ngram'] = False
    else:
      tagger.settings['ngram'] = True
    
    # Get poems and perform tagging
    print ("\n  Tagging #{}:".format(iteration), end='' )
    sys.stdout.flush()
      
    for author_id in authors:
      cursor = query_db( "SELECT * FROM main WHERE author_id='" + str(author_id) + "'" )
      poems.clear()  
      id0 = dict()
      for row in cursor:
        if row['poem_id'] not in id0:
          id0[ row['poem_id'] ] = row['line_id']
        gold_list = set()
        if row['gold']:
          gold_list = set( map( lambda x: int(x) - int(id0[ row['poem_id'] ]), row['gold'].split('#') ) )
        poems[ row['poem_id'] ].append({ 'word':   row['word'], 
                                         'sampa':  row['sampa'], 
                                         'stanza': row['stanza_id'], 
                                         'gold':   gold_list,
                                         'class':  set( [ periods[author_id] ] ) })
  
      # Perform tagging
      print ("[{}]".format(authors[author_id]), end='' )
      sys.stdout.flush()
      for key in poems:
        tagger.tagging(poems[key])
        
    # Print current evaluation
    print("\n  EVAL:"),
    evaluation = tagger.eval_info()
    print ( json.dumps(evaluation, indent=2, sort_keys=True ) )

    # Rebuild training set
    equilibrium = tagger.rebuild_training_set()
    if equilibrium:
      message = "TAGGING #" + str(iteration) + ": SYSTEM HAS REACHED EQUILIBRIUM"
      store_eval(tagger, message, evaluation, lang )
      break
    elif iteration == max_iter:
      message = "TAGGING #" + str(iteration) + ": SYSTEM HAS NOT REACHED EQUILIBRIUM"
      store_eval(tagger, message, evaluation, lang )
 
