package Rhyme::Tagger;

##############################################################################
# MODULES
#

use utf8;
use strict;
use warnings;
use File::Basename;
use XML::Simple qw(:strict);
use Encode qw(decode encode);
use Deep::Encode;
use Test::More;
use Carp;
use Data::Dumper;
$Data::Dumper::Sortkeys = 1;
  
##############################################################################
# CONSTRUCTOR
#

sub new {
  my ( $self, $settings ) = @_;
  $self = {
		'settings' => $settings
	};
  bless $self;
	$self->errorHandling();
  return $self;
}

##############################################################################
# ERROR HANDLING
#

sub errorHandling {
	my $self = shift;

	# Language not set or unkown
	if ( $self->{'settings'}->{'lang'} !~ /^en$|^cs$|^fr$/ ) {
		croak "\nThe script has to be run with an argument specifying language. Possible values: -en | -fr | -cs\n\n";
	}	
}

##############################################################################
# LOAD XML FILES
#
# Read the content of a dir and return all .xml files' names
#

sub loadXmlFiles {
	my ( $self, $xmlDir ) = @_;

	# Open directory & read its content
	opendir(DIR, $xmlDir);
	my @files = readdir(DIR); 
	close DIR;

	# Drop all but .xml files
	@files = grep(/\.xml/, @files);

	# Sort by alphabetical order
	@files = sort { $a cmp $b } @files; 

	# Return files
	return ( \@files );
}

##############################################################################
# LOOP XML
#
#	Loop XML files and call requested method 
#

sub loopXml {
	my ( $self, $method, $xmlDir, $xmlFiles, $opt1, $opt2 ) = @_;
	my $result;
	print "\n\n--------------- $method ------------\n\n";

	# Delete former evalution 
	if ( $method eq "findRhymes" ) {
		delete $self->{'eval'};
	}

	# Loop through XML files
	for ( my $i = 0; $i < @$xmlFiles; $i++ ) {

		# Print info to terminal
		print " [$xmlFiles->[$i]]";

		# XML file to perl object
		my $parsedXML = XMLin( "$xmlDir/$xmlFiles->[$i]", KeyAttr => { }, ForceArray => 1 );
		deep_utf8_encode( $parsedXML );

		# Call the requested method
		$result = $self->$method( $parsedXML, $result, $opt1, $opt2, $xmlFiles->[$i] );

	} 

	return $result;
}

##############################################################################
# GET COLLOCATIONS
#
# (1) Count the corpus size
# (2) Count the frequency of line-final words
# (3) Count the frequency of collocations
#

# ----- Search for collocations in a book -----

sub collocations {
	my ( $self, $parsedXML ) = @_;

	# Loop through poems
	for ( my $poem = 0; $poem < @{ $parsedXML->{'poem'} }; $poem++ ) {
		# Loop through poem's lines
		for ( my $line1 = 0; $line1 < @{ $parsedXML->{'poem'}->[$poem]->{'line'} }; $line1++ ) {
			my $word1 = $parsedXML->{'poem'}->[$poem]->{'line'}->[$line1];

			# Add 1 to corpus size & token's frequency
			$self->{'collocations'}->{'corpusSize'}++;
			$self->{'collocations'}->{'freqs'}->{ $word1->{'finToken'} }++;

			# Loop [frame1] lines back 
			for ( my $line2 = $line1 - $self->{'settings'}->{'frame1'}; $line2 <= $line1-1; $line2++ ) {
				# If not before beggining of the poem
				if ( $line2 >= 0 ) {
					my $word2 = $parsedXML->{'poem'}->[$poem]->{'line'}->[$line2];
					$self->_storeCollocations( $word1, $word2 );				
				}
			}
		}
	}
}

# -----  Store the collocations in $self -----

sub _storeCollocations {
	my ( $self, $line1, $line2 ) = @_;
	my $token1 = $line1->{'finToken'};
	my $token2 = $line2->{'finToken'};
	my $sampa1 = $line1->{'finSampa'};
	my $sampa2 = $line2->{'finSampa'};

	# If both words are not the same
	if ( $token1 ne $token2 ) {
		# Store pair ( token1 -> token2 )
		$self->{'collocations'}->{'pairs'}->{$token1}->{$token2}++;
		$self->{'collocations'}->{'pairs'}->{$token2}->{$token1}++;

		# Store token1's SAMPA
		$self->{'collocations'}->{'sampa'}->{$token1} = $sampa1;
		$self->{'collocations'}->{'sampa'}->{$token2} = $sampa2;
	}
}

