<?php
$data = parse_ini_file( '../replica.my.cnf' );
if ( !$data || !$data['user'] || !$data['password'] ) {
	throw new Exception( "Login data not found!" );
}

return $data;
