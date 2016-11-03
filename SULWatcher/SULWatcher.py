#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# SYNPOPSIS:    This bot parses the RC feed for CentralAuth using
#               regex, and reports to a freenode channel.
# LICENSE:      GPL
# CREDITS:      Mike.lifeguard, Erwin, Dungodung (Filip Maljkovic)
#

import sys
import os
import re
import time
import threading
import traceback
import urllib
import MySQLdb
import MySQLdb.cursors

# Needs python-irclib
from ircbot import SingleServerIRCBot
from irclib import nm_to_n


class querier:
    """A wrapper for MySQLdb"""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

        if 'read_default_file' not in self.kwargs:
            self.kwargs['read_default_file'] = '~/.my.cnf'

        self.kwargs['cursorclass'] = MySQLdb.cursors.DictCursor

        self.connect()

    # Connect to the database server.
    def connect(self, *args, **kwargs):
        self.cursor = None
        self.db = MySQLdb.connect(*self.args, **self.kwargs)
        self.db.autocommit(True)  # Autocommit transactions

    # Execute a query.
    def do(self, *args, **kwargs):
        try:
            self.cursor = self.db.cursor()
            self.cursor.execute(*args, **kwargs)
        except (AttributeError, MySQLdb.OperationalError):
            # Try to reconnect to the server.
            self.connect()
            self.cursor = self.db.cursor()
            try:
                self.cursor.execute(*args, **kwargs)
            except:
                # Nothing we can do now.
                return None

        results = tuple(self.cursor.fetchall())
        self.cursor.close()
        return results


class SULWatcherException(Exception):
    """A single base exception class for all other SULWatcher errors."""
    pass


