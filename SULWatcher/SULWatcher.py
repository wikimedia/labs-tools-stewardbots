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
import json
import threading
import traceback
from urllib.parse import quote
from sseclient import SSEClient as EventStream

# Needs irc lib
from irc.client import NickMask
from jaraco.stream import buffer

from ib3 import Bot
from ib3.auth import SASL
from ib3.connection import SSL
from ib3.mixins import DisconnectOnError
from ib3.nick import Ghost

import pymysql


def nm_to_n(nm):
    """Convert nick mask from source to nick."""
    return NickMask(nm).nick


class Querier(object):

    """A wrapper for PyMySQL"""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

        if 'read_default_file' not in self.kwargs:
            self.kwargs['read_default_file'] = '~/.my.cnf'

        self.kwargs['cursorclass'] = pymysql.cursors.DictCursor

        self.connect()

    def connect(self, *args, **kwargs):
        """Connect to the database server."""
        self.cursor = None
        self.db = pymysql.connect(*self.args, **self.kwargs)
        self.db.autocommit(True)  # Autocommit transactions

    def do(self, *args, **kwargs):
        """Execute a query."""
        try:
            self.cursor = self.db.cursor()
            self.cursor.execute(*args, **kwargs)
        except (AttributeError, pymysql.OperationalError):
            # Try to reconnect to the server.
            self.connect()
            self.cursor = self.db.cursor()
            try:
                self.cursor.execute(*args, **kwargs)
            except Exception:
                # Nothing we can do now.
                return None

        results = tuple(self.cursor.fetchall())
        self.cursor.close()
        return results


class SULWatcherException(Exception):

    """A single base exception class for all other SULWatcher errors."""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class CommanderError(SULWatcherException):

    """This exception is raised when the command parser fails."""

    pass


class BotConnectionError(SULWatcherException):

    """This exception is raised when a bot has some connection error."""

    pass


class ParseHostMaskError(SULWatcherException):

    """This exception is raised when a hostmask can't be parsed."""

    pass

