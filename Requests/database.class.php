<?php
class TSDatabase
{
    //Singleton implementation
    /*
    IRC 3 Dec 2009
    s1: enwiki
    s2: various medium-sized wikis
    s3: all wikis not on another cluster
    s4: commons
    s5: dewiki
    s6: fr/ja/ruwiki

    sql-toolserver: toolserver
    sql: user databases

    Distinct servers:
    s1, s2+s5, s3+s4+s6, sql, sql-toolserver

    Commons is available on all 3 servers.
    */
    private static $instance;

    public $link = array();
    public $status = array();
    private $_randServer = '';
    private $_servers = array('sql', 'sql-s1', 'sql-s2', 'sql-s3', 'sql-s4', 'sql-s5', 'sql-s6');
    private $_replag = array();
    private $_dbconn = array();
    private $_mysqlconf;

    public function __clone() {}

    private function __construct()
    {
        $this->_setAllStatus();
        $this->_mysqlconf = parse_ini_file('/data/project/stewardbots/.my.cnf');
        $this->_randServer = $this->_getRandServer();
        $this->_connectHost($this->_randServer); // Need a connection for mysql_real_escape_string

    }

    public static function singleton()
    {
        if (!isset(self::$instance)) {
            $c = __CLASS__;
            self::$instance = new $c();
        }

        return self::$instance;
    }

    function __destruct()
    {
        foreach($this->_servers as $s) {
            if ($this->_dbconn[$s] === True) {
                mysql_close($this->link[$s]);
            }
        }
    }

    /****************************************************
    Public functions
    ****************************************************/
    function performQuery($sql, $server = 'any')
    {
        // Query can be performed on any server.
        if ($server == 'any') {
            $server = $this->_randServer;
        }

        if (!isset($this->_dbconn[$server])) {
            $this->_connectHost($server);
        }

        if ($this->_dbconn[$server] === True) {
            $link = $this->link[$server];
            $q = mysql_query($sql, $link);
            return $q;
        } else {
            return False;
        }

    }

    //Backwards compatibility
    function performUserQuery($sql)
    {
        return $this->performQuery($sql, $server = 'sql');

    }

    function getReplag($server, $machine = False)
    {
        if (!array_key_exists($server, $this->_replag)) {
            $this->_setReplag();
        }

        if ($machine) {
            return $this->_replag[$server][0];
        } else {
            return $this->_replag[$server][1];
        }
    }

    function getAllReplag($machine = False)
    {
        $replag = array();
        foreach($this->_servers as $s) {
            if ($s != 'sql') {
                $replag[$s] = $this->getReplag($s);
            }
        }
        return $replag;
    }

    function getWarning()
    {
        $warning = '';

        foreach ($this->_servers as $s) {
            if ($this->status[$s][0] == 'ERRO' || $this->status[$s][0] == 'DOWN') {
                $class = 'erro';
            }
            if ($this->status[$s][0] != 'OK' ) {
                $warning .= '<li ' . ($class ? ' class="' . $class . '"' : '') . '>Cluster ' . $s . ': ' . $this->status[$s][0] . ' - ' . $this->status[$s][1] . '</li>';
            }
        }

        if (!empty($warning)) {
            $warning = '<h3>Database status:</h3><ul>' . $warning . '</ul>';
        }

        if (file_exists('/var/www/sitenotice')) {
            $notice = file_get_contents('/var/www/sitenotice');
        }

        $notice = (!empty($notice) ? '<h3>Notification:</h3>' . $notice : '');

        if (!empty($warning) || !empty($notice)) {
            return '<div class="warning">' . $warning . $notice . '</div>';
        } else {
            return '';
        }
    }

    function getCluster($domain)
    {
        $sql = "SELECT server FROM toolserver.wiki WHERE domain = '" . $domain . "'";
        $q = $this->performQuery($sql, $server = 'any');
        if ($q) {
            $result = mysql_fetch_assoc($q);
            return 'sql-s' . $result['server'];
        }
    }

    function getDatabase($domain)
    {
        $sql = "SELECT dbname FROM toolserver.wiki WHERE domain = '" . $domain . "'";
        $q = $this->performQuery($sql, $server = 'any');
        if ($q) {
            $result = mysql_fetch_assoc($q);
            return $result['dbname'];
        }
    }

    function getDomain($dbname)
    {
        $sql = "SELECT domain FROM toolserver.wiki WHERE dbname = '" . $dbname . "'";
        $q = $this->performQuery($sql, $server = 'any');
        if ($q) {
            $result = mysql_fetch_assoc($q);
            return $result['domain'];
        }
    }


