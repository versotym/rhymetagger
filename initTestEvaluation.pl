#!/usr/bin/perl
$| = 1;

#	************************************************************************************************* MODULES

use FindBin;
use lib "$FindBin::Bin/lib";
use strict;
use warnings;
use Data::Dumper;
use XML::Simple qw(:strict);
use Rhyme::Tagger;

#	************************************************************************************************* SETTINGS

# Language: "-cs" | "-en" | "-fr"
my $lang = substr( $ARGV[0], 1, 2 ),			

my $settings = {

	'test' 			=> 	't',			# Collocation measure: "t" (t-score) | "mi" (MI-score) | "dice" 
	'frame1'		=>	4,				# How many lines to look for collocations (both back & forward)
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

# Create a list of golden standard rhymes
my $goldRhymesList = $tagger->loopXml( 'goldRhymesList', $xmlDir, $xmlFiles );

# Golden standard size
my $goldSize = 0;
foreach my $token1 ( keys %$goldRhymesList ) {
	foreach my $token2 ( keys %{ $goldRhymesList->{$token1} } ) {
		$goldSize++;
	}
}

# Load collocations
my $collocations = $tagger->loopXml( 'collocations', $xmlDir, $xmlFiles );

# Build initial training sets with different settings and evaluate it
my $evaluation; 

for my $minF ( 1 .. 10 ) {
	for my $minS ( 1 .. 10 ) {
		$tagger->{'settings'}->{'minF'} = $minF;
		$tagger->{'settings'}->{'minS'} = $minS;

		# Info to terminal
		print "\n rhymeSet minFreq = $minF | minScore = $minS";

		# Build rhyme set
		$tagger->initRhymeSet( );

		# Set size & true positives 
		my $truePositives = 0;		
		$evaluation->{$minF}->{$minS}->{'size'} = 0;

		foreach my $token1 ( keys %{ $tagger->{'initRhymeSet'}->{'pairs'} } ) {
			foreach my $token2 ( keys %{ $tagger->{'initRhymeSet'}->{'pairs'}->{$token1} } ) {
				# Set size
				$evaluation->{$minF}->{$minS}->{'size'}++;
				# True positives
				if ( defined $goldRhymesList->{$token1}->{$token2} ) {
					$truePositives++;
				}
			}			
		}

		# Precision
		my $precision;
		if ( $evaluation->{$minF}->{$minS}->{'size'} > 0 ) {
			$precision = $truePositives / $evaluation->{$minF}->{$minS}->{'size'};
		} else {
			$precision = 0; 
		}
		$evaluation->{$minF}->{$minS}->{'precision'} = $precision;

		# Recall
		my $recall = $truePositives / $goldSize;
		$evaluation->{$minF}->{$minS}->{'recall'} = $recall;

		# F-score 		
		if ( ( $precision + $recall ) > 0 ) {
			$evaluation->{$minF}->{$minS}->{'fScore'} = ( 2 * $precision * $recall ) / ( $precision + $recall );
		} else {
			$evaluation->{$minF}->{$minS}->{'fScore'} = 0;
		}
	}
}

# Print results
my $results; 
foreach my $minF ( sort { $a <=> $b } keys %$evaluation ) {
	$results .= "\n---------------------------------------------------------------------------";
	$results .= "\n [minFreq] [minScore]   precision |    recall    |    F-score   |    size";
	$results .= "\n---------------------------------------------------------------------------";
	for my $minS ( sort { $a <=> $b } keys %{ $evaluation->{$minF} } ) {
		my $e1 = sprintf( "%02d", $minF );
		my $e2 = sprintf( "%02d", $minS );
		my $e3 = sprintf( "%.4f", $evaluation->{$minF}->{$minS}->{'precision'} );
		my $e4 = sprintf( "%.4f", $evaluation->{$minF}->{$minS}->{'recall'} );
		my $e5 = sprintf( "%.4f", $evaluation->{$minF}->{$minS}->{'fScore'} );
		$results .= "\n [$e1]      [$e2]         $e3    |    $e4    |    $e5    |    " . $evaluation->{$minF}->{$minS}->{'size'};
	}
}

	$results .= "\n---------------------------------------------------------------------------";
	$results .= "\n [minFreq] [minScore]   precision |    recall    |    F-score  |    size";
	$results .= "\n---------------------------------------------------------------------------\n";

open FILE, ">$parent/results/initTestEvaluation_$lang.txt";
print FILE $results;
close FILE;

print $results;