class FreenodeBot(SASL, SSL, DisconnectOnError, Ghost, Bot):
    def __init__(self, sulwatcher, channel, nickname, server, password, port=6697):
        self.sulwatcher = sulwatcher
        self.channel = channel
        self.nickname = nickname
        self.buildRegex()
        self.buildWhitelist()
        super().__init__(
            server_list=[(server, port)],
            nickname=nickname,
            realname=nickname,
            ident_password=password,
            channels=[self.channel]
        )

    def on_ctcp(self, c, event):
        """
        Called when the bot recieves a CTCP message.

        We only respond to:
         * VERSION, with a short string describing the bot
         * PING, if a timestamp is provided (the server requires it)
         * SOURCE, with a URL to documentation for the bot

        """
        if event.arguments[0] == "VERSION":
            c.ctcp_reply(
                self.getNick(event.source),
                "Bot for filtering account unifications in %s" % self.channel)
        elif event.arguments[0] == "PING" and len(event.arguments) > 1:
            c.ctcp_reply(self.getNick(event.source), "PING " + event.arguments[1])
        elif event.arguments[0] == "SOURCE":
            c.ctcp_reply(self.getNick(event.source),
                         "git://git.hashbang.ca/SULWatcher")

    def on_privmsg(self, c, event):
        """
        Called when the bot recieves a private message.

        We parse the message, and try to find a command. Commands
        are only passed along to do_command if the user is voiced
        or opped in the main channel. Replies are sent back to
        the user by PM.
        """
        # timestamp = time.strftime('%d.%m.%Y %H:%M:%S',
        #                           time.localtime(time.time()))
        nick = nm_to_n(event.source)
        target = nick  # If they did the command in PM, keep replies in PM
        a = event.arguments[0]
        # print('[%s] <%s/%s>: %s' % (timestamp, e.target(), e.source, a))
        command = a.strip()
        if (self.channels[self.channel].is_voiced(nick) or
                self.channels[self.channel].is_oper(nick)):
            try:
                self.do_command(event, command, target)
            except CommanderError as event:
                print('CommanderError: %s' % event.value)
                self.msg('You have to follow the proper syntax. See '
                         '\x0302https://stewardbots-legacy.toolforge.org/'
                         'SULWatcher\x03', nick)  # Make this translatable
            except Exception:
                (exceptionType, exceptionValue,
                 exceptionTraceback) = sys.exc_info()
                traceback.print_exception(
                    exceptionType, exceptionValue, exceptionTraceback)
                self.msg('Unknown internal error: %s target: %s; traceback in console'
                         % (sys.exc_info()[1], target))
        elif command == 'test':  # Safe to let them do this
            self.do_command(event, command, target)
        else:
            self.msg('Sorry, you need to be voiced to give the '
                     'bot commands.', nick)

    def on_pubmsg(self, c, event):
        """
        Called when the bot recieves a message in a channel.

        We parse the message, and try to find a command. Commands
        are only passed along to do_command if the user is voiced
        or opped in the main channel. Replies are sent back to
        the user in the channel, with some exceptions:
         * help is replied to in PM
         * ??
        """
        if not self.has_primary_nick():
            return
        # timestamp = time.strftime('%d.%m.%Y %H:%M:%S',
        #                           time.localtime(time.time()))
        nick = nm_to_n(event.source)
        # If they issued the command in a channel,
        # replies should go to the channel
        target = event.target
        a = event.arguments[0].split(':', 1)
        # print('[%s] <%s/%s>: %s' % (timestamp, target, nick, a))
        if a[0] == self.nickname:
            if len(a) == 2:
                command = a[1].strip()
                if (self.channels[self.channel].is_voiced(nick) or
                        self.channels[self.channel].is_oper(nick)):
                    try:
                        self.do_command(event, command, target)
                    except CommanderError as event:
                        print('CommanderError: %s' % event.value)
                        self.msg('You have to follow the proper syntax. See '
                                 '\x0302https://stewardbots-legacy.toolforge.org/'
                                 'SULWatcher\x03', target)
                    except Exception:
                        (exceptionType, exceptionValue,
                         exceptionTraceback) = sys.exc_info()
                        traceback.print_exception(
                            exceptionType, exceptionValue, exceptionTraceback)
                        self.msg(
                            'Unknown internal error: {}; traceback in console.'
                            .format(sys.exc_info()[1]), target)
                elif command == 'test':  # This one is safe to let them do
                    self.do_command(event, command, target)
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
        print("do_command(self, e, '%s', '%s')" % (cmd, target))
        global badwords, whitelist
        nick = nm_to_n(e.source)
        args = cmd.split(' ')  # Should use regex to parse here
        if args[0] == '_':  # I forget why this was needed :(
            args.remove('_')
        if args[0] == 'help':
            self.msg(self.sulwatcher.get_config_result('help'), nick)
        elif args[0] == 'test':  # Notifications
            if len(args) >= 4:
                try:
                    i = args.index('regex')
                    string = ' '.join(args[1:i])
                    probe = ' '.join(args[i + 1:])
                    if re.search(probe, string, re.IGNORECASE):
                        self.msg('"%s" matches case insensitive regex "%s"'
                                 % (string, probe), target)
                    else:
                        self.msg('"%s" does not match regex "%s"'
                                 % (string, probe), target)
                except IndexError:
                    print('IndexError: %s' % sys.exc_info()[1])
                    raise CommanderError(
                        "You didn't use the right format for "
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
                    result = self.sulwatcher.querier.do(sql)
                except Exception:
                    result = None

                if result:
                    r = result[0]
                    try:
                        timestamp = time.strftime(
                            '%H:%M, %d %B %Y',
                            time.strptime(r['l_timestamp'].decode("ASCII"), '%Y%m%d%H%M%S'))
                    except ValueError:
                        timestamp = r['l_timestamp']
                    self.msg('MySQL connection seems to be fine. Last hit '
                             'was {r[l_user]} matching {r[l_regex]} at {ts}.'
                             .format(r=r, ts=timestamp))
                else:
                    self.msg('MySQL connection seems to be down. '
                             'Please restart the bots.')
        elif args[0] in ('find', 'search'):
            if args[1] in ('regex', 'badword'):
                badword = ' '.join(args[2:])
                self.getPrintRegex(regex=badword, target=target)
            elif args[1] in ('match', 'matches'):
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
                results = self.sulwatcher.querier.do(sql, args)
                regexes = [r['r_regex'] for r in results]
                if len(regexes) == 0:
                    self.msg('%s has added no regexes.' % adder, target)
                else:
                    maxlen = 20
                    shortlists = [regexes[i:i + maxlen]
                                  for i in range(0, len(regexes), maxlen)]
                    for i in range(0, len(shortlists)):
                        self.msg(r'%s added (%s/%s): %s.'
                                 % (adder, i + 1, len(shortlists),
                                    ", ".join(shortlists[i])), target)
                        time.sleep(2)  # Sleep a bit to avoid flooding?
            elif args[1] == 'number':
                index = args[2]
                self.getPrintRegex(index=index, target=target)
            else:
                self.msg('You can search for info on a regex by saying '
                         '"SULWatcher: find regex \bregex\b", or you can find '
                         'the regex matching a string by saying "SULWatcher: '
                         'find match String to test".', target)
        elif args[0] in ('edit', 'change'):
            index = args[1]
            if args[2] in ('regex', 'badword'):
                regex = ' '.join(args[3:])
                adder = self.getCloak(e.source)
                sql = ('UPDATE regex SET r_regex=%s,r_cloak=%s,'
                       'r_timestamp=%s WHERE r_id=%s')
                args = (regex, adder, time.strftime('%Y%m%d%H%M%S'), index)
                self.sulwatcher.querier.do(sql, args)
                if self.sulwatcher.querier.cursor.rowcount > 0:
                    self.msg('Regex #%s updated.' % (index), target=target)
                    self.getPrintRegex(index=index, target=target)
                    self.buildRegex()
            elif args[2] in ('note', 'reason'):
                cloak = self.getCloak(e.source)
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
                self.sulwatcher.querier.do(sql, args)
                if self.sulwatcher.querier.cursor.rowcount > 0:
                    self.msg('Regex #%s updated.' % (index), target=target)
                    self.getPrintRegex(index=index, target=target)
            elif args[2] in ('enable', 'active'):
                self.enableRegex(index, target)
            elif args[2] in ('case', 'casesensitive'):
                if args[3] == 'true':
                    sql = ('UPDATE regex SET r_case=1,r_timestamp=%s '
                           'WHERE r_id=%s')
                else:
                    sql = ('UPDATE regex SET r_case=0,r_timestamp=%s '
                           'WHERE r_id=%s')
                args = (time.strftime('%Y%m%d%H%M%S'), index)
                self.sulwatcher.querier.do(sql, args)
                if self.sulwatcher.querier.cursor.rowcount > 0:
                    self.msg('Regex #%s updated.' % (index), target=target)
                    self.getPrintRegex(index=index, target=target)
                    self.buildRegex()

        elif args[0] == 'list':  # Lists: modify and show
            if args[1] in ('badword', 'badwords', 'regex', 'regexes'):
                if self.channels[self.channel].is_oper(nick):
                    sql = ('SELECT r_regex FROM regex WHERE r_active=1;')
                    results = self.sulwatcher.querier.do(sql)
                    longlist = [r['r_regex'] for r in results]
                    maxlen = 20
                    shortlists = [longlist[i:i + maxlen]
                                  for i in range(0, len(longlist), maxlen)]
                    self.msg('Listing active regexes:', target)
                    for i in range(0, len(shortlists)):
                        self.msg('Regex list (%s/%s): %s'
                                 % (i + 1, len(shortlists),
                                    ", ".join(shortlists[i])), target)
                        time.sleep(2)  # sleep a bit to avoid flooding?
                else:
                    self.msg("Sorry, can't do. I'm afraid of flooding. You "
                             'can view the list at https://stewardbots-legacy.toolforge.org/'
                             'SULWatcher/ or force me to display it by repeating'
                             'this command as operator.',
                             target)
            elif args[1] == 'whitelist':
                self.msg('Whitelisted users: %s'
                         % ', '.join(whitelist), target)
        elif args[0] == 'add':
            if args[1] in ('badword', 'regex'):
                badword = ' '.join(args[2:])
                adder = self.getCloak(e.source)
                self.addRegex(badword, adder, target)
            elif args[1] == 'reason':
                index = args[2]
                cloak = self.getCloak(e.source)
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
                self.sulwatcher.querier.do(sql, args)
                if self.sulwatcher.querier.cursor.rowcount > 0:
                    self.msg('Regex #%s updated.' % (index), target=target)
                    self.getPrintRegex(index=index, target=target)
            elif args[1] == 'whitelist':
                who = ' '.join(args[2:])
                self.addToList(who, 'whitelist', target)
        elif args[0] == 'remove':
            if args[1] in ('badword', 'regex'):
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
                print('%s is opped - dying...' % nick)
                if len(args) > 1:
                    quitmsg = ' '.join(args[1:])
                else:
                    quitmsg = self.sulwatcher.get_config_result('quitmsg')
                for botinstance in self.sulwatcher.irc_bots:
                    try:
                        rawquitmsg = ':' + quitmsg
                        botinstance.connection.part(botinstance.channel, rawquitmsg)
                        botinstance.connection.quit(rawquitmsg)
                        botinstance.disconnect()
                    except Exception:
                        # let's exit anyways
                        print(traceback.format_exc())
                        print("a bot didn't disconnect")
                print('Killed. Now exiting...')
                # sys.exit(0) # 0 is a normal exit status
                os._exit(os.EX_OK)  # really really kill things off!!
            else:
                self.msg("You can't kill me; you're not opped!", target)
        elif args[0] == 'restart':  # Restart
            if self.channels[self.channel].is_oper(nick):
                print('%s is opped - restarting...' % nick)
                if len(args) == 1:
                    quitmsg = self.sulwatcher.get_config_result('quitmsg')
                    print('Restarting all bots with message: "%s"' % quitmsg)
                    rawquitmsg = ':' + quitmsg
                    for botinstance in self.sulwatcher.irc_bots:
                        try:
                            rawquitmsg = ':' + quitmsg
                            botinstance.connection.part(botinstance.channel, rawquitmsg)
                            botinstance.connection.quit(rawquitmsg)
                            botinstance.disconnect()
                            BotThread(botinstance).start()
                        except Exception:
                            raise BotConnectionError(
                                "a bot didn't recover: {} {} {}"
                                .format(sys.exc_info()[1],
                                        sys.exc_info()[1],
                                        sys.exc_info()[2]))
                elif len(args) > 1 and args[1] == 'rc':
                    self.msg('Restarting RC reader', target)
                    try:
                        self.sulwatcher.eventstreams_stop.set()
                        self.sulwatcher.start_eventstreams()

                    except Exception as e:
                        raise BotConnectionError(str(e))
                else:
                    raise CommanderError("Invalid command")
            else:
                self.msg("You can't restart me; you're not opped!", target)

    def buildRegex(self):
        print('buildRegex(self)')
        global badwords
        sql = ('SELECT r_id,r_regex,r_case FROM regex WHERE r_active=1;')
        results = self.sulwatcher.querier.do(sql)
        badwords = []
        for r in results:
            index = r['r_id']
            try:
                if r['r_case']:
                    regex = re.compile(r['r_regex'])
                else:
                    regex = re.compile(r['r_regex'], re.IGNORECASE)
                badwords.append((index, regex))
            except Exception:
                # What is the actual exception to be caught here?
                self.msg('Disabling regex %s. Could not compile pattern '
                         'into regex object.' % (index))
                self.removeRegex(index=index)
        return badwords

    def buildWhitelist(self):
        print('buildWhitelist(self)')
        global whitelist
        sql = ("SELECT s_value FROM setup WHERE s_param='whitelist';")
        result = self.sulwatcher.querier.do(sql)
        whitelist = [r['s_value'] for r in result]

    def addRegex(self, regex, cloak, target):
        print("addRegex(self, '%s', '%s', '%s')" % (regex, cloak, target))
        sql = ('SELECT r_id FROM regex WHERE r_regex=%s;')
        args = (regex,)
        result = self.sulwatcher.querier.do(sql, args)
        if not result:
            sql = ('INSERT IGNORE INTO regex (r_regex,r_cloak,r_timestamp) '
                   'VALUES (%s,%s,%s)')
            args = (regex, cloak, time.strftime('%Y%m%d%H%M%S'))
            self.sulwatcher.querier.do(sql, args)
            if self.sulwatcher.querier.cursor.rowcount > 0:
                self.msg('%s added %s to the list of regexes. If you would '
                         'like to set a reason, say "SULWatcher: add reason '
                         '%s reason for adding the regex".'
                         % (cloak, regex, self.sulwatcher.querier.cursor.lastrowid), target)
                self.buildRegex()
        else:
            self.msg('%s is already listed as a regex.' % (regex), target)
            self.getPrintRegex(regex=regex, target=target)

    def removeRegex(self, regex=None, index=None, target=None):
        print("removeRegex(self, '%s', '%s', '%s')" % (regex, index, target))
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
        self.sulwatcher.querier.do(sql, args)
        if self.sulwatcher.querier.cursor.rowcount > 0:
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
        print("enableRegex(self, '%s', '%s')" % (index, target))
        sql = ('UPDATE regex SET r_active=1 '
               'WHERE r_id=%s;')
        args = (index,)
        self.sulwatcher.querier.do(sql, args)
        if self.sulwatcher.querier.cursor.rowcount > 0:
            self.msg('Enabled regex #%s.' % (index), target)
            self.buildRegex()

    def getRegex(self, regex=None, index=None):
        print("getRegex(self, '%s', '%s')" % (regex, index))
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
        result = self.sulwatcher.querier.do(sql, args)
        # "no results" is really one row of Nones:
        # {'hits': None, 'r_regex': None, 'r_cloak': None, 'r_id': None,
        # 'r_timestamp': None, 'r_case': None, 'r_reason': None,
        # 'r_active': None}
        # So: check if r_regex is None - if it is, the row returned is bogus
        if result[0]['r_regex'] is None:
            return None
        if result:
            return result[0]
        return None

    def getPrintRegex(self, regex=None, index=None, target=None):
        print("getPrintRegex(self, '%s', '%s', '%s')" % (regex, index, target))
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
                                          time.strptime(r['r_timestamp'],
                                                        '%Y%m%d%H%M%S'))
            except ValueError:
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
        print("addToList(self, '%s', '%s', '%s')" % (who, groupname, target))
        group_members = self.sulwatcher.get_config_result(groupname)
        if not group_members:
            self.msg("Could not find '%s'." % (groupname), target)
        elif who not in group_members:
            sql = ('INSERT INTO setup (s_param,s_value) '
                   'VALUES (%s,%s);')
            args = (groupname, who)
            self.sulwatcher.querier.do(sql, args)
            if self.sulwatcher.querier.cursor.rowcount > 0:
                self.msg('Added %s to %s.' % (who, groupname), target)
                # Rebuild whitelist if necessary
                if groupname == 'whitelist':
                    self.buildWhitelist()
        else:
            self.msg('%s is already in %s.' % (who, groupname), target)

    def removeFromList(self, who, groupname, target):
        print(
            "removeFromList(self, '%s', '%s', '%s')"
            % (who, groupname, target)
        )
        group_members = self.sulwatcher.get_config_result(groupname)
        if not group_members:
            self.msg("Could not find '%s'." % (groupname), target)
        elif who in group_members:
            sql = ('DELETE FROM setup WHERE s_param=%s AND s_value=%s;')
            args = (groupname, who)
            self.sulwatcher.querier.do(sql, args)
            if self.sulwatcher.querier.cursor.rowcount > 0:
                self.msg('Removed %s from %s.' % (who, groupname), target)
                # Rebuild whitelist if necessary
                if groupname == 'whitelist':
                    self.buildWhitelist()
        else:
            self.msg('%s is not in %s.' % (who, groupname), target)

    def msg(self, message, target=None):
        # print("msg(self, '%s', '%s')" % (message, target))
        if not target:
            target = self.channel
        self.connection.privmsg(target, message)

    def getCloak(self, mask):
        """
        Parse a hostmask, extracting the cloak part:

        nick!~user@host.com -> host.com
        """
        # print("getCloak(self, '%s')" % mask)
        if "@" in mask:
            return mask.split("@")[1]
        raise ParseHostMaskError("Hostmask %s seems invalid." % mask)

    def getUser(self, mask):
        """
        Parse a hostmask, extracting the user part:

        nick!~user@host.com -> ~user
        """
        # print("getUser(self, '%s')" % mask)
        if "!" in mask and "@" in mask:
            return mask.split("!")[1].split("@")[0]
        raise ParseHostMaskError("Hostmask %s seems invalid." % mask)

    def getNick(self, mask):
        """
        Parse a hostmask, extracting the nick part:

        nick!~user@host.com -> nick
        """
        # print("getNick(self, '%s')" % mask)
        if "!" in mask:
            return mask.split("!")[0]
        raise ParseHostMaskError("Hostmask %s seems invalid." % mask)


