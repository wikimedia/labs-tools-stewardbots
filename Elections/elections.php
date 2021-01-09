<?php
include '../vendor/autoload.php';
use Symfony\Component\Process\Process;

// Election year
$year = 2021;

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

function getPages( $titles ) {
	$URL = 'https://meta.wikimedia.org/w/api.php'
		. '?action=query&format=php&prop=revisions&rvprop=content&redirects&titles=';
	if ( is_array( $titles ) ) {
		foreach ( $titles as $t ) {
			$URL .= urlencode( $t ) . '|';
		}
		$URL = rtrim( $URL, '|' );
	} else {
		$URL .= urlencode( $titles );
	}

	echo "<!-- $URL -->";
	$ch = curl_init( $URL );
	curl_setopt( $ch, CURLOPT_RETURNTRANSFER, true );
	curl_setopt( $ch, CURLOPT_USERAGENT, 'Toolforge Bot - https://stewardbots.toolforge.org/' );
	$result = unserialize( curl_exec( $ch ) );
	curl_close( $ch );
	$resultPages = $result['query']['pages'];
	if ( $resultPages ) {
		$output = [];
		foreach ( $resultPages as $page ) {
			$output[] = [
				'title' => $page['title'],
				'content' => $page['revisions'][0]['*']
			];
		}
		return $output;
	}

	return false;
}

// To sort the array returned by getPages
function titleSort( $a, $b ) {
	return strnatcasecmp( $a['title'], $b['title'] );
}

?>
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"
"http://www.w3.org/TR/html4/loose.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en" dir="ltr">
<head>
	<title><?php echo "Steward elections $year"; ?></title>
	<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
	<link rel="stylesheet" type="text/css" href="/resources/Common.css" />
	<link rel="stylesheet" type="text/css" href="/resources/stylesheet.css" />
	<script src="https://tools-static.wmflabs.org/static/jquery/2.1.0/jquery.min.js"></script>
	<script src="https://tools-static.wmflabs.org/static/jquery-tablesorter/2.0.5/jquery.tablesorter.min.js"></script>
	<script lang="javascript">
	jQuery(document).ready( function() {
	   jQuery('table.sortable').tablesorter();
	} );
	</script>
</head>
<body>
	<div id="globalWrapper">
		<div id="content" class="mw-body" role="main">
			<h2>Steward elections</h2>
			<p>
				<?php
				echo "This page contains an unofficial tally of the votes in the <a href='//meta.wikimedia.org/wiki/Stewards/Elections_$year'>$year steward elections</a>."
				?>
			</p>
<?php
$cacheFile = './cache/elections.php';
$useCache = false;
// Used cached version?
if ( file_exists( $cacheFile ) ) {
	$useCache = true;
	$lastModifiedTime = filemtime( $cacheFile );
	if ( $_GET['action'] === 'purge' && time() - $lastModifiedTime > 60 ) {
		// Cache can be purged only once within a minute
		$useCache = false;
	}
}

