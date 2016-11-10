#!/usr/bin/perl
$| = 1;

#	************************************************************************************************* MODULES

use FindBin;
use lib "$FindBin::Bin/lib";
use lib "/home/plechac/perl5/lib/perl5/";
use lib "/home/plechac/perl5/man/man3/";
use strict;
use warnings;
use XML::Simple qw(:strict);
use Rhyme::Tagger;
use Test::More;
use Data::Dumper;
$Data::Dumper::Sortkeys = 1;

#	************************************************************************************************* SETTINGS

# Language: "-cs" | "-en" | "-fr"
my $lang = substr( $ARGV[0], 1, 2 );	

my $settings = {
	'lang'      =>  $lang,

	'test' 			=> 	't',			# Collocation measure: "t" (t-score) | "mi" (MI-score) | "dice" 
	'minS' 			=> 	4,				# Minimum score of collocation to be taken into account
	'minF' 			=> 	2,				# Minimum absolute frequency of collocation to be taken into account 
	'minP' 			=> 	0.95,			# Minimum rhyme probability to be tagged

	'frame1'		=>	4,				# How many lines to look for collocations (both back & forward)
	'frame2'		=>	4, 				# How many lines to look for rhymes (both back & forward)

	'matchLen'	=>	2,				# How many syllables should match
	'stress'		=>	1,				# 0 (disregard stress) | 1 (take into account only syllables after last stress)
	'ngram'			=>	3,				# How many line final characters to take into account when comparing ortography
	'minPngram' => 	0.95,			# Minimum rhyme probability to be tagged
	
	'tagIter'		=>  20,				# How many tagging iterations should be performed
	'stanzaic'	=>  1					# Disregard rhymes between stanzas ? ( 0: no, 1: yes ) 
};

#	************************************************************************************************* GET COLLOCATIONS

# Parent directory
my $parent = "$FindBin::Bin";

# XML files directory
my $xmlDir = "$parent/data/$lang";

# New Tagger
my $tagger = Rhyme::Tagger->new( $settings );

# Load XML files names
my $xmlFiles = $tagger->loadXmlFiles( $xmlDir ); 

# Load collocations
$tagger->loopXml( 'collocations', $xmlDir, $xmlFiles );

# Build training rhyme set
my $trainingSet = $tagger->trainingRhymeSet( );

# Get components' frequencies
$tagger->componentsFrequencies( );

#	************************************************************************************************* FIND RHYMES

# Open output file
open FILE, ">$parent/results/taggingEvaluation_$lang" . "_stanzaic" . $settings->{'stanzaic'} . ".txt";

# Print initial setting to file
print FILE "\n\n---------------------------------------------------------------------------";
print FILE "\n                          SETTINGS ";
print FILE "\n---------------------------------------------------------------------------";
print FILE "\n" . Dumper ( $settings );
print FILE "\n---------------------------------------------------------------------------\n";

# First tagging loop disregards n-grams
my $ortho = 0;
my $tagged;
my $recentTagged;

# Tagging loop
TAGGINGLOOP: foreach my $taggingLoop ( 1..$settings->{'tagIter'} ) {

	# Equilibrium reached
	if ( ( eq_hash( $tagged, $recentTagged ) ) && ( $taggingLoop > 1 ) ) {
		print "\n\n===========================================================================";
		print "\n\n                   SYSTEM HAS REACHED EQUILIBRIUM";
		print "\n\n===========================================================================";
		last TAGGINGLOOP;
	}

	# Take n-grams into account after first iteration
	if ( $taggingLoop >= 2 ) {
		$ortho = 1;
	}

	# Get rhyme probs
	my $rhymeProbs = $tagger->rhymeProbs( $trainingSet );

	# Print training set size (terminal)
	print "\n TRAINING SET BUILT  ( N = " . $trainingSet->{'size'} . " )";

	# Print training set size (file)
	print FILE "\nTRAINING SET BUILT  ( N = " . $trainingSet->{'size'} . " )";

	# Perform tagging and store new training set
	$tagger->{'completeResults'} = {};
	$trainingSet = $tagger->loopXml( 'findRhymes', $xmlDir, $xmlFiles, $rhymeProbs, $ortho );

	# Store the results
	$recentTagged = $tagged;
	$tagged = $tagger->{'completeResults'};

	# Tagging evaluation (head)
	my $results;
	$results .= "\n\n---------------------------------------------------------------------------";
	$results .= "\n                          TAGGING $taggingLoop ";
	$results .= "\n---------------------------------------------------------------------------";
	$results .= "\n period   |   precision |    recall    |    F-score";
	$results .= "\n---------------------------------------------------------------------------";

	# Tagging evaluation (periods)
	foreach my $period ( sort { $a cmp $b } keys %{ $tagger->{'eval'} } ) {
		my $precision = sprintf( "%.4f", $tagger->{'eval'}->{$period}->{'precision'} );
		my $recall = sprintf( "%.4f", $tagger->{'eval'}->{$period}->{'recall'} );
		my $fScore = sprintf( "%.4f", $tagger->{'eval'}->{$period}->{'fScore'} );
		$results .= "\n $period     |    $precision   |    $recall    |    $fScore";
	}


	# Tagging evaluation (foot)
	$results .= "\n---------------------------------------------------------------------------\n";

	# Print evaluation (terminal)
	print $results;

	# Print evaluation (file)
	print FILE $results;
}

# Close file
close FILE;


$tagger->loopXml( 'storeResults', $xmlDir, $xmlFiles, "$parent/results" );

