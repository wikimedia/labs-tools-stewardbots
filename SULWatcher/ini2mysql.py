#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# SYNPOPSIS:    This bot convert SULWatcher's old config to the database.
# LICENSE:      GPL
# CREDITS:      Erwin
#

import ConfigParser, time
import MySQLdb, MySQLdb.cursors

class querier:
    """A wrapper for MySQLdb"""
    
    def __init__(self, *args, **kwargs):
        if 'read_default_file' not in kwargs:
             kwargs['read_default_file'] = '~/.my.cnf'

        kwargs['cursorclass'] = MySQLdb.cursors.DictCursor

        self.db = MySQLdb.connect(*args, **kwargs)
        self.db.autocommit(True) # Autocommit transactions

        self.cursor = None
    
    # Execute a query
    def do(self, *args, **kwargs):          
        self.cursor = self.db.cursor()
        self.cursor.execute(*args, **kwargs)

        results = tuple(self.cursor.fetchall())

        self.cursor.close()

        return results

def main():
    config = ConfigParser.ConfigParser()
    config.read('SULWatcher.ini')
    
    db = querier(host = 'sql')
       
    for section in config.sections():
        if section == 'Setup':
            for option in config.options(section):
                value = config.get(section, option)
                if '<|>' in value:
                    values = value.split('<|>')
                else:
                    values = [value]
                sql = 'INSERT INTO p_stewardbots_sulwatcher.setup (s_param, s_value) VALUES '
                sql += '(%s, %s), ' * len(values)
                sql = sql[:-2] + ';'
                args = []
                for v in values:
                    args.append(option)
                    args.append(v.strip().encode('utf8'))
                args = tuple(args)
                db.do(sql, args)
        else:
            try:
                regex = unicode(config.get(section, 'regex'), 'utf8')
                regex = regex.encode('utf8')
            except:
                print 'Failing for %s' % (regex)
                print [regex]
            cloak = config.get(section, 'adder')
            timestamp = time.strftime('%Y%m%d%H%M%S')
            if config.has_option(section, 'reason'):
                sql = 'INSERT IGNORE INTO p_stewardbots_sulwatcher.regex (r_regex, r_cloak, r_reason, r_timestamp) VALUES (%s, %s, %s, %s)'
                args = (regex, cloak, config.get(section, 'reason'), timestamp)
            else:
                sql = 'INSERT IGNORE INTO p_stewardbots_sulwatcher.regex (r_regex, r_cloak, r_timestamp) VALUES (%s, %s, %s)'
                args = (regex, cloak, timestamp)
        
            db.do(sql, args)
            
if __name__ == "__main__":
    main()