if ( $useCache ) {
	echo '<p style="font-style:italic">'
		. 'Using cached data from '
		. strftime( '%H:%M, %e %B %Y', filemtime( $cacheFile ) ) . ' (UTC), '
		. '<a href="' . $_SERVER['php_self'] . '?action=purge">purge</a>.'
		. '<small>Note: Data can only be purged once every minute.</small></p>';
	require_once $cacheFile;
} else {
	// Start output buffering to regenerate cache
	ob_start();
?>
			<table class="wikitable sortable">
				<thead>
					<tr>
						<th>#</th>
						<th style="width:300px;">Candidate</th>
						<th>Yes</th>
						<th>No</th>
						<th>Neutral</th>
						<th>Support</th>
					</tr>
				</thead>
			<tbody>
<?php
	$pages = getPages( "Stewards/Elections_$year" );
	$content = '';
	if ( $pages ) {
		$content = $pages[0]['content'];
	}

	 preg_match_all(
		  '/^\{\{[Ss]e[_ ]candidate[_ ]indexer\|\d{4}\|(?<user>[^\|\}]+)(?:\|(?<status>[^\|\}]+))?\}\}/m',
		  $content, $m
	 );

	// Loop users
	$titles = [];
	$count = count( $m['user'] );
	for ( $i = 0; $i < $count; $i++ ) {
		$user = $m['user'][$i];
		$status = $m['status'][$i];
		if ( !$status || $status == 'yes' ) {
			$titles[] = "Stewards/Elections_$year/Votes/$user";
		}
	}

	natcasesort( $titles );

	$titles = array_chunk( $titles, 40 );
	$i = 1;

	foreach ( $titles as $tchunk ) {
		$pages = getPages( $tchunk );

		usort( $pages, 'titleSort' );

		// Treat pages
		foreach ( $pages as $page ) {
			$title = $page['title'];
			$rawUser = substr( $title, 30 );
			$user = htmlspecialchars( $rawUser, ENT_QUOTES, 'UTF-8' );
			$encodedUser = rawurlencode( $rawUser );
			$content = $page['content'];
			if ( !empty( $content ) ) {
				// Find vote headers
				$offset = [];
				preg_match( '/\=\=\=[ ]*?\{\{sr-heading\|yes\}\}[ ]*?\=\=\=/', $content, $m, PREG_OFFSET_CAPTURE );
				$offset['yes'] = $m[0][1];
				preg_match( '/\=\=\=[ ]*?\{\{sr-heading\|no\}\}[ ]*?\=\=\=/', $content, $m, PREG_OFFSET_CAPTURE );
				$offset['no'] = $m[0][1];
				preg_match( '/\=\=\=[ ]*?\{\{sr-heading\|neutral\}\}[ ]*?\=\=\=/', $content, $m, PREG_OFFSET_CAPTURE );
				$offset['neutral'] = $m[0][1];

				// Find votes
				$vote = '/^\#[^\:\#].+?$/m';
				$votes = [];
				$votes['yes'] = preg_match_all( $vote, substr( $content, $offset['yes'], $offset['no'] - $offset['yes'] ), $m );
				$votes['no'] = preg_match_all( $vote, substr( $content, $offset['no'], $offset['neutral'] - $offset['no'] ), $m );
				$votes['neutral'] = preg_match_all( $vote, substr( $content, $offset['neutral'] ), $m );

				// Math
				$totalVotes = $votes['yes'] + $votes['no'];
				if ( $totalVotes > 0 ) {
					$support = $votes['yes'] / $totalVotes;
				} else {
					$support = 0;
				}
				$perc = round( $support * 100, 1 );

				$bgyes = ( $votes['yes'] < 30 ) ? 'style="background-color:#FF9999"' : '';
				$bgsup = 'style="background-color:' . ( $support >= 0.8 ? '#99FF99' : '#FF9999' ) . '"';
				// Output row
?>
				<tr>
					<td><?php echo $i;?></td>
					<?php echo "<td><a href='//meta.wikimedia.org/wiki/Stewards/Elections_$year/Votes/$encodedUser'>$user</a></td>";?>
					<td <?php echo $bgyes;?>><?php echo $votes['yes'];?></td>
					<td><?php echo $votes['no'];?></td>
					<td><?php echo $votes['neutral'];?></td>
					<td <?php echo $bgsup;?>><?php echo $perc;?>%</td>
				</tr>
<?php
			} else {
?>
				<tr>
					<td><?php echo $i; ?></td>
					<?php echo "<td><a href='//meta.wikimedia.org/wiki/Stewards/Elections_$year/Votes/$encodedUser'>$user</a></td>";?>
					<td colspan="4">Could not get votes. Please <a href="//phabricator.wikimedia.org/maniphest/task/create/?projects=Tool-stewardbots">report</a> this.</td>
				</tr>
<?php
			}
		$i++;
		}
	}
?>
			</tbody>
		</table>
<?php
	// Save results to cache if possible
	if ( file_exists( $cacheFile ) ) {
		$f = fopen( $cacheFile, 'w' );
		fwrite( $f, ob_get_contents() );
		fclose( $f );
	}

	// Send the output to the browser
	ob_end_flush();

}
?>
		</div>

		<div id="column-one">
			<div class="portlet" id="p-logo">
				<a style="background-image:
url(//upload.wikimedia.org/wikipedia/commons/thumb/8/89/Toolforge_logo_with_text.svg/135px-Toolforge_logo_with_text.svg.png);"
href="//tools.wmflabs.org/stewardbots/Elections/elections.php" title="Elections"></a>
			</div>
			<div class="portlet" id="p-navigation">
				<h3>Stewards</h3>
				<div class="pBody">
					<ul>
						<li><a href="//meta.wikimedia.org/wiki/Stewards">Stewards</a></li>
						<li><a href="//meta.wikimedia.org/wiki/Stewards_policy">Policy</a></li>
						<li><a href="//meta.wikimedia.org/wiki/Steward_handbook">Handbook</a></li>
					</ul>
				</div>
			</div>
			<div class="portlet" id="p-navigation2">
				<h3>Steward elections</h3>
				<div class="pBody">
					<ul>
						<?php echo(
						"<li><a href='//meta.wikimedia.org/wiki/Stewards/Elections_$year'>Elections page</a></li>" .
						"<li><a href='//meta.wikimedia.org/wiki/Stewards/Elections_$year/Guidelines'>Guidelines</a></li>" .
						"<li><a href='//meta.wikimedia.org/wiki/Stewards/Elections_$year/Statements'>Statements</a></li>" .
						"<li><a href='//meta.wikimedia.org/wiki/Stewards/Elections_$year/Questions'>Questions</a></li>" .
						"<li><a href='//meta.wikimedia.org/wiki/Stewards/Elections_$year/Statistics'>Statistics</a></li>"
						);
						?>
					</ul>
				</div>
			</div>
		</div>

		<div id="footer">
			<div id="f-poweredbyico">
				<a href="/"><img style = "border:0; float:left; padding: 5px;"
src="//upload.wikimedia.org/wikipedia/commons/4/46/Powered_by_labs_button.png" alt="Powered by
Wikimedia Labs" title="Powered by Wikimedia Labs" height="31"
width="88" /></a>
			</div>
			<ul id="f-list">
				<li id="lastmod">This page is based on remote version <?php echo $rev;?> modified <?php echo $lastModified;?>.</li>
				<li id="about">This tool was written by <a href="//meta.wikimedia.org/wiki/User:Erwin">Erwin</a> and is mantained by the stewardbots project.</li>
			</ul>
		</div>
	</div>
</body>
</html>