##############################################################################
# BUILD INITIAL TRAINING SET
#
# Pick all collocations which pass the test ( minimum score, minimum frequency )
#

# ----- Loop through collocations -----
 
sub trainingRhymeSet {
	my ( $self ) = @_;	
	my $rhymeSet;

	# Loop tokens...
	foreach my $token1 ( keys %{ $self->{'collocations'}->{'pairs'} } ) {
		# ... and its pairs
		foreach my $token2 ( keys %{ $self->{'collocations'}->{'pairs'}->{$token1} } ) {

			# Frequency of token1
			my $fx = $self->{'collocations'}->{'freqs'}->{$token1};
			# Frequency of token2
			my $fy = $self->{'collocations'}->{'freqs'}->{$token2};
			# Frequency of token1 <=> token2 collocation
			my $fxy = $self->{'collocations'}->{'pairs'}->{$token1}->{$token2};
			# Corpus size
			my $n = $self->{'collocations'}->{'corpusSize'};
			# Collocations score
			my $score = $self->_collocationScore( $fx, $fy, $fxy, $n );

			if ( $score > 0 ) {
				unless ( defined $rhymeSet->{'pairs'}->{$token1}->{$token2} ) {
					$rhymeSet->{'size'}++;
				}
				$rhymeSet->{'pairs'}->{$token1}->{$token2} = 1;
			}
		}
	}

	# Return initial training set
	return $rhymeSet;
}

# ----- Count collocation's score -----

sub _collocationScore {
	my ( $self, $fx, $fy, $fxy, $n ) = @_;
	my $score = 0;

	# T-score
	if ( $self->{'settings'}->{'test'} eq "t") {
		$score = ( $fxy - ( ( $fx * $fy ) / $n ) ) / ( $fxy ** 0.5 );
	# MI-score
	} elsif ( $self->{'settings'}->{'test'} eq "MI" ) {
		$score =  log ( ( $n * $fxy ) / ( $fx * $fy ) ) / log(2);
	# Dice
	} elsif ( $self->{'settings'}->{'test'} eq "dice" ) {
		$score = ( 2 * $fxy ) / ( $fx + $fy );
	} 

	# If minimum frequency & minimum score => return $score, otherwise => return 0
	if ( ( $fxy >= $self->{'settings'}->{'minF'} ) && ( $score >= $self->{'settings'}->{'minS'} ) ) {
		return $score;
	} else {
		return 0;
	}
}

##############################################################################
# COMPONENTS' FREQUENCIES
#
# Count the relative frequencies of line-final n-grams and relevant line-final sound clusters in the corpus
#

sub componentsFrequencies {
	my ( $self ) = @_;	
	my ( $f, $n, $fRelative );

	# Loop tokens...
	foreach my $token ( keys %{ $self->{'collocations'}->{'sampa'} } ) {

		# Get token's final n-gram
		my $ngram = $self->_nGram( $token, $self->{'settings'}->{'ngram'} );

		# Count n-gram's occurrence
		$f->{'ngrams'}->{ $ngram }++;
		$n->{'ngrams'}++;

		# Get relevant sound clusters
		my $sampa = $self->{'collocations'}->{'sampa'}->{$token};
		my $sets = $self->relevantClusters( $sampa );

		# Count clusters' occurrences
		foreach my $type ( keys %{ $sets } ) {
			foreach my $i ( sort { $a <=> $b } keys %{ $sets->{$type} } ) {
				$f->{'clusters'}->{$type}->{$i}->{ $sets->{$type}->{$i} }++;
				$n->{'clusters'}->{$type}->{$i}++;
			}
		}		
	}

	# Count n-grams' relative frequencies
	foreach my $ngram ( keys %{ $f->{'ngrams'} } ) {
		$fRelative->{'ngrams'}->{$ngram} = $f->{'ngrams'}->{$ngram} / $n->{'ngrams'};
	}

	# Count clusters' relative frequencies
	foreach my $type ( keys %{ $f->{'clusters'} } ) {
		foreach my $i ( keys %{ $f->{'clusters'}->{$type} } ) {
			foreach my $c ( keys %{ $f->{'clusters'}->{$type}->{$i} } ) {
				$fRelative->{'clusters'}->{$type}->{$i}->{$c} = $f->{'clusters'}->{$type}->{$i}->{$c} / $n->{'clusters'}->{$type}->{$i};
			}
		}
	}

	# Store relative frequencies in $self
	$self->{'componentsFrequencies'} = $fRelative;

	# Return n-gram's & clusters' relative frequencies
	return $fRelative;
}

