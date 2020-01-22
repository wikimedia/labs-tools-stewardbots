#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# SYNPOPSIS:    This bot convert SULWatcher's old config to the database.
# LICENSE:      GPL
# CREDITS:      Erwin
#
from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import sys
import pymysql
import time

PY2 = sys.version_info[0] == 2

if PY2:
    from ConfigParser import ConfigParser
else:
    from configparser import ConfigParser
    unicode = str


class querier:
    """A wrapper for PyMySQL"""

    def __init__(self, *args, **kwargs):
        if 'read_default_file' not in kwargs:
            kwargs['read_default_file'] = '~/.my.cnf'

        kwargs['cursorclass'] = pymysql.cursors.DictCursor

        self.db = pymysql.connect(*args, **kwargs)
        self.db.autocommit(True)  # Autocommit transactions

        self.cursor = None

    # Execute a query
    def do(self, *args, **kwargs):
        self.cursor = self.db.cursor()
        self.cursor.execute(*args, **kwargs)

        results = tuple(self.cursor.fetchall())

        self.cursor.close()

        return results


def main():
    config = ConfigParser()
    config.read('SULWatcher.ini')

    db = querier(host='sql')

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
                    args.append(v.strip())
                args = tuple(args)
                db.do(sql, args)
        else:
            try:
                regex = unicode(config.get(section, 'regex'))
            except UnicodeDecodeError:
                print('Failing for %s' % (regex))
                print([regex])
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
