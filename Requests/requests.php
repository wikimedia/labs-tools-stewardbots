<?php
function getPages($titles)
{
    $URL = 'http://meta.wikimedia.org/w/api.php?action=query&format=php&prop=revisions&rvprop=content&titles=';

    if (is_array($titles)) {
        foreach ($titles as $t) {
            $URL .= urlencode($t) . '|';
        }
        $URL = rtrim($URL, '|');
    } else {
        $URL .= urlencode($titles);
    }
    $ch = curl_init($URL);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, True);
    curl_setopt($ch, CURLOPT_USERAGENT, 'Stewardbots; Wikimedia Labs - https://tools.wmflabs.org/stewardbots');
    $result = unserialize(curl_exec($ch));
    curl_close($ch);

    $output = array();
    if ($result['query']['pages']) {
        foreach($result['query']['pages'] as $page) {
            $output[] = array('title' => $page['title'],
                              'content' => $page['revisions'][0]['*']);
        }

        return $output;
    } else {
        return False;
    }
}

function isSteward($user) {
    global $cluster;
    global $db;
    $user = mysql_real_escape_string($user);
    $sql = 'SELECT 1
            FROM metawiki_p.user
            JOIN metawiki_p.user_groups
            ON ug_user = user_id
            WHERE user_name = \'' . $user . '\'
            AND ug_group = \'steward\' LIMIT 1;';
    $q = $db->performQuery($sql, $cluster);
    if ($q) {
        if (mysql_num_rows($q) == 1) {
            return True;
        }
    }

    return False;
}

function anchorencode($text) {
    $a = trim($text);
    $a = preg_replace('/\[\[(?:[^\]]*?)\|([^\]]*?)\]\]/', '${1}', $a);
    $a = preg_replace('/\[\[([^\]]*?)\]\]/', '${1}', $a);

    // Rest of function from CoreParserFunctions.php
    // phase3/includes/parser/CoreParserFunctions.php (r54220)
    $a = urlencode( $a );
    $a = strtr( $a, array( '%' => '.', '+' => '_' ) );
    # leave colons alone, however
    $a = str_replace( '.3A', ':', $a );
    return $a;
}

require_once '/Requests/database.class.php';

$db = TSDatabase::singleton();

// Page content
// $cacheFile = './cache/requests.php'; # Disabled this for now, M.A. 15-03-2016
?>
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en" dir="ltr">
<head>
    <title>Steward requests</title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <link href="/Common.css" rel="stylesheet" type="text/css" />
    <script type="text/javascript" language="javascript" src="sorting.js"></script>
</head>
<body>
    <div id="globalWrapper">
        <div id="content">
            <h2>Steward requests</h2>
            <p><b>steward requests</b> is an overview of the steward request pages.</p>
<?php
// Used cached version?
if ( file_exists($cacheFile) ) {
    $useCache = True;
    if ( $_GET['action'] == 'purge' && (time() - filemtime($cacheFile)) > 60) {
        $useCache = False;
    }
} else {
    $useCache = False;
}