##############################################################################
# RHYME PROBABILITIES
#
# Count the probabilities of rhyme pairs constituents
#

sub rhymeProbs {
	my ( $self, $trainingSet ) = @_;	
	my ( $f, $n, $rhymeProbs );

	# Loop tokens...
	foreach my $token1 ( keys %{ $trainingSet->{'pairs'} }  ) {
		my $sampa1 = $self->{'collocations'}->{'sampa'}->{$token1};

		# ... and its pairs
		foreach my $token2 ( keys %{ $trainingSet->{'pairs'}->{$token1} } ) {
			my $sampa2 = $self->{'collocations'}->{'sampa'}->{$token2};

			# Get tokens final n-grams
			my $ngram1 = $self->_nGram($token1, $self->{'settings'}->{'ngram'} );
			my $ngram2 = $self->_nGram($token2, $self->{'settings'}->{'ngram'} );

			# Count ngrams cooccurrence
			$f->{'ngrams'}->{$ngram1}->{$ngram2}++;
			$n->{'ngrams'}->{$ngram1}++;

			# Get relevant sound clusters
			my $clusters1 = $self->relevantClusters( $sampa1 );
			my $clusters2 = $self->relevantClusters( $sampa2 );

			# Count clusters cooccurrence
			foreach my $type ( keys %{ $clusters1 } ) {
				foreach my $i ( sort { $a <=> $b } keys %{ $clusters1->{$type} } ) {
					if ( defined $clusters2->{$type}->{$i} ) {
						$f->{'clusters'}->{$type}->{$i}->{ $clusters1->{$type}->{$i} }->{ $clusters2->{$type}->{$i} }++;
						$n->{'clusters'}->{$type}->{$i}->{ $clusters1->{$type}->{$i} }++;
					}
				}
			}		
		}
	}	

	# Count probability ( rhyme | clusters cooccurrence )
	foreach my $type ( keys %{ $f->{'clusters'} } ) {
		foreach my $i ( keys %{ $f->{'clusters'}->{$type} } ) {
			foreach my $c1 ( keys %{ $f->{'clusters'}->{$type}->{$i} } ) {
				foreach my $c2 ( keys %{ $f->{'clusters'}->{$type}->{$i}->{$c1} } ) {
					my $prob1 = $f->{'clusters'}->{$type}->{$i}->{$c1}->{$c2} / $n->{'clusters'}->{$type}->{$i}->{$c1};
					my $prob0 = $self->{'componentsFrequencies'}->{'clusters'}->{$type}->{$i}->{$c2};
					my $probR = $prob1 / ( $prob1 + $prob0 );
					$rhymeProbs->{'clusters'}->{$type}->{$i}->{$c1}->{$c2} = $probR;
				}
			}
		}
	}

	# Count probability ( rhyme | n-grams cooccurrence )
	foreach my $g1 ( keys %{ $f->{'ngrams'} } ) {
		foreach my $g2 ( keys %{ $f->{'ngrams'}->{$g1} } ) {
			my $prob1 = $f->{'ngrams'}->{$g1}->{$g2} / $n->{'ngrams'}->{$g1};
			my $prob0 = $self->{'componentsFrequencies'}->{'ngrams'}->{$g2};
			my $probR = $prob1 / ( $prob1 + $prob0 );
			$rhymeProbs->{'ngrams'}->{$g1}->{$g2} = $probR;
		}
	}

	return $rhymeProbs;
}

