<html>
<head><title>Delete</title></head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<style type="text/css">@import "blue/style.css";</style>
<script src="https://tools-static.wmflabs.org/static/jquery/2.1.0/jquery.min.js"></script>
<script src="https://tools-static.wmflabs.org/static/jquery-tablesorter/2.0.5/jquery.tablesorter.min.js"></script>
<script type="text/javascript">
	jQuery(document).ready( function() {
	   jQuery('#projects').tablesorter();
	} );
</script>
<?php
$loginData = require_once __DIR__ . '/../login.php';

function titleLink( $title ) {
	return str_replace( '%2F', '/', urlencode( str_replace( ' ', '_', $title ) ) );
}

function get_post( $var ) {
 return mysqli_real_escape_string( $_POST[$var] );
}

	//phpcs:disable MediaWiki.NamingConventions.ValidGlobalName.allowedPrefix
	global $loginData;
	// phpcs:enable

	$db_server = mysqli_connect( "metawiki.analytics.db.svc.eqiad.wmflabs", $loginData['user'], $loginData['password'] );
	if ( !$db_server ) { die( "Unable to connect to MySQL: " . mysqli_error() );
	}

	mysqli_select_db( $db_server, "meta_p" ) or die( "Unable to select database: " . mysqli_error( $db_server ) );
	$admins = 0;

	if ( isset( $_POST['number'] ) ) {
		$admins = get_post( 'number' );
	}
	if ( $admins > 10 ) {
			$admins = 10;
	}
?>
<body>
This will be a replacement for erwin85's delete tool.<br />
<h2>WARNING: this is a beta tool. You are responsible for your own deletions; please check before you delete!</h2>
<p>You can sort by multiple columns by first sorting by one column, and then shift-clicking the second column.</p>
<hr />
<form action="delete.php" method="post">
Number of admins (maximum 10): <input type="text" name="number" value="<?php $admins ?>"/><br />
<input type="submit" />
</form>
<table id="projects" class="tablesorter">
<thead>
<tr><th>Wiki</th><th>Admins</th><th>Last admin action</th><th>Page name</th><th>Last author</th><th>Last revision</th><th>Edit summary</th></tr>
</thead>
<tbody>
	<?php

	$query = "SELECT dbname,REPLACE(url, 'http://', 'https://') AS domain, slice FROM wiki WHERE url IS NOT NULL AND is_closed=0;";
	$result = mysqli_query( $db_server, $query );

	if ( !$result ) { die( "Database access failed: " . mysqli_error( $db_server ) );
	}

	$rows = mysqli_num_rows( $result );

	for ( $j = 0; $j < $rows; ++$j ) {
		$row = mysqli_fetch_row( $result );

		$db_server_temp = mysqli_connect( $row[2], $loginData['user'], $loginData['password'] );
		if ( !$db_server_temp ) { die( "Unable to connect to MySQL: " . mysqli_error( $db_server_temp ) );
		}

		mysqli_select_db( $db_server_temp, $row[0] . "_p" ) or die( "Unable to select database: " . mysql_error() );

		$query2 = "SELECT sum(if(ug_group = 'sysop', 1, 0)) FROM user_groups;";
		$result2 = mysqli_query( $db_server_temp, $query2 );

		if ( !$result2 ) { die( "Database access failed: " . mysqli_error() );
		}

		$row2 = mysqli_fetch_row( $result2 );

		$numAdmins = ( $row2[0] ? $row2[0] : 0 );

		if ( $numAdmins <= $admins ) {
			$queryL = "SELECT user_name, log_timestamp
					   FROM logging
						 JOIN actor_logging ON actor_id = log_actor
						 JOIN user ON user_id = actor_user
						 JOIN user_groups ON ug_user = user_id
					   WHERE log_type IN ('delete', 'block', 'protect')
						 AND ug_group = 'sysop'
					   ORDER BY log_timestamp DESC
					   LIMIT 1;";
			$resultL = mysqli_query( $db_server_temp, $queryL );

			if ( !$resultL ) { die( "Database access failed: " . mysql_error() );
			}

			$rowL = mysqli_fetch_row( $resultL );

			$query3 = "SELECT pl_title
					   FROM pagelinks
						 LEFT JOIN page ON page_id = pl_from
					   WHERE page_title = 'Delete'
						 AND page_namespace = 10
						 AND page_is_redirect = 1
					   LIMIT 1;";
			$result3 = mysqli_query( $db_server_temp, $query3 );

			if ( !$result3 ) { die( "Database access failed: " . mysql_error() );
			}

			$template = "Delete";

			if ( !$result3 ) {
				$template = "Delete";
			} elseif ( mysqli_num_rows( $result3 ) == 1 ) {
				$template = mysqli_result( $result3, 0 );
			} else {
				$template = "Delete";
			}

			$query4 = "SELECT page_title, rev_timestamp, actor_name AS rev_user_text, comment_text AS rev_comment, rev_id
					   FROM page
						 LEFT JOIN templatelinks ON tl_from = page_id
						 LEFT JOIN revision ON rev_page = page_id
						 JOIN actor_revision ON rev_actor = actor_id
						 JOIN comment_revision ON rev_comment_id = comment_id
					   WHERE tl_title = '" . $template . "'
						 AND tl_namespace=10
						 AND rev_timestamp = (
						   SELECT MAX(rev_timestamp)
						   FROM revision AS r
						   WHERE rev_page = page_id
					   )";
			$result4 = mysqli_query( $db_server_temp, $query4 );

			if ( !$result4 ) { die( "Database access failed: " . mysql_error() );
			}

			$rows4 = mysqli_num_rows( $result4 );

			for ( $k = 0; $k < $rows4; ++$k ) {
				$rowD = mysqli_fetch_row( $result4 );
				echo "<tr><td><a href=\"" . $row[1] . "\">" . $row[0] . "</a></td>";
				echo "<td>" . $numAdmins . "</td>\n";
				echo "<td>" . $rowL[1] . "</td>\n";
				echo "<td><a href=\"" . $row[1] . "/wiki/Special:Diff/" . titleLink( $rowD[4] ) . "\">" . $rowD[0] . "</a></td>\n";
				echo "<td><a href=\"" . $row[1] . "/wiki/User:" . titleLink( $rowD[2] ) . "\">" . $rowD[2] . "</a></td>\n";
				echo "<td>" . $rowD[1] . "</td>\n";
				echo "<td>" . $rowD[3] . "</td></tr>\n";
			}
		}
	}
	?>

</tbody>
</table>
<br />
<p>Acknowledgements to <a href="https://erwin85.toolforge.org/">erwin85</a> for the
original tool and many of the queries, and to <a href="https://pathoschild-contrib.toolforge.org/">Pathoschild</a>
for creating the extensive suite of tools that I used as an example.</p>
</body>
</html>