if ( $useCache ) {
    echo '<p style="font-style:italic">Using cached data from ' .  strftime('%H:%M, %e %B %Y', filemtime($cacheFile)) . ' (UTC), <a href="' . $_SERVER['php_self'] . '?action=purge">purge</a>.</p>';

    // User tried to purge, but we decided to use the cache anyway.
    if ($_GET['action'] == 'purge') {
         echo '<p style="font-weight:bold;">Note: data can only be purged once every minute. Please be patient.</p>';
    }

    include_once $cacheFile;
} else {
    // Start output buffering to regenerate chache
    ob_start();

    $domain = 'meta.wikimedia.org';
    $cluster = $db->getCluster($domain);

    $requestPages = array(
                        'Steward requests/Checkuser' => array('title' => 'Checkuser', 'level' => 3),
                        'Steward requests/Global' => array('title' => 'Global', 'level' => 3),
                        'Steward requests/Global permissions' => array('title' => 'Global permissions', 'level' => 3),
                        'Steward requests/Bot status' => array('title' => 'Bot status', 'level' => 3),
                        'Steward requests/Permissions' => array('title' => 'Permissions', 'level' => 4),
                        'Steward requests/Username changes' => array('title' => 'Username changes', 'level' => 3),
                        'Steward requests/SUL requests' => array('title' => 'SUL requests', 'level' => 3),
                        'Steward requests/Speedy deletions' => array('title' => 'Speedy deletions', 'level' => 4),
                    );

    $pages = getPages(array_keys($requestPages));
    // Loop over steward request pages.
    foreach($pages as $page) {
        $requestPage = $requestPages[$page['title']];
        $sqlTitle = str_replace(' ', '_', $page['title']);

        echo '<h2><a href="http://' . $domain . '/wiki/' . $sqlTitle . '">' . $requestPage['title'] . '</a></h2>';

        // Get contents.
        $content = $page['content'];

        $iOpen = 0;
        $iUnhandled = 0;
        $aOldest = array(time(), '');
        $aUsers = array();
        $aRequests = array();

        if (!$content) {
            trigger_error('Could not get [[' . $page . ']].', E_USER_WARNING);
        }

        $offset = (strpos($content, '<!-- bof -->') ? strpos($content, '<!-- bof -->') : 0);

        $requests = preg_split('/^\={' . $requestPage['level'] . '}([^\=]*?)\={' . $requestPage['level'] . '}$/m', substr($content, $offset), 0, PREG_SPLIT_NO_EMPTY | PREG_SPLIT_DELIM_CAPTURE);

        // Loop requests
        for($i = 1; $i < count($requests); $i = $i + 2) {
            $title = $requests[$i];
            $text = $requests[$i + 1];
            $handled = False;
            $info = array();

            // Ignore closed requests;
            if (preg_match('/\{\{[Cc]losed(?:\||\}\})/', $text)
                || preg_match('/\s*?\|status\s*?=\s*?[Dd]one/', $text)
                || preg_match('/\s*?\|status\s*?=\s*?[Nn]ot done/', $text)
                || preg_match('/\{\{[Ss]tatus\|(?:[Dd]one|[Nn]ot done)(?:\||\}\})/', $text)) {
                $info['status'] = 'Closed';
            }

            // Find timestamps
            $timestamps = array();
            preg_match_all('/\d{2}:\d{2}, \d{1,2} .*? \d{4} \(UTC\)/', $text, $matches);
            foreach($matches[0] as $m) {
                $timestamps[] = strtotime($m);
            }

            sort($timestamps);

            // If no timestamp is found it's probably an example.
            if ($timestamps[0] == 0) {
                $info['status'] = 'Ignored';
            }

            if ($timestamps[0] < $aOldest[0] && !isset($info['status'])) {
                $aOldest = array($timestamps[0], $title);
            }

            $info['t_old'] = strftime('%H:%M, %e %B %Y', $timestamps[0]);
            $info['t_new'] = strftime('%H:%M, %e %B %Y', $timestamps[count($timestamps)-1]);

            // Find users
            $users = array();
            preg_match_all('/\[\[([Uu]ser:|Special:Contributions\/)(?P<user>[^\|\]]*?)\|[^\]]*?\]\]/', $text, $matches);

            foreach($matches['user'] as $u) {
                if(isSteward($u)) {
                    $handled = True;
                    $item = array('name' => $u, 'steward' => True);
                } else {
                    $item = array('name' => $u, 'steward' => False);
                }
                if (!in_array($item, $users)) {
                    $users[] = $item;
                }
            }
            $info['users'] = $users;

            // Update number of unhandled requests.
            if (!isset($info['status'])) {
                $iOpen++;
                if (!$handled) {
                    $iUnhandled++;
                    $info['status'] = 'Unhandled';
                } else {
                    $info['status'] = 'Handled';
                }
            }

            // Add array to main array
            $aRequests[$title] = $info;
        }

        // Show statistics

        $sql = 'SELECT user_name
                FROM metawiki_p.revision
                JOIN metawiki_p.page
                ON page_id = rev_page
                JOIN metawiki_p.user
                ON user_id = rev_user
                JOIN metawiki_p.user_groups
                ON ug_user = user_id
                WHERE page_namespace = 0
                AND page_title = \'' . $sqlTitle . '\'
                AND ug_group = \'steward\'
                AND rev_timestamp > DATE_SUB(NOW(), INTERVAL 1 MONTH) + 0
                GROUP BY user_id
                ORDER BY user_name ASC';
        $q = $db->performQuery($sql, $cluster);

        if (!$q) {
            $stewards = 'Unknown';
        } else {
            $stewards = array();
            while($row = mysql_fetch_assoc($q)) {
                $stewards[] = $row['user_name'];
            }
            $stewards = join(', ', $stewards);
        }

        echo '<p>';
        echo 'Open requests: ' . $iOpen . ' (<b>' . $iUnhandled . ' unhandled</b>).<br />';
	    if ($iOpen > 0) {
            echo 'Oldest open request: <i>' . $aOldest[1] . '</i> opened at <b>' . strftime('%H:%M, %e %B %Y', $aOldest[0]) . '</b>. <br />';
        }
        echo 'Recent stewards: <i>' . $stewards . '</i>.';
        echo '</p>';

        // List open requests
        if ($iOpen > 0) {
            echo '<table class="prettytable sortable" style="width: 100%">';
            echo '<tr><th style="width: 30%">Title</th><th style="width: 20%">First comment</th><th style="width: 20%">Last comment</th><th style="width: 30%">Users</th>';
            foreach($aRequests as $title => $info) {
                if($info['status'] == 'Handled' || $info['status'] == 'Unhandled'){
                    $sUsers = '';
                    foreach ($info['users'] as $u) {
                        if($u['steward']) {
                            $sUsers .= ', <b>' . $u['name'] . '</b>';
                        } else {
                            $sUsers .= ', ' . $u['name'];
                        }
                    }
                    $sUsers = (strlen($sUsers) > 2 ? substr($sUsers, 2) : $sUsers);
                    $link = '<a href="http://' . $domain . '/wiki/' . $sqlTitle . '#' . anchorencode($title) . '">' . $title . '</a>';
                    echo '<tr>';
                    echo '<td>' . $link . '</td><td>' . $info['t_old'] . '</td><td>' . $info['t_new'] . '</td><td>' . $sUsers . '</td>';
                    echo '</tr>';
                }
            }
            echo '</table>';
        }
    }

    // Save results to cache
    $f = fopen($cacheFile, 'w');
    fwrite($f, ob_get_contents());
    fclose($f);

    // Send the output to the browser
    ob_end_flush();
}
?>
        </div>

        <div id="column-one">
            <div class="portlet" id="p-logo">
                <a style="background-image: url(//upload.wikimedia.org/wikipedia/commons/thumb/a/a4/Tool_labs_logo.svg/135px-Tool_labs_logo.svg.png);" href="<?=$_SERVER['PHP_SELF'];?>"></a>
            </div>
            <div class="portlet" id="p-navigation">
                <h5>Stewards</h5>
                <div class="pBody">
                    <ul>
                        <li><a href="//meta.wikimedia.org/wiki/Stewards">Stewards</a></li>
                        <li><a href="//meta.wikimedia.org/wiki/Stewards_policy">Policy</a></li>
                        <li><a href="//meta.wikimedia.org/wiki/Steward_handbook">Handbook</a><li>
                    </ul>
                </div>
            </div>
            <div class="portlet" id="p-navigation2">
                <h5>Steward requests</h5>
                <div class="pBody">
                    <ul>
                        <li><a href="//meta.wikimedia.org/wiki/Steward_requests/Bot_status">Bot status</a></li>
                        <li><a href="//meta.wikimedia.org/wiki/Steward_requests/Checkuser">Checkuser</a></li>
                        <li><a href="//meta.wikimedia.org/wiki/Steward_requests/Global">Global</a></li>
                        <li><a href="//meta.wikimedia.org/wiki/Steward_requests/Global_permissions">Global permissions</a></li>
                        <li><a href="//meta.wikimedia.org/wiki/Steward_requests/Permissions">Permissions</a></li>
                        <li><a href="//meta.wikimedia.org/wiki/Steward_requests/SUL_requests">SUL requests</a></li>
                        <li><a href="//meta.wikimedia.org/wiki/Steward_requests/Username_changes">Username changes</a></li>
                        <li><a href="//meta.wikimedia.org/wiki/Steward_requests/Speedy_deletions">Speedy deletions</a></li>
                    </ul>
                </div>
            </div>
        </div>

        <div id="footer">
            <div id="f-poweredbyico">
                <a href="/"><img style = "border:0; float:left; padding: 5px;" src="//upload.wikimedia.org/wikipedia/commons/4/46/Powered_by_labs_button.png" alt="Powered by Wikimedia Toolserver" title="Powered by Wikimedia Toolserver" height="31" width="88" /></a>
            </div>
            <ul id="f-list">
                <li id="lastmod">This page was last modified 15 March 2016.</li>
                <li id="about">This tool was written by <a href="http://meta.wikimedia.org/wiki/User:Erwin">Erwin</a> and is now mantained by the stewardbots project.</li>
            </ul>
        </div>
    </div>
</body>
</html>