##############################################################################
# N-GRAM
#
# Pick final n-gram from token
#

sub _nGram{
	my ( $self, $token, $length ) = @_;	
	my $ngram = decode('UTF-8', $token);
	my $position = ( length $ngram ) - $length; 
	$ngram = substr( $ngram, $position, $length );
	$ngram = encode('UTF-8', $ngram);
	return $ngram;
}

##############################################################################
# PICK RELEVANT CLUSTERS
#
# Pick clusters that are relevant according to settings
#

sub relevantClusters {
	my ( $self, $sampa ) = @_;

	# Define sounds forming syllable peaks
	my $peaks = "[iye2E9\{a\&IYU1\}\@836Mu7oVOAQ0\=]";

	# Split SAMPA into array
	my @split = split ( " ", $sampa );
	
	# Clusters + cluster index
	my $clusters;
	my $ci = 0;
	
	# Loop sampa backwards
	RELEVANTS: for ( my $i = ( scalar @split ) - 1; $i >= 0; $i-- ) {

		# Stress symbol "'"
		if ( $split[$i] =~ /\'/ ) {
			# If stress relevant 
			if ( $self->{'settings'}->{'stress'} == 1 ) {
				# Delete consonant cluster after stress
				delete $clusters->{'con'}->{$ci};
				# Quit loop
				last RELEVANTS;
			}

		# Syllable peak symbol ( vowel | syllabic consonant )
		} elsif ( $split[$i] =~ /$peaks/ ) {
			$clusters->{'vow'}->{$ci} .= $split[$i];
			# Define empty consonant cluster if do not exists
			unless ( defined $clusters->{'con'}->{$ci} ) {
				$clusters->{'con'}->{$ci} = "null";
			}
			# Increase cluster index
			$ci++;
			# Set index >= length => quit loop
			if ( $ci >= $self->{'settings'}->{'matchLen'} ) {
				last RELEVANTS;
			}

		# Consonant symbol
		} else {
			$clusters->{'con'}->{$ci} .= $split[$i];
		}
	}

	return $clusters;
}

##############################################################################
# GOLD RHYMES LIST
#
# 

sub goldRhymesList {
	my ( $self, $parsedXML ) = @_;
	# Loop through poems
	for ( my $poem = 0; $poem < @{ $parsedXML->{'poem'} }; $poem++ ) {
		# Loop through poem's lines (1)
		for ( my $line1 = 0; $line1 < @{ $parsedXML->{'poem'}->[$poem]->{'line'} }; $line1++ ) {
			my $word1 = $parsedXML->{'poem'}->[$poem]->{'line'}->[$line1];
			# Loop through poem's lines (2)
			for ( my $line2 = 0; $line2 < @{ $parsedXML->{'poem'}->[$poem]->{'line'} }; $line2++ ) {
				my $word2 = $parsedXML->{'poem'}->[$poem]->{'line'}->[$line2];
				# If $word1 & $word2 has same index => store the pair
				if ( ( $line1 != $line2 ) && ( $word1->{'rhymeScheme'} eq $word2->{'rhymeScheme'} ) && ( $word1->{'rhymeScheme'} ne "X" ) ) {
					my $token1 = $word1->{'finToken'};
					my $token2 = $word2->{'finToken'};
					$self->{'goldRhymesList'}->{$token1}->{$token2}++;
				}
			}
		}
	}

return $self->{'goldRhymesList'};
}

##############################################################################
# FIND RHYMES ( TAGGING )
#
# 
#

