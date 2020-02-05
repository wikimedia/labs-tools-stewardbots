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
	<title>Wikimedia Toolforge - Stewardbots</title>
	<link href="/stewardbots/resources/docs.css" rel="stylesheet" type="text/css" />
</head>
<body>
<div>
<div style="border:1px solid #ccc;padding:5px 10px;">
<h1 style="text-align: center;">Wikimedia Toolforge: ~stewardbots project</h1>
<p style="text-align: center;">This is a <a dir="ltr" href="https://tools.wmflabs.org/" target="_self">multi-mantainer project</a> for several <a href="https://meta.wikimedia.org/wiki/IRC/Bots" target="_self">IRC bots</a> and related <a href="https://meta.wikimedia.org/wiki/Stewards" target="_self">steward</a> tools.</p>
</div>
</div>

<h4>List of tools</h4>

<p>Currently the following tools are avalaible:</p>

<ul>
	<li><a href="/stewardbots/Elections/elections.php">Elections</a>: Breakdown of the steward elections.</li>
	<li><a href="/stewardbots/hat-web-tool/delete.php">Delete</a>: Overview of open speedy deletion requests.</li>
	<li><a href="/stewardbots/hat-web-tool/projects.php">Projects</a>: Overview of the number of administrators, bureaucrats, CheckUsers and Oversighters on the Wikimedia Wikis.</li>
</ul>

<h4>Help pages for the bots</h4>

<ul>
	<li><a href="/stewardbots/SULWatcher/SULWatcher.html">SULWatcher</a></li>
	<li><a href="/stewardbots/StewardBot/StewardBot.html">StewardBot</a></li>
</ul>

<h4>Code</h4>

<p>You can browse the code of our tools at <a href="https://phabricator.wikimedia.org/diffusion/TSTW/">Diffusion</a> or at <a href="https://github.com/wikimedia/labs-tools-stewardbots">GitHub</a>.</p>
<p>The development of this software happens on <a href="https://gerrit.wikimedia.org/">Wikimedia Gerrit</a> and is covered by a <a href="https://www.mediawiki.org/wiki/Code_of_Conduct">Code of Conduct</a>. Patches are always welcome.</p>

<h4>Other external tools</h4>

<ul>
	<li><a href="https://tools.wmflabs.org/rightstool">Rights tool</a>: A list of specific user-rights tools (by <a href="https://meta.wikimedia.org/wiki/User:Dungodung" target="_blank" rel="noopener">Dungodung</a>).</li>
</ul>

<h4>Bugs and suggestions</h4>

<p>We appreciate bugs reports and suggestions at <a href="https://phabricator.wikimedia.org/maniphest/task/create/?projects=Tool-stewardbots">Phabricator</a>.</p>

<hr />
<div id="footer">
<div id="f-poweredbyico"><a href="/"><img alt="Powered by Wikimedia Cloud Services" height="31" src="//upload.wikimedia.org/wikipedia/commons/4/46/Powered_by_labs_button.png" style="border:0; float:left; padding: 10px;" title="Powered by Wikimedia Cloud Services" width="88" /></a></div>
<div id="lastmod">This page is based on remote version <?php echo $rev;?> modified <?php echo $lastModified;?>.</div>
<div style="text-align: right;"><a href="https://tools.wmflabs.org/stewardbots/privacy.html">Privacy and Cookie statement</a>&nbsp;&middot;&nbsp;<a href="https://wikitech.wikimedia.org/wiki/Wikitech:Labs_Terms_of_use" target="_blank">Terms of Use</a>&nbsp;&middot;&nbsp;<a href="https://www.mediawiki.org/wiki/Code_of_Conduct">Code of Conduct</a>
</div>
</div>
</body>
</html>