class CommanderError(SULWatcherException):
    """This exception is raised when the command parser fails."""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class BotConnectionError(SULWatcherException):
    """This exception is raised when a bot has some connection error."""

    def __init(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class ParseHostMaskError(SULWatcherException):
    """This exception is raised when a hostmask can't be parsed."""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class FreenodeBot(SingleServerIRCBot):

    def __init__(self, channel, nickname, server, password, port=6667):
        SingleServerIRCBot.__init__(self, [(server, port, "%s:%s"
                                            % (nickname, password))], nickname, nickname)
        self.server = server
        self.channel = channel
        self.nickname = nickname
        self.password = password
        self.buildRegex()
        self.buildWhitelist()

    def on_error(self, c, e):
        """
        Called when some kind of IRC error happens.

        WTF does that mean?!
        """
        print "Error:"
        print "Arguments: %s" % e.arguments()
        print "Target: %s" % e.target()
        self.die()
        sys.exit(1)

    def on_nicknameinuse(self, c, e):
        """
        Called when the server tells us our nick is already in use.

        We attempt to ghost the nick and acquire it.
        """
        print "Nick %s is in use, trying to acquire it..." % self.nickname
        c.nick(c.get_nickname() + "_")
        c.privmsg("NickServ", "GHOST %s %s" % (self.nickname, self.password))
        c.nick(self.nickname)
        print "Acquired nick %s; identifying..." % self.nickname
        c.privmsg("NickServ", "IDENTIFY %s" % self.password)

    def on_welcome(self, c, e):
        """
        Called when the server welcomes us after successfully connecting.

        We log the fact, and identify to nickserv.
        """
        print "Identifying to services..."
        c.privmsg("NickServ", "IDENTIFY %s" % self.password)
        time.sleep(5)  # Let identification succeed before joining channels
        c.join(self.channel)
        print "Joined %s" % self.channel

    def on_ctcp(self, c, e):
        """
        Called when the bot recieves a CTCP message.

        We only respond to:
         * VERSION, with a short string describing the bot
         * PING, if a timestamp is provided (the server requires it)
         * SOURCE, with a URL to documentation for the bot

        """
        if e.arguments()[0] == "VERSION":
            c.ctcp_reply(
                self.getNick(e.source()),
                "Bot for filtering account unifications in %s" % self.channel)
        elif e.arguments()[0] == "PING":
            if len(e.arguments()) > 1:
                c.ctcp_reply(
                    self.getNick(e.source()), "PING " + e.arguments()[1])
        elif e.arguments()[0] == "SOURCE":
            c.ctcp_reply(self.getNick(e.source()),
                         "git://git.hashbang.ca/SULWatcher")

    def on_privmsg(self, c, e):
        """
        Called when the bot recieves a private message.

        We parse the message, and try to find a command. Commands
        are only passed along to do_command if the user is voiced
        or opped in the main channel. Replies are sent back to
        the user by PM.
        """
        # timestamp = time.strftime('%d.%m.%Y %H:%M:%S', time.localtime(time.time()))
        nick = nm_to_n(e.source())
        target = nick  # If they did the command in PM, keep replies in PM
        a = e.arguments()[0]
        # print '[%s] <%s/%s>: %s' % (timestamp, e.target(), e.source(), a)
        command = a.strip()
        if (self.channels[self.channel].is_voiced(nick) or
                self.channels[self.channel].is_oper(nick)):
            try:
                self.do_command(e, command, target)
            except CommanderError, e:
                print 'CommanderError: %s' % e.value
                self.msg('You have to follow the proper syntax. See '
                         '\x0302https://tools.wmflabs.org/stewardbots/'
                         'SULWatcher\x03', nick)  # Make this translatable
            except:
                exceptionType, exceptionValue, exceptionTraceback = sys.exc_info()
                traceback.print_exception(
                    exceptionType, exceptionValue, exceptionTraceback)
                self.msg('Unknown internal error: %s; traceback in console'
                         % (sys.exc_info()[1], target))
        elif command == 'test':  # Safe to let them do this
            self.do_command(e, command, target)
        else:
            self.msg('Sorry, you need to be voiced to give the '
                     'bot commands.', nick)

    def on_pubmsg(self, c, e):
        """
        Called when the bot recieves a message in a channel.

        We parse the message, and try to find a command. Commands
        are only passed along to do_command if the user is voiced
        or opped in the main channel. Replies are sent back to
        the user in the channel, with some exceptions:
         * help is replied to in PM
         * ??
        """
        # timestamp = time.strftime('%d.%m.%Y %H:%M:%S', time.localtime(time.time()))
        nick = nm_to_n(e.source())
        # If they issued the command in a channel,
        # replies should go to the channel
        target = e.target()
        a = e.arguments()[0].split(':', 1)
        # print '[%s] <%s/%s>: %s' % (timestamp, target, nick, a)
        if a[0] == self.nickname:
            if len(a) == 2:
                command = a[1].strip()
                if (self.channels[self.channel].is_voiced(nick) or
                        self.channels[self.channel].is_oper(nick)):
                    try:
                        self.do_command(e, command, target)
                    except CommanderError, e:
                        print 'CommanderError: %s' % e.value
                        self.msg('You have to follow the proper syntax. See '
                                 '\x0302https://tools.wmflabs.org/stewardbots'
                                 '/SULWatcher\x03', target)
                    except:
                        exceptionType, exceptionValue, exceptionTraceback = sys.exc_info()
                        traceback.print_exception(
                            exceptionType, exceptionValue, exceptionTraceback)
                        self.msg('Unknown internal error: %s; traceback in console.'
                                 % (sys.exc_info()[1]), target)
                elif command == 'test':  # This one is safe to let them do
                    self.do_command(e, command, target)
                else:
                    self.msg('Sorry, you need to be voiced to give the '
                             'bot commands.', nick)

    def do_command(self, e, cmd, target):
        """
        Parse the given command, and perform the requested action, if
        possible.

        This should be split into a command_parse method, which hands
        off only valid commands to do_X methods.
        """
        print "do_command(self, e, '%s', '%s')" % (cmd, target)
        global badwords, whitelist
        nick = nm_to_n(e.source())
        args = cmd.split(' ')  # Should use regex to parse here
        if args[0] == '_':  # I forget why this was needed :(
            args.remove('_')
        if args[0] == 'help':
            self.msg(getConfig('help'), nick)
        elif args[0] == 'test':  # Notifications
            if len(args) >= 4:
                try:
                    i = args.index('regex')
                    string = ' '.join(args[1:i])
                    probe = ' '.join(args[i + 1:])
                    if (re.search(probe, string, re.IGNORECASE)):
                        self.msg('"%s" matches case insensitive regex "%s"'
                                 % (string, probe), target)
                    else:
                        self.msg('"%s" does not match regex "%s"'
                                 % (string, probe), target)
                except IndexError, e:
                    print 'IndexError: %s' % sys.exc_info()[1]
                    raise CommanderError("You didn't use the right format for "
                                         "testing: 'SULWatcher: test <string to test> regex "
                                         "\bregular ?expression\b'")
            elif len(args) == 1:
                self.msg("Yes, I'm alive. You can test a string against a "
                         "regex by saying 'SULWatcher: test <string to test> "
                         "regex \bregular ?expression\b'.", target)
                try:
                    # Test MySQL connection
                    sql = ('SELECT l_regex,l_user,l_timestamp FROM '
                           'logging ORDER BY l_id DESC LIMIT 1;')
                    result = db.do(sql)
                except:
                    result = None

                if result:
                    r = result[0]
                    try:
                        timestamp = time.strftime('%H:%M, %d %B %Y',
                                                  time.strptime(r['l_timestamp'], '%Y%m%d%H%M%S'))
                    except:
                        timestamp = r['l_timestamp']
                    self.msg(u'MySQL connection seems to be fine. Last hit '
                             'was %s matching %s at %s.'
                             % (r['l_user'], r['l_regex'], timestamp))
                else:
                    self.msg(u'MySQL connection seems to be down. '
                             'Please restart the bots.')
        elif args[0] == 'find' or args[0] == 'search':
            if args[1] == 'regex' or args[1] == 'badword':
                badword = ' '.join(args[2:])
                self.getPrintRegex(regex=badword, target=target)
            elif args[1] == 'match' or args[1] == 'matches':
                string = ' '.join(args[2:])
                matches = []
                for (idx, bw) in badwords:
                    if bw.search(string):
                        matches.append('%s (#%s)' % (bw.pattern, idx))
                if len(matches) == 0:
                    self.msg('There is no regex which matches the string "%s"'
                             % string, target)
                else:
                    self.msg('"%s" matches "%s".'
                             % (string, '", "'.join(matches)), target)
            elif args[1] == 'adder':
                adder = args[2]
                regexes = []
                sql = ('SELECT r_regex FROM regex '
                       'WHERE r_cloak=%s AND r_active=1;')
                args = (adder,)
                results = db.do(sql, args)
                regexes = [r['r_regex'] for r in results]
                if len(regexes) == 0:
                    self.msg('%s has added no regexes.' % adder, target)
                else:
                    maxlen = 20
                    shortlists = [regexes[i:i + maxlen] for i in range(0,
                                                                       len(regexes), maxlen)]
                    for l in range(0, len(shortlists)):
                        self.msg(r'%s added (%s/%s): %s.'
                                 % (adder, l + 1, len(shortlists),
                                    ", ".join(shortlists[l])), target)
                        time.sleep(2)  # Sleep a bit to avoid flooding?
            elif args[1] == 'number':
                index = args[2]
                self.getPrintRegex(index=index, target=target)
            else:
                self.msg('You can search for info on a regex by saying '
                         '"SULWatcher: find regex \bregex\b", or you can find '
                         'the regex matching a string by saying "SULWatcher: '
                         'find match String to test".', target)
        elif args[0] == 'edit' or args[0] == 'change':
            index = args[1]
            if args[2] == 'regex' or args[2] == 'badword':
                regex = ' '.join(args[3:])
                adder = self.getCloak(e.source())
                sql = ('UPDATE regex SET r_regex=%s,r_cloak=%s,'
                       'r_timestamp=%s WHERE r_id=%s')
                args = (regex, adder, time.strftime('%Y%m%d%H%M%S'), index)
                db.do(sql, args)
                if db.cursor.rowcount > 0:
                    self.msg('Regex #%s updated.' % (index), target=target)
                    self.getPrintRegex(index=index, target=target)
                    self.buildRegex()
            elif args[2] == 'note' or args[2] == 'reason':
                cloak = self.getCloak(e.source())
                # Re-attribute regex to cloak.
                if args[3] == '!':
                    reason = ' '.join(args[4:])
                    sql = ('UPDATE regex SET r_reason=%s,r_cloak=%s,'
                           'r_timestamp=%s WHERE r_id=%s')
                    args = (reason, cloak, time.strftime(
                        '%Y%m%d%H%M%S'), index)
                else:
                    reason = ' '.join(args[3:])
                    sql = ('UPDATE regex SET r_reason=%s,r_timestamp=%s '
                           'WHERE r_id=%s')
                    args = (reason, time.strftime('%Y%m%d%H%M%S'), index)
                db.do(sql, args)
                if db.cursor.rowcount > 0:
                    self.msg('Regex #%s updated.' % (index), target=target)
                    self.getPrintRegex(index=index, target=target)
            elif args[2] == 'enable' or args[2] == 'active':
                self.enableRegex(index, target)
            elif args[2] == 'case' or args[2] == 'casesensitive':
                if args[3] == 'true':
                    sql = ('UPDATE regex SET r_case=1,r_timestamp=%s '
                           'WHERE r_id=%s')
                else:
                    sql = ('UPDATE regex SET r_case=0,r_timestamp=%s '
                           'WHERE r_id=%s')
                args = (time.strftime('%Y%m%d%H%M%S'), index)
                db.do(sql, args)
                if db.cursor.rowcount > 0:
                    self.msg('Regex #%s updated.' % (index), target=target)
                    self.getPrintRegex(index=index, target=target)
                    self.buildRegex()

        elif args[0] == 'list':  # Lists: modify and show
            if (args[1] == 'badword' or args[1] == 'badwords' or
                    args[1] == 'regex' or args[1] == 'regexes'):
                if self.channels[self.channel].is_oper(nick):
                    sql = ('SELECT r_regex FROM regex WHERE r_active=1;')
                    results = db.do(sql)
                    longlist = [r['r_regex'] for r in results]
                    maxlen = 20
                    shortlists = [longlist[i:i + maxlen] for i in range(0,
                                                                        len(longlist), maxlen)]
                    self.msg('Listing active regexes:', target)
                    for l in range(0, len(shortlists)):
                        self.msg('Regex list (%s/%s): %s'
                                 % (l + 1, len(shortlists),
                                    ", ".join(shortlists[l])), target)
                        time.sleep(2)  # sleep a bit to avoid flooding?
                else:
                    self.msg('Sorry, can\'t do. I\'m afraid of flooding. You '
                             'can view the list at https://tools.wmflabs.org/'
                             'stewardbots/SULWatcher/ or force me to display '
                             'it by repeating this command as operator.', target)
            elif args[1] == 'whitelist':
                self.msg('Whitelisted users: %s'
                         % ', '.join(whitelist), target)
        elif args[0] == 'add':
            if args[1] == 'badword' or args[1] == 'regex':
                badword = ' '.join(args[2:])
                adder = self.getCloak(e.source())
                self.addRegex(badword, adder, target)
            elif args[1] == 'reason':
                index = args[2]
                cloak = self.getCloak(e.source())
                if args[3] == '!':  # Re-attribute regex to cloak.
                    reason = ' '.join(args[4:])
                    sql = ('UPDATE regex SET r_reason=%s,r_cloak=%s,'
                           'r_timestamp=%s WHERE r_id=%s')
                    args = (reason, cloak, time.strftime(
                        '%Y%m%d%H%M%S'), index)
                else:
                    reason = ' '.join(args[3:])
                    sql = ('UPDATE regex SET r_reason=%s,r_timestamp=%s '
                           'WHERE r_id=%s')
                    args = (reason, time.strftime('%Y%m%d%H%M%S'), index)
                db.do(sql, args)
                if db.cursor.rowcount > 0:
                    self.msg('Regex #%s updated.' % (index), target=target)
                    self.getPrintRegex(index=index, target=target)
            elif args[1] == 'whitelist':
                who = ' '.join(args[2:])
                self.addToList(who, 'whitelist', target)
        elif args[0] == 'remove':
            if args[1] == 'badword' or args[1] == 'regex':
                badword = ' '.join(args[2:])
                self.removeRegex(regex=badword, target=target)
            elif args[1] == 'whitelist':
                whitelist = ' '.join(args[2:])
                self.removeFromList(whitelist, 'whitelist', target)
        elif args[0] == 'huggle':  # Huggle
            if len(args) == 2:
                who = args[1]
                self.connection.action(self.channel, 'huggles %s' % who)
            else:
                raise CommanderError('Who is the target of these malicious '
                                     'huggles?!')
        elif args[0] == 'die':  # Die
            if self.channels[self.channel].is_oper(nick):
                print '%s is opped - dying...' % nick
                if len(args) > 1:
                    quitmsg = ' '.join(args[1:])
                else:
                    quitmsg = getConfig('quitmsg')
                try:
                    rawquitmsg = ':' + quitmsg
                    rcreader.connection.part(rcreader.rcfeed)
                    rcreader.connection.quit()
                    rcreader.disconnect()
                except:
                    raise BotConnectionError("RC reader didn't disconnect")
                try:
                    bot1.connection.part(bot1.channel, rawquitmsg)
                    bot1.connection.quit(rawquitmsg)
                    bot1.disconnect()
                except:
                    raise BotConnectionError("bot1 didn't disconnect")
                try:
                    bot2.connection.part(bot2.channel, rawquitmsg)
                    bot2.connection.quit(rawquitmsg)
                    bot2.disconnect()
                except:
                    raise BotConnectionError("bot2 didn't disconnect")
                print 'Killed. Now exiting...'
                # sys.exit(0) # 0 is a normal exit status
                os._exit(os.EX_OK)  # really really kill things off!!
            else:
                self.msg("You can't kill me; you're not opped!", target)
        elif args[0] == 'restart':  # Restart
            if self.channels[self.channel].is_oper(nick):
                print '%s is opped - restarting...' % nick
                if len(args) == 1:
                    quitmsg = getConfig('quitmsg')
                    print 'Restarting all bots with message: "%s"' % quitmsg
                    rawquitmsg = ':' + quitmsg
                    try:
                        rcreader.connection.part(rcfeed)
                        rcreader.connection.quit()
                        rcreader.disconnect()
                        BotThread(rcreader).start()
                    except:
                        raise BotConnectionError("rcreader didn't recover: %s %s %s"
                                                 % (sys.exc_info()[1],
                                                    sys.exc_info()[1],
                                                    sys.exc_info()[2]))
                    try:
                        bot1.connection.part(mainchannel, rawquitmsg)
                        bot1.connection.quit()
                        bot1.disconnect()
                        BotThread(bot1).start()
                    except:
                        raise BotConnectionError("bot1 didn't recover: %s %s %s"
                                                 % (sys.exc_info()[1],
                                                    sys.exc_info()[1],
                                                    sys.exc_info()[2]))
                    try:
                        bot2.connection.part(mainchannel, rawquitmsg)
                        bot2.connection.quit()
                        bot2.disconnect()
                        BotThread(bot2).start()
                    except:
                        raise BotConnectionError("bot2 didn't recover: %s %s %s"
                                                 % (sys.exc_info()[1],
                                                    sys.exc_info()[1],
                                                    sys.exc_info()[2]))
                elif len(args) > 1 and args[1] == 'rc':
                    self.msg('Restarting RC reader', target)
                    try:
                        rcreader.connection.part(rcfeed)
                        rcreader.connection.quit()
                        rcreader.disconnect()
                        BotThread(rcreader).start()
                    except:
                        raise BotConnectionError("rcreader didn't recover: %s %s %s"
                                                 % (sys.exc_info()[1],
                                                    sys.exc_info()[1],
                                                    sys.exc_info()[2]))

                else:
                    raise CommanderError("Invalid command")
            else:
                self.msg("You can't restart me; you're not opped!", target)

    def buildRegex(self):
        print 'buildRegex(self)'
        global badwords
        sql = ('SELECT r_id,r_regex,r_case FROM regex WHERE r_active=1;')
        results = db.do(sql)
        badwords = []
        for r in results:
            index = r['r_id']
            try:
                if r['r_case']:
                    regex = re.compile(r['r_regex'])
                else:
                    regex = re.compile(r['r_regex'], re.IGNORECASE)
                badwords.append((index, regex))
            except:  # What is the actual exception that might need to be caught here?
                self.msg('Disabling regex %s. Could not compile pattern '
                         'into regex object.' % (index))
                self.removeRegex(index=index)
        return badwords

    def buildWhitelist(self):
        print 'buildWhitelist(self)'
        global whitelist
        sql = ("SELECT s_value FROM setup WHERE s_param='whitelist';")
        result = db.do(sql)
        whitelist = [r['s_value'] for r in result]

    def addRegex(self, regex, cloak, target):
        print "addRegex(self, '%s', '%s', '%s')" % (regex, cloak, target)
        sql = ('SELECT r_id FROM regex WHERE r_regex=%s;')
        args = (regex,)
        result = db.do(sql, args)
        if not result:
            sql = ('INSERT IGNORE INTO regex (r_regex,r_cloak,r_timestamp) '
                   'VALUES (%s,%s,%s)')
            args = (regex, cloak, time.strftime('%Y%m%d%H%M%S'))
            db.do(sql, args)
            if db.cursor.rowcount > 0:
                self.msg('%s added %s to the list of regexes. If you would '
                         'like to set a reason, say "SULWatcher: add reason '
                         '%s reason for adding the regex".'
                         % (cloak, regex, db.cursor.lastrowid), target)
                self.buildRegex()
        else:
            self.msg('%s is already listed as a regex.' % (regex), target)
            self.getPrintRegex(regex=regex, target=target)

    def removeRegex(self, regex=None, index=None, target=None):
        print "removeRegex(self, '%s', '%s', '%s')" % (regex, index, target)
        if regex:
            sql = ('UPDATE regex SET r_active=0,r_timestamp=%s '
                   'WHERE r_regex=%s;')
            args = (time.strftime('%Y%m%d%H%M%S'), regex)
        elif index:
            sql = ('UPDATE regex SET r_active=0,r_timestamp=%s '
                   'WHERE r_id=%s;')
            args = (time.strftime('%Y%m%d%H%M%S'), index)
        else:
            return
        db.do(sql, args)
        if db.cursor.rowcount > 0:
            if regex:
                self.msg('Disabled regex %s.' % (regex), target)
            elif index:
                self.msg('Disabled regex #%s.' % (index), target)
            self.buildRegex()
        else:
            if regex:
                self.msg('Could not disable regex %s.' % (regex), target)
            elif index:
                self.msg('Could not disable regex #%s.' % (index), target)

    def enableRegex(self, index, target):
        print "enableRegex(self, '%s', '%s')" % (index, target)
        sql = ('UPDATE regex SET r_active=1 '
               'WHERE r_id=%s;')
        args = (index,)
        db.do(sql, args)
        if db.cursor.rowcount > 0:
            self.msg('Enabled regex #%s.' % (index), target)
            self.buildRegex()

    def getRegex(self, regex=None, index=None):
        print "getRegex(self, '%s', '%s')" % (regex, index)
        if regex:
            sql = """
                  SELECT r_id, r_regex, r_active, r_case, r_cloak, r_reason, r_timestamp, sum(if(l_id, 1, 0)) AS hits
                  FROM regex
                  LEFT JOIN logging
                  ON l_regex = r_regex
                  WHERE r_regex = %s;
                  """
            args = (regex,)
        elif index:
            sql = """
                  SELECT r_id, r_regex, r_active, r_case, r_cloak, r_reason, r_timestamp, sum(if(l_id, 1, 0)) AS hits
                  FROM regex
                  LEFT JOIN logging
                  ON l_regex = r_regex
                  WHERE r_id = %s;
                  """
            args = (index,)
        else:
            return None
        result = db.do(sql, args)
        # "no results" is really one row of Nones:
        # {'hits': None, 'r_regex': None, 'r_cloak': None, 'r_id': None,
        # 'r_timestamp': None, 'r_case': None, 'r_reason': None,
        # 'r_active': None}
        # So: check if r_regex is None - if it is, the row returned is bogus
        if result[0]['r_regex'] is None:
            return None
        if result:
            return result[0]
        else:
            return None

    def getPrintRegex(self, regex=None, index=None, target=None):
        print "getPrintRegex(self, '%s', '%s', '%s')" % (regex, index, target)
        r = self.getRegex(regex=regex, index=index)
        if r:
            if r['r_active']:
                info = 'active'
            else:
                info = 'inactive'
            if r['r_case']:
                info += ', case sensitive'
            try:
                timestamp = time.strftime('%H:%M, %d %B %Y',
                                          time.strptime(r['r_timestamp'], '%Y%m%d%H%M%S'))
            except:
                timestamp = r['r_timestamp']
            self.msg('Regex %s (#%s, %s, %s hits) added by %s with last '
                     'update at %s and note: \'%s\'.'
                     % (r['r_regex'], r['r_id'], info, r['hits'],
                        r['r_cloak'], timestamp, r['r_reason']), target)
        else:
            if regex:
                self.msg("Regex '%s' couldn't be found." % (regex), target)
            elif index:
                self.msg("Regex #%s couldn't be found." % (index), target)
            else:
                self.msg("That record couldn't be found.", target)

    def addToList(self, who, groupname, target):
        print "addToList(self, '%s', '%s', '%s')" % (who, groupname, target)
        l = getConfig(groupname)
        if not l:
            self.msg("Could not find '%s'." % (groupname), target)
        elif who not in l:
            sql = ('INSERT INTO setup (s_param,s_value) '
                   'VALUES (%s,%s);')
            args = (groupname, who)
            db.do(sql, args)
            if db.cursor.rowcount > 0:
                self.msg('Added %s to %s.' % (who, groupname), target)
                # Rebuild whitelist if necessary
                if groupname == 'whitelist':
                    self.buildWhitelist()
        else:
            self.msg('%s is already in %s.' % (who, groupname), target)

    def removeFromList(self, who, groupname, target):
        print ("removeFromList(self, '%s', '%s', '%s')"
               % (who, groupname, target))
        l = getConfig(groupname)
        if not l:
            self.msg("Could not find '%s'." % (groupname), target)
        elif who in l:
            sql = ('DELETE FROM setup WHERE s_param=%s AND s_value=%s;')
            args = (groupname, who)
            db.do(sql, args)
            if db.cursor.rowcount > 0:
                self.msg('Removed %s from %s.' % (who, groupname), target)
                # Rebuild whitelist if necessary
                if groupname == 'whitelist':
                    self.buildWhitelist()
        else:
            self.msg('%s is not in %s.' % (who, groupname), target)

    def msg(self, message, target=None):
        # print "msg(self, '%s', '%s')" % (message, target)
        if not target:
            target = self.channel
        self.connection.privmsg(target, message)

    def getCloak(self, mask):
        """
        Parse a hostmask, extracting the cloak part:

        nick!~user@host.com -> host.com
        """
        # print "getCloak(self, '%s')" % mask
        if "@" in mask:
            return mask.split("@")[1]
        else:
            raise ParseHostMaskError("Hostmask %s seems invalid." % mask)

    def getUser(self, mask):
        """
        Parse a hostmask, extracting the user part:

        nick!~user@host.com -> ~user
        """
        # print "getUser(self, '%s')" % mask
        if "!" in mask and "@" in mask:
            return mask.split("!")[1].split("@")[0]
        else:
            raise ParseHostMaskError("Hostmask %s seems invalid." % mask)

    def getNick(self, mask):
        """
        Parse a hostmask, extracting the nick part:

        nick!~user@host.com -> nick
        """
        # print "getNick(self, '%s')" % mask
        if "!" in mask:
            return mask.split("!")[0]
        else:
            raise ParseHostMaskError("Hostmask %s seems invalid." % mask)


class WikimediaBot(SingleServerIRCBot):

    def __init__(self, rcfeed, nickname, server, port=6667):
        SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
        self.server = server
        self.rcfeed = rcfeed
        self.nickname = nickname
        globals()['lastsulname'] = None
        globals()['lastbot'] = 1

    def on_error(self, c, e):
        print e.target()
        # self.die()

    def on_nicknameinuse(self, c, e):
        c.nick(c.get_nickname() + '_')

    def on_welcome(self, c, e):
        c.join(self.rcfeed)

    def on_ctcp(self, c, e):
        if e.arguments()[0] == 'VERSION':
            c.ctcp_reply(nm_to_n(e.source()),
                         "Bot for filtering account unifications in %s" % self.rcfeed)
        elif e.arguments()[0] == 'PING':
            if len(e.arguments()) > 1:
                c.ctcp_reply(nm_to_n(e.source()),
                             "PING " + e.arguments()[1])

    def on_pubmsg(self, c, e):
        global badwords, whitelist
        a = e.arguments()[0]
        # bot1.msg(a)
        # Parsing the rcbot output:
        # \x0314[[\x0307Usu\xc3\xa1rio:Liliaan\x0314]]\x034@ptwiki\x0310
        # \x0302http://pt.wikipedia.org/wiki/Usu%C3%A1rio:Liliaan\x03
        # \x035*\x03 \x0303Liliaan\x03 \x035*\x03
        parse = re.compile("\\x0314\[\[\\x0307(?P<localname>.*)\\x0314\]\]"
                           "\\x034@(?P<sulwiki>.*)\\x0310.*\\x0303(?P<sulname>"
                           ".*)\\x03 \\x035\*\\x03", re.UNICODE)
        try:
            # localname = parse.search(a).group('localname')
            sulwiki = parse.search(a).group('sulwiki')
            sulname = parse.search(a).group('sulname')
            if (not globals()['lastsulname'] or
                    globals()['lastsulname'] != sulname):
                bad = False
                good = False
                # print "%s@%s" % (sulname, sulwiki)
                matches = []
                for (idx, bw) in badwords:
                    if (bw.search(sulname)):
                        bad = True
                        matches.append(bw.pattern)
                for wl in whitelist:
                    if sulname == wl:
                        print "Skipped '%s'; user is whitelisted" % sulname
                        good = True
                urlname = urllib.quote(sulname)
#                print 'original: %s' % urlname
                if urlname.endswith('.'):
                    urlname = re.sub('\.$', '%2E', urlname)
#                print 'Replacement: %s' % sulname
                if not bad and not good:
                    if globals()['lastbot'] != 1:
                        bot1.msg("\x0303%s\x03@%s: \x0302https://meta.wikimedia.org/wiki/Special:CentralAuth/%s\x03"
                                 % (sulname, sulwiki, urlname))
                        globals()['lastbot'] = 1
                    else:
                        bot2.msg("\x0303%s\x03@%s: \x0302https://meta.wikimedia.org/wiki/Special:CentralAuth/%s\x03"
                                 % (sulname, sulwiki, urlname))
                        globals()['lastbot'] = 2
                elif bad and not good:
                    for m in matches:
                        try:
                            sql = ('INSERT INTO logging (l_regex,l_user,'
                                   'l_project,l_timestamp) VALUES '
                                   '(%s,%s,%s,%s);')
                            args = (m, sulname, sulwiki,
                                    time.strftime('%Y%m%d%H%M%S'))
                            db.do(sql, args)
                        except:
                            print 'Could not log hit to database.'
                    if globals()['lastbot'] != 1:
                        bot1.msg("\x0303%s\x03@%s \x0305\x02matches badword "
                                 "%s\017: \x0302https://meta.wikimedia.org/wiki/Special:CentralAuth/%s\x03"
                                 % (sulname, sulwiki, '; '.join(matches),
                                    urlname))
                        globals()['lastbot'] = 1
                    else:
                        bot2.msg("\x0303%s\x03@%s \x0305\x02matches badword "
                                 "%s\017: \x0302https://meta.wikimedia.org/wiki/Special:CentralAuth/%s\x03"
                                 % (sulname, sulwiki, '; '.join(matches),
                                    urlname))
                        globals()['lastbot'] = 2
            globals()['lastsulname'] = sulname
        except:  # Should be specific about what might happen here
            print ('RC reader error: %s %s %s'
                   % (sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]))


