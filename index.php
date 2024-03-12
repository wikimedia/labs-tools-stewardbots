<?php
include './vendor/autoload.php';
use Symfony\Component\Process\Process;

// Get git hash
$rev = getGitInfo( [ 'rev-parse', '--short' ] );

// Get git date
$lastModified = getGitInfo( [ 'show', '-s', '--format=format:%cD' ] );

function getGitInfo( $command ) {
	$process = new Process( array_merge( [ 'git' ], $command, [ 'HEAD' ] ) );
	$process->run();

	if ( !$process->isSuccessful() ) {
		throw new ProcessFailedException( $process );
	}

	return $process->getOutput();
}

?>

<!doctype html>
<html>
<head>
	<title>Stewardbots (legacy webservice)</title>
	<link href="/resources/docs.css" rel="stylesheet" type="text/css" />
</head>
<body>
<div>
<div style="border:1px solid #ccc;padding:5px 10px;">
<h1 style="text-align: center;">Stewardbots (legacy webservice)</h1>
<p style="text-align: center;">This is a <a dir="ltr" href="https://wikitech.wikimedia.org/wiki/Portal:Toolforge" target="_self">multi-mantainer project</a> for several <a href="https://meta.wikimedia.org/wiki/IRC/Bots" target="_self">IRC bots</a> and related <a href="https://meta.wikimedia.org/wiki/Stewards" target="_self">steward</a> tools.</p>
</div>
</div>

<h4>List of tools</h4>

<p>The following tool is currently avalaible:</p>

<ul>
	<li><a href="/Elections/elections.php">Elections</a>: Breakdown of the steward elections.</li>
</ul>

<h4>Source code, bug reports and feedback</h4>

<p>Our source code is hosted at <a href="https://gerrit.wikimedia.org/r/admin/repos/labs/tools/stewardbots">Wikimedia Gerrit</a>. Subject to a developer <a href="https://www.mediawiki.org/wiki/Code_of_Conduct">code of conduct</a>, patches and improvements are always welcome. If you find any bug or want to propose a new feature you may file a Task in <a href="https://phabricator.wikimedia.org/maniphest/task/edit/form/1/?projects=stewardbots">Wikimedia Phabricator</a>.</p>

<hr />
<div id="footer">
<div id="f-poweredbyico"><a href="/"><img alt="Powered by Wikimedia Cloud Services" height="31" src="//upload.wikimedia.org/wikipedia/commons/4/46/Powered_by_labs_button.png" style="border:0; float:left; padding: 10px;" title="Powered by Wikimedia Cloud Services" width="88" /></a></div>
<div id="lastmod">This page is based on remote version <?php echo $rev;?> modified <?php echo $lastModified;?>.</div>
<div style="text-align: right;"><a href="https://wikitech.wikimedia.org/wiki/Wikitech:Cloud_Services_Terms_of_use" target="_blank">Terms of Use</a>&nbsp;&middot;&nbsp;<a href="https://www.mediawiki.org/wiki/Code_of_Conduct">Code of Conduct</a>
</div>
</div>
</body>
</html>