sub findRhymes {
	my ( $self, $parsedXML, $newTrainingSet, $rhymeProbs, $ortho, $fileName  ) = @_;

	# Loop through poems
	for ( my $poem = 0; $poem < @{ $parsedXML->{'poem'} }; $poem++ ) {
		my ( $golden, $tagged );

		# Loop through poem's lines (1)
		for ( my $line1 = 0; $line1 < @{ $parsedXML->{'poem'}->[$poem]->{'line'} }; $line1++ ) {
			my $word1 = $parsedXML->{'poem'}->[$poem]->{'line'}->[$line1];

			# Loop through lines preceding (1)
			for ( my $line2 = 0; $line2 < $line1; $line2++ ) {
				my $word2 = $parsedXML->{'poem'}->[$poem]->{'line'}->[$line2];

				# If both lines belong to one stanza || stanzaic is set to 0	
				if ( ( $word1->{'stanzaId'} == $word2->{'stanzaId'} ) || ( $self->{'settings'}->{'stanzaic'} == 0 ) ) {

					# ----- GET GOLDEN STANDARD -----
					# If $word1 & $word2 has same non-X index => store the pair
					if ( ( $word1->{'rhymeScheme'} eq $word2->{'rhymeScheme'} ) 
					&&   ( $word1->{'rhymeScheme'} ne "X" ) ) {
#					&&   ( $word1->{'finToken'} ne $word2->{'finToken'} ) ) {			
						$golden->{$line1}->{$line2} = 1;
						$golden->{$line2}->{$line1} = 1;

					}

					# ----- PERFORM TAGGING -----
					# If $line2 is in the selected frame
					if ( ( $line1 - $line2 ) <= $self->{'settings'}->{'frame2'} ) {
						my $ngram1 = $self->_nGram( $word1->{'finToken'}, $self->{'settings'}->{'ngram'} );
						my $ngram2 = $self->_nGram( $word2->{'finToken'}, $self->{'settings'}->{'ngram'} );

						# Get rhyme scores
						my ( $scoreClusters, $scoreNgrams ) = $self->_rhymesScore( $word1->{'finSampa'}, $word2->{'finSampa'}, $ngram1, $ngram2, $rhymeProbs );				
	
						# Disregard score based on ngrams if $ortho == 1
						unless ( $ortho == 1 ) {
							$scoreNgrams = 0;
						}

						# Tag rhyme if one of scores is greater than minimum value
						if ( $scoreClusters >= $self->{'settings'}->{'minP'} ) {
							$tagged->{$line1}->{$line2} = 1;
							$tagged->{$line2}->{$line1} = 1;

							# Tag distant rhymes
							foreach my $line3 ( keys %{ $tagged->{$line2} } ) {
								if ( $line1 != $line3 ) {
									$tagged->{$line1}->{$line3} = 1;
									$tagged->{$line3}->{$line1} = 1;
								}
							}

							# Increase new training set size if rhyme has not been found yet
							unless ( defined $newTrainingSet->{'pairs'}->{ $word1->{'finToken'} }->{ $word2->{'finToken'} } ) {
								$newTrainingSet->{'size'}++;
							}

							# Put rhyme in new training set
							$newTrainingSet->{'pairs'}->{ $word1->{'finToken'} }->{ $word2->{'finToken'} } = 1;
						}
					}
				}
			}
		}

		# Loop through poem's lines (1)
		for ( my $line1 = 0; $line1 < @{ $parsedXML->{'poem'}->[$poem]->{'line'} }; $line1++ ) {
			my $word1 = $parsedXML->{'poem'}->[$poem]->{'line'}->[$line1];


			# Loop through lines preceding (1)
			for ( my $line2 = 0; $line2 < $line1; $line2++ ) {
				my $word2 = $parsedXML->{'poem'}->[$poem]->{'line'}->[$line2];


				# If both lines belong to one stanza || stanzaic is set to 0	
				if ( ( $word1->{'stanzaId'} == $word2->{'stanzaId'} ) || ( $self->{'settings'}->{'stanzaic'} == 0 ) ) {

					# ----- PERFORM TAGGING -----
					# If $line2 is in the selected frame
					if ( ( $line1 - $line2 ) <= $self->{'settings'}->{'frame2'} ) {
						my $ngram1 = $self->_nGram( $word1->{'finToken'}, $self->{'settings'}->{'ngram'} );
						my $ngram2 = $self->_nGram( $word2->{'finToken'}, $self->{'settings'}->{'ngram'} );

						# Get rhyme scores
						my ( $scoreClusters, $scoreNgrams ) = $self->_rhymesScore( $word1->{'finSampa'}, $word2->{'finSampa'}, $ngram1, $ngram2, $rhymeProbs );				
	
						# Disregard score based on ngrams if $ortho == 1
						unless ( $ortho == 1 ) {
							$scoreNgrams = 0;
						}

						# Tag rhyme if one of scores is greater than minimum value
						if ( ( $scoreNgrams >= $self->{'settings'}->{'minPngram'} ) 
						&&   ( ! defined $tagged->{$line1} )
						&&   ( ! defined $tagged->{$line2} ) ) {
							$tagged->{$line1}->{$line2} = 1;
							$tagged->{$line2}->{$line1} = 1;

							# Increase new training set size if rhyme has not been found yet
							unless ( defined $newTrainingSet->{'pairs'}->{ $word1->{'finToken'} }->{ $word2->{'finToken'} } ) {
								$newTrainingSet->{'size'}++;
							}

							# Put rhyme in new training set
							$newTrainingSet->{'pairs'}->{ $word1->{'finToken'} }->{ $word2->{'finToken'} } = 1;
						}
					}
				}
			}
		}



		# ----- TAGGING EVALUATION -----
		# Poems' period
		my $period = $parsedXML->{'poem'}->[$poem]->{'period'};
		my $author = $parsedXML->{'poem'}->[$poem]->{'author'};
		my $poemId = $parsedXML->{'poem'}->[$poem]->{'id'};

		# Loop through lines
		for ( my $line1 = 0; $line1 < @{ $parsedXML->{'poem'}->[$poem]->{'line'} }; $line1++ ) {

			# Precision
			foreach my $line2 ( keys %{$tagged->{$line1} } ) {
				$self->{'eval'}->{$period}->{'positives'}++;
				$self->{'eval'}->{'*ALL'}->{'positives'}++;
				if ( defined $golden->{$line1}->{$line2} ) {
					$self->{'eval'}->{$period}->{'truePositives'}++;
					$self->{'eval'}->{'*ALL'}->{'truePositives'}++;
				}
			} 

			# Recall
			foreach my $line2 ( keys %{$golden->{$line1} } ) {
				$self->{'eval'}->{$period}->{'relevant'}++;
				$self->{'eval'}->{'*ALL'}->{'relevant'}++;
			} 
		}

		#push ( @{ $self->{'completeResults'} }, $tagged );
		$self->{'completeResults'}->{$fileName}->{$poemId} = $tagged;
	}

	# Store precision and recall in $self
	foreach my $period ( keys %{ $self->{'eval'} } ) {
		my $tp = $self->{'eval'}->{$period}->{'truePositives'};
		my $p = $self->{'eval'}->{$period}->{'positives'};
		my $r = $self->{'eval'}->{$period}->{'relevant'};

		my $precision = $tp / $p;
		my $recall = $tp / $r;

		$self->{'eval'}->{$period}->{'precision'} = $precision;
		$self->{'eval'}->{$period}->{'recall'} = $recall;
		$self->{'eval'}->{$period}->{'fScore'} = ( 2 * $precision * $recall ) / ( $precision + $recall );
	}

	# Return new training set
	return $newTrainingSet;
}