    function getNamespace($ns_id, $db_name)
    {
        $sql = "SELECT ns_name FROM toolserver.namespace WHERE dbname = '" . $db_name . "' AND ns_id = " . $ns_id;
        $q = $this->performQuery($sql, $server = 'any');
        if ($q) {
            $result = mysql_fetch_assoc($q);
            if ($result['ns_name'] == 'Article') {
                return '';
            } else {
                return $result['ns_name'];
            }
        }
    }

    function getNamespaceID($ns_name, $db_name)
    {
        $sql = "SELECT ns_id FROM toolserver.namespace WHERE dbname = '" . $db_name . "' AND ns_name = '" . $ns_name . "'";
        $q = $this->performQuery($sql, $server = 'any');
        if ($q) {
            $result = mysql_fetch_assoc($q);
            return $result['ns_id'];
        }
    }


    /****************************************************
    Private functions
    ****************************************************/
    private function _setStatus($text, $server)
    {
        // Don't use named groups, annoying php
        // $match = preg_match('/^(?P<status>[a-zA-Z]+?)\;(?P<msg>.*?)$/m', $txt, $m);
        $match = preg_match('/^([a-zA-Z]+?)\;(.*?)$/m', $text, $m);
        if ($match) {
            $this->status[$server] = array($m[1], $m[2]);
        } else {
            $this->status[$server] = array('UNKNOWN', '');
        }

        if ($this->status[$server][0] == 'ERRO' || $this->status[$server][0] == 'DOWN') {
            $this->_dbup[$server] = False;
        } else {
            $this->_dbup[$server] = True;
        }
    }

    private function _setAllStatus()
    {
        foreach ($this->_servers as $s) {
            if ($s != 'sql') {
                $f = '/var/www/status_' . substr($s, 4);
            } else {
                $f = '/var/www/status_sql';
            }

            if (file_exists($f)) {
                $status = file_get_contents($f);
                $this->_setStatus($status, $s);
            } else {
                $this->_setStatus('Unknown', $s);
            }
        }
    }

    private function _getRandServer()
    {
        $servers = $this->_servers;
        while (count($servers) > 0) {
            $randKey = array_rand($servers);
            $s = $servers[$randKey];
            if ($this->_dbup[$s]) {
                return $s;
            } else {
                unset($server[$randKey]);
            }
        }
    }

    private function _connectHost($host)
    {
        $this->link[$host] = @mysql_connect($host, $this->_mysqlconf['user'], $this->_mysqlconf['password']);
        if ($this->link[$host]) {
            $this->_dbconn[$host] = True;
        } else {
            $this->_dbconn[$host] = False;
        }

    }
    private function _setReplag()
    {
        foreach ($this->_servers as $s) {
            if ($s != 'sql') {
                unset($r);
                switch($s) {
                    case 'sql-s1':
                        $dbname = 'enwiki_p';
                        break;
                    case 'sql-s2':
                        $dbname = 'nlwiki_p';
                        break;
                    case 'sql-s3':
                        $dbname = 'eswiki_p';
                        break;
                    case 'sql-s4':
                        $dbname = 'commonswiki_p';
                        break;
                    case 'sql-s5':
                        $dbname = 'dewiki_p';
                        break;
                    case 'sql-s6':
                        $dbname = 'frwiki_p';
                        break;
                }

                if (isset($dbname)) {
                    $sql = 'SELECT time_to_sec(timediff(now()+0,rev_timestamp)) FROM ' . $dbname . '.revision ORDER BY rev_timestamp DESC LIMIT 1';
                    $q = $this->performQuery($sql, $s);
                    if ($q) {
                        $result = mysql_fetch_array($q, MYSQL_NUM);
                        $r = array($result[0], $this->_timeDiff($result[0]));
                    }
                }

                $this->_replag[$s] = (isset($r) ? $r : array(-1, 'infinite'));
            }
        }
    }

    private function _timeDiff($time)
    {
        $days = ($time - ($time % 86400))/86400;
        $hours = (($time - $days*86400) - (($time - $days*86400) % 3600))/3600;
        $minutes = (($time - $days*86400 - $hours*3600) - (($time - $days*86400 - $hours*3600) % 60))/60;
        $seconds = $time - $days*86400 - $hours*3600 - $minutes*60;
        return $days . 'd ' . $hours . 'h ' . $minutes . 'm ' . $seconds . 's (' . $time .'s)';
    }
}
?>
