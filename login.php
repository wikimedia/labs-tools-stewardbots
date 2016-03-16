<?php
$data = parse_ini_file( __DIR__ . '/../replica.my.cnf' );
if ( !$data || !$data['user'] || !$data['password'] ) {
	throw new Exception( "Login data not found!" );
}

return $data;