class EventstreamsListener:
    def __init__(self, sulwatcher):
        self.sulwatcher = sulwatcher

    def start(self):
        counter = 0
        url = "https://stream.wikimedia.org/v2/stream/recentchange"
        ca = "https://meta.wikimedia.org/wiki/Special:CentralAuth/"
        while not self.sulwatcher.eventstreams_stop.isSet():  # Thread will die when there isn't anything in the EventStream. Keep alive.
            for event in EventStream(url):  # Listen to EventStream
                if self.sulwatcher.eventstreams_stop.isSet():  # Check flag inside loop
                    break
                if event.event != 'message':
                    continue

                try:
                    change = json.loads(event.data)

                    if change['type'] != 'log':  # We don't want edits
                        continue
                    if change['log_type'] != 'newusers':  # We only want newusers, not blocks or etc
                        continue

                    bad = False
                    good = False
                    matches = []
                    botsay = None

                    for (idx, bw) in badwords:  # Use old method for checking badwords
                        if re.search(bw, change['user']):
                            bad = True
                            matches.append(bw.pattern)
                    for wl in whitelist:  # Use old method to check for whitelist
                        if change['user'] == wl:
                            print("Skipped '%s'; user is whitelisted" % change['user'])
                            good = True

                    if not bad and not good:  # Use old method to build bot spam
                        botsay = "\x0303{0} \x0302{1}{2}\x03".format(
                            change['user'],
                            ca,
                            quote(change['user']).replace('.', "%2E")
                        )
                    elif bad and not good:
                        for m in matches:
                            try:
                                sql = ('INSERT INTO logging (l_regex,l_user,'
                                       'l_timestamp) VALUES '
                                       '(%s,%s,%s);')
                                args = (m, change['user'], time.strftime('%Y%m%d%H%M%S'))
                                self.sulwatcher.querier.do(sql, args)
                            except Exception:
                                print('Could not log hit to database.')
                        botsay = "\x0303{0} \x0305\x02 matches badword {1} \017: \x0302{2}{3}\x03".format(
                            change['user'],
                            '; '.join(matches),
                            ca,
                            quote(change['user']).replace('.', "%2E")
                        )

                    if botsay is not None:
                        self.sulwatcher.irc_bots[counter % len(self.sulwatcher.irc_bots)].msg(botsay)
                        counter += 1
                except ValueError:  # Sometimes EventStream sends garbage. Catch and throw it away
                    pass
                except Exception as e:  # Should be specific about what might happen here
                    print(
                        'RC reader error: %s %s %s'
                        % (sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
                    )
                    self.sulwatcher.irc_bots[0].msg(str(e))


class EventstreamsThread(threading.Thread):
    def __init__(self, listener):
        threading.Thread.__init__(self)
        self.listener = listener

    def run(self):
        self.listener.start()


class IgnoreErrorsBuffer(buffer.DecodingLineBuffer):
    def handle_exception(self):
        pass


class BotThread(threading.Thread):
    def __init__(self, bot):
        threading.Thread.__init__(self)
        self.bot = bot

    def run(self):
        self.bot.start()


class SULWatcher:
    """
    Main SULWatcher class holding references to other objects.
    """

    def __init__(self):
        # TODO: those should not be hardcoded
        self.querier = Querier(host="tools.db.svc.eqiad.wmflabs", db="s51541__sulwatcher")

        self.irc_bots = None
        self.eventstreams_stop = None
        self.eventstreams_listener = None

    def get_config_result(self, key):
        print('getConfig(%s)' % key)
        result = [r['s_value'] for r in self.querier.do('SELECT s_value FROM setup WHERE s_param = %s;', (key, ))]
        if len(result) > 1:
            return result
        if len(result) == 1:
            return result[0]
        return None

    def start_irc_bots(self):
        if self.irc_bots is None:
            irc_password = self.get_config_result('password')
            irc_server = self.get_config_result('server')
            irc_channel = self.get_config_result('channel')
            self.irc_bots = [
                FreenodeBot(self, irc_channel, self.get_config_result('nickname'), irc_server, irc_password),
                FreenodeBot(self, irc_channel, self.get_config_result('alias'), irc_server, irc_password),
                FreenodeBot(self, irc_channel, self.get_config_result('alias2'), irc_server, irc_password),
            ]

        for bot in self.irc_bots:
            print("starting", bot.nickname)
            BotThread(bot).start()

    def start_eventstreams(self):
        if self.eventstreams_listener is None:
            self.eventstreams_listener = EventstreamsListener(self)
        if self.eventstreams_stop is None:
            self.eventstreams_stop = threading.Event()
        else:
            self.eventstreams_stop.clear()

        EventstreamsThread(self.eventstreams_listener).start()
        print("starting EventStream")

    def start_bots(self):
        """Start all the bots"""
        self.start_irc_bots()
        self.start_eventstreams()


def main():
    sulwatcher = SULWatcher()
    try:
        sulwatcher.start_bots()
    except KeyboardInterrupt:
        pass
    finally:
        for bot in sulwatcher.irc_bots:
            bot.die()

        sulwatcher.eventstreams_stop.set()


if __name__ == "__main__":
    main()
