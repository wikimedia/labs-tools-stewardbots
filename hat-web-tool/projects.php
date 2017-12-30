<html>
<head><title>Projects</title>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<style type="text/css">@import "blue/style.css";</style>
<script src="https://tools-static.wmflabs.org/static/jquery/2.1.0/jquery.min.js"></script>
<script src="https://tools-static.wmflabs.org/static/jquery-tablesorter/2.0.5/jquery.tablesorter.min.js"></script>
<script type="text/javascript">
$(document).ready(function()
	{
		$("#projects").tablesorter();
	}
);
</script>
</head>
<body>
This is a replacement for erwin85's projects tool. For special rights, see <a href="http://tools.wmflabs.org/rightstool/cgi-bin/rightsstats">Dungodung's tool</a>.

<br /><br />
<table id="projects" class="tablesorter">
<thead>
<tr><th>Wiki</th><th>sysop</th><th>bureaucrat</th><th>checkuser</th><th>oversight</th></tr>
</thead>
<tbody>
	<?php
	$loginData = require_once __DIR__ . '/../login.php';

	$db_server = mysql_connect( "metawiki.analytics.db.svc.eqiad.wmflabs", $loginData['user'], $loginData['password'] );
	if ( !$db_server ) { die( "Unable to connect to MySQL: " . mysql_error() );
	}

	mysql_select_db( "meta_p", $db_server ) or die( "Unable to select database: " . mysql_error() );

	$query = "SELECT dbname,REPLACE(url, 'http://', 'https://') AS domain, slice FROM wiki WHERE url IS NOT NULL AND is_closed=0;";
	$result = mysql_query( $query );

	if ( !$result ) { die( "Database access failed: " . mysql_error() );
	}

	$rows = mysql_num_rows( $result );

	for ( $j = 0; $j < $rows; ++$j ) {
		$row = mysql_fetch_row( $result );

		$db_server_temp = mysql_connect( $row[2], $loginData['user'], $loginData['password'] );
		if ( !$db_server_temp ) { die( "Unable to connect to MySQL: " . mysql_error() );
		}

		mysql_select_db( $row[0]."_p", $db_server_temp ) or die( "Unable to select database: " . mysql_error() );

		$query2 = "SELECT sum(if(ug_group = 'sysop', 1, 0)), sum(if(ug_group = 'bureaucrat', 1, 0)), sum(if(ug_group = 'checkuser', 1, 0)), sum(if(ug_group = 'oversight', 1, 0)) FROM user_groups;";
		$result2 = mysql_query( $query2 );

		if ( !$result2 ) { die( "Database access failed: " . mysql_error() );
		}

		$row2 = mysql_fetch_row( $result2 );

		echo "<tr><td><a href=\"" . $row[1] . "\">". $row[0] . "</a></td>";
		echo "<td><a href=\"" . $row[1]. "/wiki/Special:ListUsers/sysop\">". ( $row2[0] ? $row2[0] : 0 )."</td>\n";
		echo "<td><a href=\"" . $row[1]. "/wiki/Special:ListUsers/bureaucrat\">".( $row2[1] ? $row2[1] : 0 )."</td>\n";
		echo "<td><a href=\"" . $row[1]. "/wiki/Special:ListUsers/checkuser\">".( $row2[2] ? $row2[2] : 0 )."</td>\n";
		echo "<td><a href=\"" . $row[1]. "/wiki/Special:ListUsers/oversight\">".( $row2[3] ? $row2[3] : 0 )."</td></tr>\n";
	}
	?>

</tbody>
</table>
<br />
<p>This tool was written by <a href="https://meta.wikimedia.org/wiki/User:Rschen7754">Rschen7754</a>. Acknowledgements to <a href="http://tools.wmflabs.org/erwin85/">erwin85</a> for the original tool and many of the queries, and to <a href="http://tools.wmflabs.org/pathoschild-contrib/">Pathoschild</a> for creating the extensive suite of tools that were used as an example.</p>
</body>
</html>