##############################################################################
# RHYME SCORES
#
# Get the probabilities P(rhyme|clusters) & P(rhyme|ngram)
#

sub _rhymesScore {
	my ( $self, $sampa1, $sampa2, $ngram1, $ngram2, $rhymeProbs ) = @_;
	my ( $scoreClusters, $scoreNgrams );

	# Get relevant clusters
	my $clusters1 = $self->relevantClusters( $sampa1 );
	my $clusters2 = $self->relevantClusters( $sampa2 );

	# Count score based on clusters
	my $pProd = 1;
	my $qProd = 1;
	
	# Loop through cluster types
	foreach my $type ( keys %{ $clusters1 } ) {
		# Loop through cluster positions
		foreach my $i ( sort { $a <=> $b } keys %{ $clusters1->{$type} } ) {
			# If cluster exists
			if ( defined $clusters2->{$type}->{$i} ) {
				my $c1 = $clusters1->{$type}->{$i};
				my $c2 = $clusters2->{$type}->{$i};
				my $p;

				# If P(rhyme|clusters) is known
				if ( defined $rhymeProbs->{'clusters'}->{$type}->{$i}->{$c1}->{$c2} ) {
					$p = $rhymeProbs->{'clusters'}->{$type}->{$i}->{$c1}->{$c2};
 				# If P(rhyme|clusters) is unknown and clusters are the same
				} elsif ( $c1 eq $c2 ) {
					$p = 0.9;
				# P(rhyme|clusters) is unknown and clusters are different
				} else {
					$p = 0.0001;
				}

				# Probabilities product
				my $q = 1 - $p;
				$pProd *= $p;
				$qProd *= $q;
			}
		}
	}
	
	# P(rhyme|clusters) combined probabilty
	if ( ( $pProd + $qProd ) > 0 ) {
		$scoreClusters = $pProd / ( $pProd + $qProd );
	} else {
		$scoreClusters = 0;
	}

	# Count score based on nGrams
	if ( defined $rhymeProbs->{'ngrams'}->{$ngram1}->{$ngram2} ) {
		$scoreNgrams = $rhymeProbs->{'ngrams'}->{$ngram1}->{$ngram2};
	} else {
		$scoreNgrams = 0;
		}

	# Return probabilities
	return ( $scoreClusters, $scoreNgrams );
}