class BotThread(threading.Thread):

    def __init__(self, bot):
        self.b = bot
        threading.Thread.__init__(self)

    def run(self):
        self.startbot(self.b)

    def startbot(self, bot):
        bot.start()


def getConfig(param):
    print "getConfig(self, '%s')" % (param)
    sql = ('SELECT s_value FROM setup WHERE s_param=%s;')
    args = (param,)
    result = db.do(sql, args)
    result = [r['s_value'] for r in result]
    if len(result) > 1:
        return result
    elif len(result) == 1:
        return result[0]
    else:
        return None


def main():
    global bot1, bot2, rcreader, nickname, alias, password, mainchannel, mainserver, wmserver, rcfeed, db

    # These vars should be customized - in the future, they should be
    # read from a simple external config file for bootstrapping - all
    # other config data is in the database itself, but we need to know
    # where that db is & connect successfully before we can actually start.
    myhost = 'tools-db'
    mydatabase = 's51541_sulwatcher'

    db = querier(host=myhost, db=mydatabase)
    nickname = getConfig('nickname')
    alias = getConfig('alias')
    password = getConfig('password')
    mainchannel = getConfig('channel')
    mainserver = getConfig('server')
    wmserver = getConfig('wmserver')
    rcfeed = getConfig('rcfeed')
    bot1 = FreenodeBot(mainchannel, nickname, mainserver, password, 8001)
    bot2 = FreenodeBot(mainchannel, alias, mainserver, password, 8001)
    rcreader = WikimediaBot(rcfeed, 'SULW', wmserver, 8001)
    try:
        BotThread(bot1).start()
        BotThread(bot2).start()
        # The Freenode bots connect comparatively slowly & have a 5s delay
        # to identify to services before joining channels.
        time.sleep(5)
        BotThread(rcreader).start()  # Can cause ServerNotConnectedError
    except KeyboardInterrupt:
        raise

if __name__ == "__main__":
    global bot1, rcreader, bot2
# main()
    try:
        main()
    # We should be specific about what kinds of errors actually necessitate
    # dying, and which ones have better failure modes.
    except KeyboardInterrupt:
        exceptionType, exceptionValue, exceptionTraceback = sys.exc_info()
        traceback.print_exception(
            exceptionType, exceptionValue, exceptionTraceback)
        os._exit(os.EX_OK)
        raise
    except:
        print '\nUnexpected error:\n'
        exceptionType, exceptionValue, exceptionTraceback = sys.exc_info()
        traceback.print_exception(
            exceptionType, exceptionValue, exceptionTraceback)
        bot1.die()
        rcreader.die()
        bot2.die()
        sys.exit()
