<?php
function getPages($titles)
{
    $URL =
'https://meta.wikimedia.org/w/api.php?action=query&format=php&prop=revisions&rvprop=content&redirects&titles=';
    
    if (is_array($titles)) {
        foreach ($titles as $t) {
            $URL .= urlencode($t) . '|';
        }
        $URL = rtrim($URL, '|');
    } else {
        $URL .= urlencode($titles);
    }
    echo '<!--', $URL, '-->';

    $ch = curl_init($URL);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, True);
    curl_setopt($ch, CURLOPT_USERAGENT, 'Labs Bot -
https://tools.wmflabs.org/stewardbots');
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

// To sort the array returned by getPages()
function titleSort($a , $b) {
    return strnatcasecmp($a['title'], $b['title']);
}

// Page content
$cacheFile = './cache/elections.php';
?>
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"
"http://www.w3.org/TR/html4/loose.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en" dir="ltr">
<head>
    <title>Steward elections 2016</title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <link rel="stylesheet" type="text/css" href="/stewardbots/Common.css" />
    <link rel="stylesheet" type="text/css"
href="/stewardbots/content/jquery.tablesorter/style.css" />
    <link rel="stylesheet" type="text/css"
href="/stewardbots/content/stylesheet.css" />
    <script type="text/javascript" language="javascript"
src="jquery.js"></script>
    <script type="text/javascript" language="javascript"
src="content/jquery.tablesorter/jquery.tablesorter.js"></script>
    <script type="text/javascript" language="javascript">
    jQuery(document).ready(function() { 
       jQuery('table.sortable').tablesorter();
    } );
    </script>
</head>
<body>
    <div id="globalWrapper">
        <div id="content" class="mw-body" role="main">           
            <h2>Steward elections</h2>
            <p>This page contains an unofficial tally of the votes in the <a
href="//meta.wikimedia.org/wiki/Stewards/Elections_2016">steward elections
2016</a>.</p>
<?php
// Used cached version?
if ( file_exists($cacheFile) ) {
    $useCache = True;
    if ( $_GET['action'] == 'purge' && ((time() - filemtime($cacheFile)) > 60)
|| $_GET['adm']) {
        $useCache = False;
    }    
} else {
    $useCache = False;
}

if ( $useCache ) {
    echo '<p style="font-style:italic">Using cached data from ' .
strftime('%H:%M, %e %B %Y', filemtime($cacheFile)) . ' (UTC), <a href="' .
$_SERVER['php_self'] . '?action=purge">purge</a>.</p>';
    
    // User tried to purge, but we decided to use the cache anyway.
    if ($_GET['action'] == 'purge') {
         echo '<p style="font-weight:bold;">Note: data can only be purged once
every minute. Please be patient.</p>';
    }
    
    include_once $cacheFile;
} else {
    // Start output buffering to regenerate chache
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
    $pages = getPages('Stewards/Elections_2016');
    
    if($pages) {
        $content = $pages[0]['content'];
    }
    #preg_match_all('/^\\{\\{[Ss]e[_ ]candidate[_
]indexer\\|2016\\|(?<user>[^\\|\\}]+)(?:\\|(?<status>[^\\|\\}]+))?\\}\\}/m',
$content, $m);
    preg_match_all('/^\{\{[Ss]e[_ ]candidate[_
]indexer\|2016\|(?<user>[^\|\}]+)(?:\|(?<status>[^\|\}]+))?\}\}/m', $content,
$m);

    // Loop users
    $titles = array();
    $count = count($m['user']);
    for($i = 0; $i < $count; $i++) {
        $user = $m['user'][$i];
        $status = $m['status'][$i];
        if(!$status || $status == 'yes')
            $titles[] = 'Stewards/Elections_2016/Votes/' . $user;
    }
    natcasesort($titles);
    
    $titles = array_chunk($titles, 40);
    $i = 1;
    foreach($titles as $tchunk) {
        $pages = getPages($tchunk);
        usort($pages, 'titleSort');
                
        // Treat pages
        foreach($pages as $page) {
            $title = $page['title'];
            $user = substr($title, 30);
            $content = $page['content'];

            if(!empty($content)) {
                // Find vote headers
                $offset = array();
                preg_match('/\=\=\=[ ]*?\{\{sr-heading\|yes\}\}[ ]*?\=\=\=/',
$content, $m, PREG_OFFSET_CAPTURE);
                $offset['yes'] = $m[0][1];
                preg_match('/\=\=\=[ ]*?\{\{sr-heading\|no\}\}[ ]*?\=\=\=/',
$content, $m, PREG_OFFSET_CAPTURE);
                $offset['no'] = $m[0][1];
                preg_match('/\=\=\=[ ]*?\{\{sr-heading\|neutral\}\}[
]*?\=\=\=/', $content, $m, PREG_OFFSET_CAPTURE);
                $offset['neutral'] = $m[0][1];

                // Find votes
                $vote = '/^\#[^\:\#].+?$/m';
                $votes = array();
                $votes['yes'] = preg_match_all($vote, substr($content,
$offset['yes'], $offset['no'] - $offset['yes']), $m);
                $votes['no'] = preg_match_all($vote, substr($content,
$offset['no'], $offset['neutral'] - $offset['no']), $m);
                $votes['neutral'] = preg_match_all($vote, substr($content,
$offset['neutral']), $m);
                
                // Math
                $support = $votes['yes'] / ($votes['yes'] + $votes['no']);
                $perc = round($support * 100, 1);
                
                $bgyes = ($votes['yes'] < 30 ? '
style="background-color:#FF9999"' : '');
                $bgsup = ' style="background-color:' . ($support >= 0.8 ?
'#99FF99' : '#FF9999') . '"';
                
                // Output row
?>
        <tr>
            <td><?=$i;?></td>
            <td><a
href="//meta.wikimedia.org/wiki/Stewards/Elections_2016/Votes/<?=$user;?>"><?=$user;?></a></td>
            <td<?=$bgyes;?>><?=$votes['yes'];?></td>
            <td><?=$votes['no'];?></td>
            <td><?=$votes['neutral'];?></td>
            <td<?=$bgsup;?>><?=$perc;?>%</td>
        </tr>
<?php
        } else {
?>
        <tr>
            <td><?=$i;?></td>
            <td><a
href="//meta.wikimedia.org/wiki/Stewards/Elections_2016/Votes/<?=$user;?>"><?=$user;?></a></td>
            <td colspan="4">Could not get votes. Please <a
href="//meta.wikimedia.org/wiki/User_talk:Erwin">report</a> this.</td>
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
                <a style="background-image:
url(//upload.wikimedia.org/wikipedia/commons/thumb/b/be/Wikimedia_Community_Logo-Toolserver.svg/135px-Wikimedia_Community_Logo-Toolserver.svg.png);"
href="//toolserver.org/~stewardbots/elections.php" title="Elections"></a>
            </div>
            <div class="portlet" id="p-navigation">
                <h5>Stewards</h5>
                <div class="pBody">
                    <ul>
                        <li><a
href="//meta.wikimedia.org/wiki/Stewards">Stewards</a></li>
                        <li><a
href="//meta.wikimedia.org/wiki/Stewards_policy">Policy</a></li>
                        <li><a
href="//meta.wikimedia.org/wiki/Steward_handbook">Handbook</a></li>
                    </ul>
                </div>
            </div>
            <div class="portlet" id="p-navigation2">
                <h5>Steward elections</h5>
                <div class="pBody">
                    <ul>
                        <li><a
href="//meta.wikimedia.org/wiki/Stewards/Elections_2016">Elections page</a></li>
                        <li><a
href="//meta.wikimedia.org/wiki/Stewards/Elections_2016/Guidelines">Guidelines</a></li>
                        <li><a
href="//meta.wikimedia.org/wiki/Stewards/Elections_2016/Statements">Statements</a></li>
                        <li><a
href="//meta.wikimedia.org/wiki/Stewards/Elections_2016/Questions">Questions</a></li>
                        <li><a
href="//meta.wikimedia.org/wiki/Stewards/Elections_2016/Statistics">Statistics</a></li>
                    </ul>
                </div>
            </div>
        </div>
        
        <div id="footer">
            <div id="f-poweredbyico">
                <a href="/"><img style = "border:0; float:left; padding: 5px;"
src="//upload.wikimedia.org/wikipedia/commons/a/a4/Tool_labs_logo.svg" alt="Powered by
Wikimedia Toolserver" title="Powered by Wikimedia Toolserver" height="31"
width="88" /></a>
            </div>
            <ul id="f-list">
                <li id="lastmod">This page was last modified 20 January
2016.</li>
                <li id="about">This tool is written by <a
href="//meta.wikimedia.org/wiki/User:Erwin">Erwin</a>.</li>
            </ul>
        </div>
    </div>
</body>
</html>