sub storeResults {
	my ( $self, $parsedXML, $empt1 , $path, $empt2 , $fileName  ) = @_;
	my $output;
	my $outputName = $fileName;
	$outputName =~ s/\.xml$/\.txt/;

	# Create directory [$lang] if it does not exists
	mkdir "$path/$self->{settings}->{lang}" unless -d "$path/$self->{settings}->{lang}";


	# Loop through poems
	for ( my $poem = 0; $poem < @{ $parsedXML->{'poem'} }; $poem++ ) {
		my $golden;
		my $poemId = $parsedXML->{'poem'}->[$poem]->{'id'};
		my $poemIdInt = $poemId;
		$poemIdInt =~ s/\-|POEM//g;
		$output->{'id'}->{$poemIdInt} = $poemId;
	
		# Loop through poem's lines (1)
		for ( my $line1 = 0; $line1 < @{ $parsedXML->{'poem'}->[$poem]->{'line'} }; $line1++ ) {
			my $word1 = $parsedXML->{'poem'}->[$poem]->{'line'}->[$line1];

			# Loop through lines preceding (1)
			for ( my $line2 = 0; $line2 < $line1; $line2++ ) {
				my $word2 = $parsedXML->{'poem'}->[$poem]->{'line'}->[$line2];

				# If both lines belong to one stanza || stanzaic is set to 0	
				if ( ( $word1->{'stanzaId'} == $word2->{'stanzaId'} ) || ( $self->{'settings'}->{'stanzaic'} == 0 ) ) {

					# ----- GET GOLDEN STANDARD -----
					# If $word1 & $word2 has same non-X index => store the pair
					if ( ( $word1->{'rhymeScheme'} eq $word2->{'rhymeScheme'} ) 
					&&   ( $word1->{'rhymeScheme'} ne "X" ) ) {
#					&&   ( $word1->{'finToken'} ne $word2->{'finToken'} ) ) {			
						$golden->{$line1}->{$line2} = 1;
						$golden->{$line2}->{$line1} = 1;

					}
				}
			}
		}

		for ( my $line1 = 0; $line1 < @{ $parsedXML->{'poem'}->[$poem]->{'line'} }; $line1++ ) {
			$output->{'poem'}->{$poemIdInt} .= "\n [$line1]" . $parsedXML->{'poem'}->[$poem]->{'line'}->[$line1]->{'finToken'}
			. "\n\t[G] " . join ( " " , sort {$a cmp $b} keys %{ $golden->{$line1} } )
			. "\n\t[T] " . join ( " " , sort {$a cmp $b} keys %{ $self->{'completeResults'}->{$fileName}->{$poemId}->{$line1} } );
		}
	}

	# Create / open file
	open OUT, ">$path/$self->{settings}->{lang}/$outputName";

	# Write the results
	foreach my $id ( sort { $a <=> $b } keys %{ $output->{'poem'} } ) {
		print OUT "\n\n=============\n" . $output->{'id'}->{$id} . "\n=============\n\n" . $output->{'poem'}->{$id};
	}

	# Close file
	close OUT;
}


1
