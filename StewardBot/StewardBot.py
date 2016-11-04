#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import random
import re
import string
import sys
import threading
import time

import MySQLdb
import config

# needs python-irclib
from ircbot import SingleServerIRCBot
from irclib import nm_to_n

# DB data
dbfile = open(os.path.expanduser('~/.my.cnf'), 'r')
li = [l.strip("\n") for l in dbfile.readlines()[1:]]
dbfile.close()
SQLuser = li[0].split("=")[1].strip()
SQLpassword = li[1].split("=")[1].strip().strip("\"")
SQLhost = li[2].split("=")[1].strip().strip("\"")
SQLdb = 'YOURDBNAME'

# common queries
queries = {
    "privcloaks": "(select p_cloak from privileged) union (select s_cloak from stewards)",
    "ignoredusers": "(select i_username from ignored) union (select s_username from stewards)",
    "stalkedpages": "select f_page from followed",
    "listenedchannels": "select l_channel from listen",
    "stewardusers": "select s_username from stewards",
    "stewardnicks": "select s_nick from stewards",
    "stewardoptin": "select s_nick from stewards where s_optin=1",
}


def query(sqlquery, one=True):
    db = MySQLdb.connect(db=SQLdb, host=SQLhost,
                         user=SQLuser, passwd=SQLpassword)
    cursor = db.cursor()
    cursor.execute(sqlquery)
    db.close()
    res = list(cursor.fetchall())
    list.sort(res)
    if one:
        res2 = []
        for i in res:
            if i[0] is not None:
                res2 += [i[0]]
        return res2
    else:
        return res


def modquery(sqlquery):
    db = MySQLdb.connect(db=SQLdb, host=SQLhost,
                         user=SQLuser, passwd=SQLpassword)
    cursor = db.cursor()
    cursor.execute(sqlquery)
    db.commit()
    db.close()


class FreenodeBot(SingleServerIRCBot):

    def __init__(self):
        self.server = config.server
        self.channel = config.channel
        self.nickname = config.nick
        self.password = config.password
        self.owner = config.owner
        self.privileged = query(queries["privcloaks"])
        self.listened = query(queries["listenedchannels"])
        self.optin = query(queries["stewardoptin"])
        self.steward = query(queries["stewardnicks"])
        self.quiet = False
        self.notify = True
        self.randmess = False
        self.listen = True
        self.badsyntax = "Unrecognized command. Type @help for more info."
        self.ignore_attention = {}
        self.attention_delay = 900  # 15 minutes
        self.execute_every(
            self.attention_delay, self.do_clean_ignore_attention)
        SingleServerIRCBot.__init__(
            self, [(self.server, 6667)], self.nickname, self.nickname)

    def execute_every(self, period, func):
        """Monkey patch execute_every into irclib 0.4.8."""
        # FIXME: run a modern irclib from a virtualenv instead
        self._execute_and_schedule(period, func, do_exec=False)

    def _execute_and_schedule(self, period, func, do_exec=True):
        """Execute a function and then schedule another execution."""
        if do_exec:
            func()
        self.execute_delayed(
            period, self._execute_and_schedule, (period, func))

    def on_error(self, c, e):
        print e.target()
        self.die()

    def on_nicknameinuse(self, c, e):
        c.nick(c.get_nickname() + "_")
        time.sleep(1)  # latency problem?
        c.privmsg("NickServ", 'GHOST ' + self.nickname + ' ' + self.password)
        c.nick(self.nickname)
        time.sleep(1)  # latency problem?
        c.privmsg("NickServ", 'IDENTIFY ' + self.password)

    def on_welcome(self, c, e):
        c.privmsg("NickServ", 'GHOST ' + self.nickname + ' ' + self.password)
        c.privmsg("NickServ", 'IDENTIFY ' + self.password)
        time.sleep(5)  # let identification succeed before joining channels
        c.join(self.channel)
        if self.listen and self.listened:
            for chan in self.listened:
                c.join(chan)

    def on_ctcp(self, c, e):
        if e.arguments()[0] == "VERSION":
            c.ctcp_reply(
                nm_to_n(e.source()), "Bot for informing Wikimedia stewards on " + self.channel)
        elif e.arguments()[0] == "PING":
            if len(e.arguments()) > 1:
                c.ctcp_reply(nm_to_n(e.source()), "PING " + e.arguments()[1])

    def on_action(self, c, e):
        who = "<" + self.channel + "/" + nm_to_n(e.source()) + "> "
        print "[" + time.strftime("%d.%m.%Y %H:%M:%S") + "] * " + who + e.arguments()[0]

    def on_privmsg(self, c, e):
        nick = nm_to_n(e.source())
        a = e.arguments()[0]
        nocando = "This command cannot be used via query!"
        print "[" + time.strftime("%d.%m.%Y %H:%M:%S") + "] <private/" + nick + "> " + a
        if a[0] == "@" or a.lower().startswith(self.nickname.lower() + ":"):
            if a[0] == "@":
                command = a[1:]
            else:
                command = re.sub("(?i)%s:" %
                                 self.nickname.lower(), "", a).strip(" ")
            if command.lower() == "die":
                if self.getcloak(e.source()) == self.owner:
                    self.do_command(e, command)
                else:
                    self.msg(nocando, nick)
            elif self.getcloak(e.source()).lower() in self.privileged:
                self.do_command(e, string.strip(command), nick)
            else:
                self.msg(self.badsyntax, nick)
        elif a.lower().startswith("!steward"):
            # Reject !steward messages sent as private messages to the bot
            self.msg(nocando, nick)
        elif self.getcloak(e.source()).lower() == self.owner:
            if a[0] == "!":
                self.connection.action(self.channel, a[1:])
            else:
                self.msg(a)

    def on_pubmsg(self, c, e):
        timestamp = "[" + time.strftime("%d.%m.%Y %H:%M:%S",
                                        time.localtime(time.time())) + "] "
        nick = nm_to_n(e.source())
        a = e.arguments()[0]
        where = e.target()
        who = "<" + where + "/" + nick + "> "
        if where == self.channel:
            print timestamp + who + a
            if a[0] == "@" or a.lower().startswith(self.nickname.lower() + ":"):
                # Start of Anti-PiR hack
                evilchars = (";", "'", '"')
                for evilchar in evilchars:
                    if evilchar in a:
                        self.msg(
                            "We do not fancy the abusive characters your command contains.", self.channel)
                        return
                # End of Anti-PiR hack

                if a[0] == "@":
                    command = a[1:]
                else:
                    command = re.sub("(?i)%s:" %
                                     self.nickname.lower(), "", a).strip(" ")
                if command.lower() in ["die"] or self.startswitharray(command.lower(), ["steward", "huggle", "help", "privileged list", "ignored list", "stalked list", "listen list", "stew users", "stew nicks", "stew optin", "stew info"]):
                    self.do_command(e, string.strip(command))
                elif self.getcloak(e.source()) and self.getcloak(e.source()).lower() in self.privileged:
                    self.do_command(e, string.strip(command))
                else:
                    # if not self.quiet: self.msg("You're not allowed to issue commands.")
                    pass
        if a.lower().startswith("!steward"):
            if where != self.channel:
                print timestamp + who + a
            reason = re.sub("(?i)!steward", "", a).strip(" ")
            self.attention(nick, where, reason)

    def do_command(self, e, cmd, target=None):
        nick = nm_to_n(e.source())
        if not target:
            target = self.channel
        c = self.connection

        # On/Off
        if cmd.lower() == "quiet":
            if not self.quiet:
                self.msg("I'll be quiet :(", target)
                self.quiet = True
        elif cmd.lower() == "speak":
            if self.quiet:
                self.msg("Back in action :)", target)
                self.quiet = False
        elif cmd.lower() == "mlock":
            if not self.quiet:
                self.msg("You have 10 seconds!", target)
                self.quiet = True
                time.sleep(10)
                self.quiet = False
        elif cmd.lower() == "notify on":
            if not self.notify:
                self.msg("Notification on", target)
                self.notify = True
        elif cmd.lower() == "notify off":
            if self.notify:
                self.msg("Notification off", target)
                self.notify = False
        elif cmd.lower() == "randmsg on":
            if not self.randmess:
                self.msg("Message notification on", target)
                self.randmess = True
        elif cmd.lower() == "randmsg off":
            if self.randmess:
                self.msg("Message notification off", target)
                self.randmess = False

        # Notifications
        elif cmd.lower().startswith("steward"):
            self.attention(nick, ping=self.optin)

        # Privileged
        elif cmd.lower().startswith("privileged"):
            self.do_privileged(re.sub("(?i)^privileged", "",
                                      cmd).strip(" "), target, nick)

        # Ignored
        elif cmd.lower().startswith("ignored"):
            self.do_ignored(re.sub("(?i)^ignored", "",
                                   cmd).strip(" "), target, nick)

        # Stalked
        elif cmd.lower().startswith("stalked"):
            self.do_stalked(re.sub("(?i)^stalked", "",
                                   cmd).strip(" "), target, nick)

        # Listen
        elif cmd.lower().startswith("listen"):
            self.do_listen(
                re.sub("(?i)^listen", "", cmd).strip(" "), target, nick)

        # Stewards
        elif cmd.lower().startswith("stew"):
            self.do_steward(
                re.sub("(?i)^stew", "", cmd).strip(" "), target, nick)

        # Help
        elif cmd.lower() == "help":
            self.msg(
                "Help = https://tools.wmflabs.org/stewardbots/StewardBot/StewardBot.html", nick)

        # Test
        elif cmd.lower() == "test":
            if bot2.testregister:
                self.msg(bot2.testregister, nick)

        # Huggle
        elif cmd.lower().startswith("huggle"):
            who = cmd[6:].strip(" ")
            self.connection.action(self.channel, "huggles " + who)

        # Die
        elif cmd.lower() == "die":
            if self.getcloak(e.source()) != self.owner:
                if not self.quiet:
                    self.msg("You can't kill me; you're not my owner! :P")
            else:
                self.msg("Goodbye!")
                c.part(self.channel, ":Process terminated.")
                bot2.connection.part(bot2.channel)
                if self.listen and self.listened:
                    for chan in self.listened:
                        self.connection.part(chan, ":Process terminated.")
                bot2.connection.quit()
                bot2.disconnect()
                c.quit()
                self.disconnect()
                os._exit(os.EX_OK)

        # Other
        elif not self.quiet:
            pass  # self.msg(self.badsyntax, target)

    def attention(self, nick, channel=None, reason=None, ping=None):
        if ping is None:
            ping = self.stewards
        if self.notify:
            now = time.time()
            if nick in self.ignore_attention:
                if self.ignore_attention[nick] > now:
                    print "[%s] ignoring attention from %s until @%d" % (
                        time.strftime("%d.%m.%Y %H:%M:%S"),
                        nick,
                        self.ignore_attention[nick]
                    )
                    return
            self.ignore_attention[nick] = now + self.attention_delay

            if not channel or channel == self.channel:
                self.msg("Stewards: Attention requested by %s ( %s )" %
                         (nick, " ".join(ping)))
            else:
                self.msg("Stewards: Attention requested ( %s )" %
                         (" ".join(ping)))
                messg = "Attention requested by %s on %s" % (nick, channel)
                if reason:
                    messg += " with the following reason: " + reason
                self.msg(messg)

    def do_clean_ignore_attention(self):
        """Clean expired items out of the ignore_attention cache."""
        now = time.time()
        for nick in self.ignore_attention.keys():
            if self.ignore_attention[nick] <= now:
                del self.ignore_attention[nick]

    def do_privileged(self, cmd, target, nick):
        if cmd.lower().startswith("list"):
            who = re.sub("(?i)^list", "", cmd).strip(" ")
            who = who.split(" ")[0]
            if who in ["all", "*"]:
                privnicks = query(
                    "(select p_nick from privileged) union (select s_nick from stewards)")
                self.msg("privileged nicks (including stewards): " +
                         ", ".join(privnicks), nick)
            else:
                privnicks = query("select p_nick from privileged")
                self.msg("privileged nicks: " + ", ".join(privnicks), nick)
        elif cmd.lower().startswith("get"):
            who = re.sub("(?i)^get", "", cmd).strip(" ")
            who = who.split(" ")[0]
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a nick", target)
            else:
                privcloak = query(
                    'select p_cloak from privileged where p_nick="%s"' % who)
                if len(privcloak) == 0:
                    self.msg(
                        "%s is not in the list of privileged users!" % who, target)
                else:
                    self.msg("The cloak of privileged user %s is %s" %
                             (who, privcloak[0]), target)
        elif cmd.lower().startswith("add"):
            who = re.sub("(?i)^add", "", cmd).strip(" ")
            wholist = who.split(" ")
            if len(wholist) < 2:
                if not self.quiet:
                    self.msg("You have to specify a nick and a cloak", target)
            else:
                pnick = wholist[0]
                pcloak = wholist[1].lower()
                if len(query('select p_nick from privileged where p_nick="%s"' % pnick)) > 0:
                    if not self.quiet:
                        self.msg("%s is already privileged!" % pnick, target)
                else:
                    modquery(
                        'insert into privileged values (0, "%s", "%s")' % (pnick, pcloak))
                    # update the list of privileged cloaks
                    self.privileged = query(queries["privcloaks"])
                    if not self.quiet:
                        self.msg(
                            "%s added to the list of privileged users!" % pnick, target)
        elif self.startswitharray(cmd.lower(), ["remove", "delete"]):
            who = re.sub("(?i)^(remove|delete)", "", cmd).strip(" ")
            who = who.split(" ")[0]
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a nick", target)
            else:
                if len(query('select p_nick from privileged where p_nick="%s"' % who)) == 0:
                    if not self.quiet:
                        self.msg(
                            "%s is not in the list of privileged users!" % who, target)
                else:
                    modquery('delete from privileged where p_nick="%s"' % who)
                    # update the list of privileged cloaks
                    self.privileged = query(queries["privcloaks"])
                    if not self.quiet:
                        self.msg(
                            "%s removed from the list of privileged users!" % who, target)
        elif self.startswitharray(cmd.lower(), ["change", "edit", "modify", "rename"]):
            who = re.sub("(?i)^(change|edit|modify|rename)",
                         "", cmd).strip(" ")
            wholist = who.split(" ")
            if len(wholist) < 2:
                if not self.quiet:
                    self.msg(
                        "You have to specify a nick and a cloak or another nick", target)
            else:
                pnick = wholist[0]
                pcloak = wholist[1]
                renamecloak = False
                if "/" in pcloak:
                    pcloak = pcloak.lower()
                    renamecloak = True
                if len(query('select p_nick from privileged where p_nick="%s"' % pnick)) == 0:
                    if not self.quiet:
                        self.msg(
                            "%s is not in the list of privileged users!" % pnick, target)
                else:
                    if renamecloak:
                        modquery(
                            'update privileged set p_cloak = "%s" where p_nick = "%s"' % (pcloak, pnick))
                        # update the list of privileged cloaks
                        self.privileged = query(queries["privcloaks"])
                        if not self.quiet:
                            self.msg(
                                "Changed the cloak for %s in the list of privileged users!" % pnick, target)
                    else:
                        modquery(
                            'update privileged set p_nick = "%s" where p_nick = "%s"' % (pcloak, pnick))
                        if not self.quiet:
                            self.msg("Changed the privileged user from %s to %s!" % (
                                pnick, pcloak), target)
        else:
            if not self.quiet:
                self.msg(self.badsyntax, target)

    def do_ignored(self, cmd, target, nick):
        if cmd.lower().startswith("list"):
            who = re.sub("(?i)^list", "", cmd).strip(" ")
            who = who.split(" ")[0]
            if who in ["all", "*"]:
                ignoredusers = query(queries["ignoredusers"])
                self.msg("ignored users (including stewards): " +
                         ", ".join(ignoredusers), nick)
            else:
                ignoredusers = query("select i_username from ignored")
                self.msg("ignored users: " + ", ".join(ignoredusers), nick)
        elif cmd.lower().startswith("add"):
            who = re.sub("(?i)^add", "", cmd).strip(" ")
            who = who.split(" ")[0]
            who = who.replace("_", " ")
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a username", target)
            else:
                who = who[0].upper() + who[1:]
                if len(query('select i_username from ignored where i_username="%s"' % who)) > 0:
                    if not self.quiet:
                        self.msg("%s is already ignored!" % who, target)
                else:
                    modquery('insert into ignored values (0, "%s")' % who)
                    # update the list of ignored users
                    bot2.ignored = query(queries["ignoredusers"])
                    if not self.quiet:
                        self.msg(
                            "%s added to the list of ignored users!" % who, target)
        elif self.startswitharray(cmd.lower(), ["remove", "delete"]):
            who = re.sub("(?i)^(remove|delete)", "", cmd).strip(" ")
            who = who.split(" ")[0]
            who = who.replace("_", " ")
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a username", target)
            else:
                who = who[0].upper() + who[1:]
                if len(query('select i_username from ignored where i_username="%s"' % who)) == 0:
                    if not self.quiet:
                        self.msg(
                            "%s is not in the list of ignored users!" % who, target)
                else:
                    modquery('delete from ignored where i_username="%s"' % who)
                    # update the list of ignored users
                    bot2.ignored = query(queries["ignoredusers"])
                    if not self.quiet:
                        self.msg(
                            "%s removed from the list of ignored users!" % who, target)
        elif self.startswitharray(cmd.lower(), ["change", "edit", "modify", "rename"]):
            who = re.sub("(?i)^(change|edit|modify|rename)",
                         "", cmd).strip(" ")
            wholist = who.split(" ")
            if len(wholist) < 2:
                if not self.quiet:
                    self.msg("You have to specify two usernames", target)
            else:
                iuser1 = wholist[0]
                iuser2 = wholist[1]
                iuser1 = iuser1[0].upper() + iuser1[1:]
                iuser2 = iuser2[0].upper() + iuser2[1:]
                iuser1 = iuser1.replace("_", " ")
                iuser2 = iuser2.replace("_", " ")
                if len(query('select i_username from ignored where i_username="%s"' % iuser1)) == 0:
                    if not self.quiet:
                        self.msg("%s is not in the list of ignored users!" %
                                 iuser1, target)
                else:
                    modquery('update ignored set i_username = "%s" where i_username = "%s"' % (
                        iuser2, iuser1))
                    # update the list of ignored users
                    bot2.ignored = query(queries["ignoredusers"])
                    if not self.quiet:
                        self.msg(
                            "Changed the username of %s in the list of ignored users!" % iuser1, target)
        else:
            if not self.quiet:
                self.msg(self.badsyntax, target)

    def do_stalked(self, cmd, target, nick):
        if cmd.lower().startswith("list"):
            stalkedpages = query(queries["stalkedpages"])
            self.msg("stalked pages: " + ", ".join(stalkedpages), target)
        elif cmd.lower().startswith("add"):
            who = re.sub("(?i)^add", "", cmd).strip(" ")
            who = who.split(" ")[0]
            who = who.replace("_", " ")
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a page name", target)
            else:
                who = who[0].upper() + who[1:]
                if len(query('select f_page from followed where f_page="%s"' % who)) > 0:
                    if not self.quiet:
                        self.msg("%s is already stalked!" % who, target)
                else:
                    modquery('insert into followed values (0, "%s")' % who)
                    # update the list of stalked pages
                    bot2.stalked = query(queries["stalkedpages"])
                    if not self.quiet:
                        self.msg(
                            "%s added to the list of stalked pages!" % who, target)
        elif self.startswitharray(cmd.lower(), ["remove", "delete"]):
            who = re.sub("(?i)^(remove|delete)", "", cmd).strip(" ")
            who = who.split(" ")[0]
            who = who.replace("_", " ")
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a page name", target)
            else:
                who = who[0].upper() + who[1:]
                if len(query('select f_page from followed where f_page="%s"' % who)) == 0:
                    if not self.quiet:
                        self.msg(
                            "%s is not in the list of stalked pages!" % who, target)
                else:
                    modquery('delete from followed where f_page="%s"' % who)
                    # update the list of stalked pages
                    bot2.stalked = query(queries["stalkedpages"])
                    if not self.quiet:
                        self.msg(
                            "%s removed from the list of stalked pages!" % who, target)
        elif self.startswitharray(cmd.lower(), ["change", "edit", "modify", "rename"]):
            who = re.sub("(?i)^(change|edit|modify|rename)",
                         "", cmd).strip(" ")
            wholist = who.split(" ")
            if len(wholist) < 2:
                if not self.quiet:
                    self.msg("You have to specify two page names", target)
            else:
                ipage1 = wholist[0]
                ipage2 = wholist[1]
                ipage1 = ipage1[0].upper() + ipage1[1:]
                ipage2 = ipage2[0].upper() + ipage2[1:]
                ipage1 = ipage1.replace("_", " ")
                ipage2 = ipage2.replace("_", " ")
                if len(query('select f_page from followed where f_page="%s"' % ipage1)) == 0:
                    if not self.quiet:
                        self.msg("%s is not in the list of stalked pages!" %
                                 ipage1, target)
                else:
                    modquery('update followed set f_page = "%s" where f_page = "%s"' % (
                        ipage2, ipage1))
                    # update the list of stalked pages
                    bot2.stalked = query(queries["stalkedpages"])
                    if not self.quiet:
                        self.msg(
                            "Changed the username of %s in the list of stalked pages!" % ipage1, target)
        else:
            if not self.quiet:
                self.msg(self.badsyntax, target)

    def do_listen(self, cmd, target, nick):
        if cmd.lower().startswith("list"):
            listenedchannels = query(queries["listenedchannels"])
            self.msg("'listen' channels: " +
                     ", ".join(listenedchannels), target)
        elif cmd.lower().startswith("add"):
            who = re.sub("(?i)^add", "", cmd).strip(" ")
            who = who.split(" ")[0]
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a channel", target)
            else:
                if not who.startswith("#"):
                    who = "#" + who
                if len(query('select l_channel from listen where l_channel="%s"' % who)) > 0:
                    if not self.quiet:
                        self.msg(
                            "%s is already in the list of 'listen' channels!" % who, target)
                else:
                    modquery('insert into listen values (0, "%s")' % who)
                    # update the list of listened channels
                    self.listened = query(queries["listenedchannels"])
                    if not self.quiet:
                        self.msg(
                            "%s added to the list of 'listen' channels!" % who, target)
                    self.connection.join(who)
        elif self.startswitharray(cmd.lower(), ["remove", "delete"]):
            who = re.sub("(?i)^(remove|delete)", "", cmd).strip(" ")
            who = who.split(" ")[0]
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a channel", target)
            else:
                if not who.startswith("#"):
                    who = "#" + who
                if len(query('select l_channel from listen where l_channel="%s"' % who)) == 0:
                    if not self.quiet:
                        self.msg(
                            "%s is not in the list of 'listen' channels!" % who, target)
                else:
                    modquery('delete from listen where l_channel="%s"' % who)
                    # update the list of listened channels
                    self.listened = query(queries["listenedchannels"])
                    if not self.quiet:
                        self.msg(
                            "%s removed from the list of 'listen' channels!" % who, target)
                    self.connection.part(
                        who, "Requested by " + nick + " in " + self.channel)
        elif self.startswitharray(cmd.lower(), ["change", "edit", "modify", "rename"]):
            who = re.sub("(?i)^(change|edit|modify|rename)",
                         "", cmd).strip(" ")
            wholist = who.split(" ")
            if len(wholist) < 2:
                if not self.quiet:
                    self.msg("You have to specify two channels", target)
            else:
                chan1 = wholist[0]
                chan2 = wholist[1]
                if not chan1.startswith("#"):
                    chan1 = "#" + chan1
                if not chan2.startswith("#"):
                    chan2 = "#" + chan2
                if len(query('select l_channel from listen where l_channel="%s"' % chan1)) == 0:
                    if not self.quiet:
                        self.msg(
                            "%s is not in the list of stalked pages!" % chan1, target)
                else:
                    modquery(
                        'update listen set l_channel = "%s" where l_channel = "%s"' % (chan2, chan1))
                    # update the list of listened channels
                    bot2.stalked = query(queries["listenedchannels"])
                    if not self.quiet:
                        self.msg(
                            "Changed the name of %s in the list of 'listen' channels!" % chan1, target)
                    self.connection.part(
                        chan1, "Requested by " + nick + " in " + self.channel)
                    self.connection.join(chan2)
        elif cmd.lower().startswith("on"):
            if not self.listen and self.listened:
                for chan in self.listened:
                    self.connection.join(chan)
                if not self.quiet:
                    self.msg("Joined the 'listen' channels.", target)
                self.listen = True
        elif cmd.lower().startswith("off"):
            if self.listen and self.listened:
                for chan in self.listened:
                    self.connection.part(chan)
                if not self.quiet:
                    self.msg("Parted the 'listen' channels.", target)
                self.listen = False
        else:
            if not self.quiet:
                self.msg(self.badsyntax, target)

    def do_steward(self, cmd, target, nick):
        if cmd.lower().startswith("users"):
            stewusers = query(queries["stewardusers"])
            self.msg("steward usernames: " + ", ".join(stewusers), nick)
        elif cmd.lower().startswith("nicks"):
            stewnicks = query(queries["stewardnicks"])
            self.msg("steward nicks: " + ", ".join(stewnicks), nick)
        elif cmd.lower().startswith("optin"):
            stewnicks = query(queries["stewardoptin"])
            self.msg("steward nicks: " + ", ".join(stewnicks), nick)
        elif cmd.lower().startswith("info"):
            who = re.sub("(?i)^info", "", cmd).strip(" ")
            who = who.split(" ")[0]
            who = who.replace("_", " ")
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a username", target)
            else:
                who = who[0].upper() + who[1:]
                stewinfo = query(
                    'select s_nick, s_cloak, s_optin from stewards where s_username="%s"' % who, False)
                if len(stewinfo) == 0:
                    self.msg("%s is not a steward!" % who, target)
                else:
                    stewout = "Steward " + who
                    if stewinfo[0][0] is None:
                        stewout += " doesn't have a registered nickname on IRC."
                    else:
                        stewout += " uses nick " + stewinfo[0][0]
                        if stewinfo[0][1] is None:
                            stewout += " and doesn't have a cloak set"
                        else:
                            stewout += " with the cloak " + stewinfo[0][1]
                        if stewinfo[0][2] == 0:
                            soptin = "n't"
                        else:
                            soptin = ""
                        stewout += ". %s is%s in the list of opt-in nicks." % (stewinfo[0][
                                                                               0], soptin)
                    self.msg(stewout, target)
        elif cmd.lower().startswith("add"):
            who = re.sub("(?i)^add", "", cmd).strip(" ")
            who = re.sub(" +", " ", who)
            wholist = who.split(" ")
            wllen = len(wholist)
            if wllen == 0:
                if not self.quiet:
                    self.msg(
                        "You have to specify username, and optionally nick, cloak and opt-in preference", target)
            else:
                suser = wholist[0]
                suser = suser[0].upper() + suser[1:]
                suser = suser.replace("_", " ")
                snick = "null"
                scloak = "null"
                soptin = "0"
                if wllen >= 2:
                    snick = '"%s"' % wholist[1]
                    if wllen >= 3:
                        if wholist[2] != "-":
                            scloak = '"%s"' % wholist[2].lower()
                        if wllen >= 4:
                            if wholist[3].lower() in ["yes", "true", "1"]:
                                soptin = "1"
                            elif wholist[3].lower() in ["no", "false", "0"]:
                                soptin = "0"
                if len(query('select s_username from stewards where s_username="%s"' % suser)) > 0:
                    if not self.quiet:
                        self.msg("%s is already in the list of stewards!" %
                                 suser, target)
                else:
                    modquery('insert into stewards values (0, "%s", %s, %s, %s)' % (
                        suser, snick, scloak, soptin))
                    # update the list of steward nicks
                    self.steward = query(queries["stewardnicks"])
                    # update the list of steward opt-in nicks
                    self.optin = query(queries["stewardoptin"])
                    # update the list of privileged cloaks
                    self.privileged = query(queries["privcloaks"])
                    # update the list of ignored users
                    bot2.ignored = query(queries["ignoredusers"])
                    if not self.quiet:
                        self.msg("%s added to the list of stewards!" %
                                 suser, target)
        elif self.startswitharray(cmd.lower(), ["remove", "delete"]):
            who = re.sub("(?i)^(remove|delete)", "", cmd).strip(" ")
            who = who.split(" ")[0]
            who = who.replace("_", " ")
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a username", target)
            else:
                who = who[0].upper() + who[1:]
                if len(query('select s_username from stewards where s_username="%s"' % who)) == 0:
                    if not self.quiet:
                        self.msg("%s is not a steward!" % who, target)
                else:
                    modquery('delete from stewards where s_username="%s"' % who)
                    # update the list of steward nicks
                    self.steward = query(queries["stewardnicks"])
                    # update the list of steward opt-in nicks
                    self.optin = query(queries["stewardoptin"])
                    # update the list of privileged cloaks
                    self.privileged = query(queries["privcloaks"])
                    # update the list of ignored users
                    bot2.ignored = query(queries["ignoredusers"])
                    if not self.quiet:
                        self.msg("%s removed from the list of stewards!" %
                                 who, target)
        elif self.startswitharray(cmd.lower(), ["change", "edit", "modify", "rename"]):
            who = re.sub("(?i)^(change|edit|modify|rename)",
                         "", cmd).strip(" ")
            wholist = who.split(" ")
            wllen = len(wholist)
            if wllen < 2:
                if not self.quiet:
                    self.msg(
                        "You have to specify two usernames, and optionally nick, cloak and opt-in preference", target)
            else:
                suser1 = wholist[0]
                suser2 = wholist[1]
                suser1 = suser1.replace("_", " ")
                suser2 = suser2.replace("_", " ")
                setlist = []
                if suser2 != "-":
                    setlist += ['s_username = "%s"' % suser2]
                if wllen >= 3:
                    if wholist[2] != "-":
                        setlist += ['s_nick = "%s"' % wholist[2]]
                    if wllen >= 4:
                        if wholist[3] != "-":
                            setlist += ['s_cloak = "%s"' % wholist[3].lower()]
                        if wllen >= 5:
                            if wholist[4].lower() in ["yes", "true", "1"]:
                                setlist += ['s_optin = 1']
                            elif wholist[4].lower() in ["no", "false", "0"]:
                                setlist += ['s_optin = 0']
                if len(query('select s_username from stewards where s_username="%s"' % suser1)) == 0:
                    if not self.quiet:
                        self.msg("%s is not a steward!" % suser1, target)
                else:
                    if len(setlist) == 0:
                        if not self.quiet:
                            self.msg("No change necessary!")
                    else:
                        modquery('update stewards set %s where s_username = "%s"' % (
                            ", ".join(setlist), suser1))
                        # update the list of steward nicks
                        self.steward = query(queries["stewardnicks"])
                        # update the list of steward opt-in nicks
                        self.optin = query(queries["stewardoptin"])
                        # update the list of privileged cloaks
                        self.privileged = query(queries["privcloaks"])
                        # update the list of ignored users
                        bot2.ignored = query(queries["ignoredusers"])
                        if not self.quiet:
                            self.msg("Updated information for steward %s!" %
                                     suser1, target)
        else:
            if not self.quiet:
                self.msg(self.badsyntax, target)

    def msg(self, poruka, target=None):
        if not target:
            target = self.channel
        self.connection.privmsg(target, poruka)

    def getcloak(self, doer):
        if re.search("/", doer) and re.search("@", doer):
            return doer.split("@")[1]

    def startswitharray(self, a, l):
        for i in l:
            if a.startswith(i):
                return True
        return False


class WikimediaBot(SingleServerIRCBot):

    def __init__(self):
        self.server = config.server2
        self.channel = config.channel2
        self.nickname = config.nick2
        self.stalked = query(queries["stalkedpages"])
        self.ignored = query(queries["ignoredusers"])
        self.testregister = None
        SingleServerIRCBot.__init__(
            self, [(self.server, 6667)], self.nickname, self.nickname)

    def on_error(self, c, e):
        print e.target()
        self.die()

    def on_nicknameinuse(self, c, e):
        c.nick(c.get_nickname() + "_")

    def on_welcome(self, c, e):
        c.join(self.channel)

    def on_ctcp(self, c, e):
        if e.arguments()[0] == "VERSION":
            c.ctcp_reply(nm_to_n(e.source()),
                         "Logging bot for #wikimedia-stewards")
        elif e.arguments()[0] == "PING":
            if len(e.arguments()) > 1:
                c.ctcp_reply(nm_to_n(e.source()), "PING " + e.arguments()[1])

    def on_privmsg(self, c, e):
        nick = nm_to_n(e.source())
        a = e.arguments()[0]
        if nick.lower() != "dungodung":
            c.privmsg(nick, "Please don't talk to me!")
        elif a.startswith(config.passwordhash):
            c.privmsg(nick, "Terminating the bot!")
            try:
                bot1.msg("Emergency killswitch activated!")
                bot1.connection.part(self.channel, "Process terminated.")
                if bot1.listen and bot1.listened:
                    for chan in bot1.listened:
                        bot1.connection.part(chan, "Process terminated.")
                bot1.connection.quit()
                bot1.disconnect()
            except:
                print "Bot 1 seems to have already quit!"
            c.part(self.channel)
            c.quit()
            self.disconnect()
            os._exit(os.EX_OK)
        else:
            c.privmsg(
                nick, "Type 'echo <password> | md5sum' to your linux terminal and paste the output here.")
        print "[" + time.strftime("%d.%m.%Y %H:%M:%S") + "] <!private/" + nick + "> " + a

    def on_pubmsg(self, c, e):
        self.randmess()
        timestamp = "[" + time.strftime("%d.%m.%Y %H:%M:%S",
                                        time.localtime(time.time())) + "] "
        who = "<" + self.channel + "/" + nm_to_n(e.source()) + "> "
        a = (e.arguments()[0])
        # nick = nm_to_n(e.source())
        self.testregister = timestamp + a
        if not bot1.quiet:
            # Parsing the rcbot output
            if "Special:Log/rights" in a:
                # 14[[07Special:Log/rights14]]4 rights10 02 5* 03Spacebirdy 5*  10changed group membership for 02User:Piolinfax@siwiktionary10 from (none) to sysop: per [[srp]], temp, 1 month
                # 14[[07Special:Log/rights14]]4 rights10 02 5* 03Nick1915 5*  10changed group membership for User:Poppy@frwiki from sysop to (none): http://meta.wikimedia.org/w/index.php?title=Steward_requests%2FPermissions&diff=1241753&oldid=1241325#Poppy.40fr.wikipedia
                comp = re.compile("14\[\[07Special:Log/rights14\]\]4 rights10 02(?P<extra>.*?) 5\* 03(?P<usersource>.+?) 5\* +10changed group membership for (02)?User:(?P<usertarget>.+?)(10)? from (?P<state1>.+?) to (?P<state2>.+?)(: (?P<comment>.+))?", re.DOTALL)
                found = comp.search(a)
                print timestamp + who + a
                if not found:
                    print "!!! Error!"
                    return
                usersource = found.group('usersource')
                usertarget = found.group('usertarget')
                state1 = found.group('state1')
                state2 = found.group('state2')
                extra = found.group('extra')
                if extra:
                    print "!!! There are extra parameters!"
                comment = found.group('comment')
                if comment:
                    comment = " with the following comment: 07" + \
                        comment.strip(" ") + ""
                else:
                    comment = ""
                selff = ""
                bott = ""
                if "@" in usertarget:
                    if usertarget.split("@")[0] == usersource:
                        selff = "6(self) "
                elif usersource == usertarget:
                    selff = "06(self) "
                if "bot" in state1 or "bot" in state2:
                    bott = "06(bot) "
                bot1.msg("%s%s03%s changed user rights for %s from 04%s to 04%s%s" % (
                    selff, bott, usersource, usertarget, state1, state2, comment))
            elif "Special:Log/gblblock" in a:
                if "gblock2" in a:
                    # [[Special:Log/gblblock]] gblock2  * Pathoschild *  globally blocked [[User:190.198.116.53]] (anonymous only, expires 15:18, 28 April 2009): crosswiki abuse, likely proxy
                    comp = re.compile(
                        "14\[\[07Special:Log/gblblock14\]\]4 gblock210 02(?P<extra>.*?) 5\* 03(?P<usersource>.+?) 5\* +10(?P<didwhat>.+?) \[\[02User:(?P<usertarget>.+?)10\]\] \((?P<expiry>.+?)\)(: (?P<comment>.+))?", re.DOTALL)
                    found = comp.search(a)
                    print timestamp + who + a
                    if not found:
                        print "!!! Error!"
                        return
                    expiry = found.group('expiry')
                    expiry = " (%s)" % expiry
                elif "modify" in a:
                    # [[Special:Log/gblblock]] modify  * Dungodung *  modified the global block on [[User:1.2.3.4]] (expires 15:34, March 28, 2009): testing
                    comp = re.compile(
                        "14\[\[07Special:Log/gblblock14\]\]4 modify10 02(?P<extra>.*?) 5\* 03(?P<usersource>.+?) 5\* +10(?P<didwhat>.+?) \[\[02User:(?P<usertarget>.+?)10\]\] \((?P<expiry>.+?)\)(: (?P<comment>.+))?", re.DOTALL)
                    found = comp.search(a)
                    print timestamp + who + a
                    if not found:
                        print "!!! Error!"
                        return
                    expiry = found.group('expiry')
                    expiry = " (%s)" % expiry
                elif "gunblock" in a:
                    # [[Special:Log/gblblock]] gunblock  * Pathoschild *  removed global block on [[User:94.229.64.0/19]]: oops
                    comp = re.compile(
                        "14\[\[07Special:Log/gblblock14\]\]4 gunblock10 02(?P<extra>.*?) 5\* 03(?P<usersource>.+?) 5\* +10(?P<didwhat>.+?) \[\[02User:(?P<usertarget>.+?)10\]\](: (?P<comment>.+))?", re.DOTALL)
                    found = comp.search(a)
                    print timestamp + who + a
                    if not found:
                        print "!!! Error!"
                        return
                    expiry = ""
                else:
                    print "!!! Error!"
                    return
                usersource = found.group('usersource')
                didwhat = found.group('didwhat')
                usertarget = found.group('usertarget')
                extra = found.group('extra')
                if extra:
                    print "!!! There are extra parameters!"
                comment = found.group('comment')
                if comment:
                    comment = " with the following comment: 7" + \
                        comment.strip(" ") + ""
                else:
                    comment = ""
                bot1.msg("03%s %s %s%s%s" %
                         (usersource, didwhat, usertarget, expiry, comment))
            elif "Special:Log/globalauth" in a:
                # 14[[07Special:Log/globalauth14]]4 ***action***10 02 5* 03***who*** 5*  10***text*** global account "<nowiki>02User:***user***@global10</nowiki>": ***opt-comment***
                # 14[[07Special:Log/globalauth14]]4 unlock10 02 5* 03Spacebirdy 5*  10unlocked global account "<nowiki>User:Bluegoblin7@global</nowiki>": user claims to be not involved in the vandalism
                # [[Special:Log/globalauth]] setstatus  * Dungodung *  changed status for global account "<nowiki>User:Pathoschild2@global</nowiki>": Set hidden; Unset locked: test
                comp = re.compile(
                    "14\[\[07Special:Log/globalauth14\]\]4 (?P<action1>.+?)10 02(?P<extra>.*?) 5\* 03(?P<usersource>.+?) 5\* +10(?P<action2>.+?) global account(.*?)(02)?User:(?P<usertarget>.+?)@global(10)?(.+?)(: (?P<comment>.+))?", re.DOTALL)
                found = comp.search(a)
                print timestamp + who + a
                if not found:
                    print "!!! Error!"
                    return
                usersource = found.group('usersource')
                usertarget = found.group('usertarget')
                action1 = found.group('action1')  # Don't really need it
                action2 = found.group('action2')
                extra = found.group('extra')
                if extra:
                    print "!!! There are extra parameters!"
                origcomment = comment = found.group('comment')
                hid = False
                if comment:  # Best that I could thought of without changing the structure of this branch
                    if action1 == "setstatus":
                        if ":" in comment:
                            ss1 = re.compile(
                                "set (?P<s>.+?); unset (?P<u>.+?):", re.DOTALL)
                        else:
                            ss1 = re.compile(
                                "set (?P<s>.+?); unset (?P<u>.+)", re.DOTALL)
                        ss2 = ss1.search(comment)
                        ss3set = ss2.group('s')
                        ss3unset = ss2.group('u')
                        changeda = []
                        if "hidden" in ss3set or "oculto" in ss3set or "versteckt" in ss3set:
                            changeda += ["hid"]
                            hid = True
                        if "locked" in ss3set or "Bloqueado" in ss3set or "gesperrt" in ss3set:
                            changeda += ["locked"]
                        if "oversighted" in ss3unset:
                            changeda += ["unsuppressed"]
                        if "hidden" in ss3unset or "oculto" in ss3unset or "versteckt" in ss3unset:
                            changeda += ["unhid"]
                        if "locked" in ss3unset or "Bloqueado" in ss3unset or "gesperrt" in ss3unset:
                            changeda += ["unlocked"]
                        list.sort(changeda, reverse=True)
                        action2 = " and ".join(changeda)
                        if ":" in comment:
                            comment = re.sub(
                                "set (.+?); unset (.+?): ", "", comment)
                        else:
                            comment = ""
                    if comment != "":
                        comment = " with the following comment: 07" + \
                            comment.strip(" ") + ""
                else:
                    comment = ""
                if usersource == usertarget:
                    selff = "06(self) "
                else:
                    selff = ""
                if hid:
                    usertarget = "a global account"
                else:
                    usertarget = "global account %s" % usertarget
                # HARCODED PART; TO BE REDESIGNED INTO AN EXCEPTION SYSTEM
                print usersource, origcomment
                # if usersource == 'Quentinv57' and 'spambot' in origcomment:
                #   pass
                if True:  # else:
                    bot1.msg("%s03%s %s %s%s" %
                             (selff, usersource, action2, usertarget, comment))
            elif "Special:Log/gblrights" in a:
                # 14[[07Special:Log/gblrights14]]4 groupprms210 02 5* 03Dungodung 5*  10changed group permissions for Special:GlobalUsers/test.Added move, patrol;Removed (none): testing
                # 14[[07Special:Log/gblrights14]]4 ***action***10 02 5* 03***who*** 5*  10***text***: ***opt-comment***
                comp = re.compile(
                    "14\[\[07Special:Log/gblrights14\]\]4 (?P<action>.+?)10 02(?P<extra>.*?) 5\* 03(?P<usersource>.+?) 5\* +10(?P<text>.+)", re.DOTALL)
                found = comp.search(a)
                print timestamp + who + a
                if not found:
                    print "!!! Error!"
                    return
                usersource = found.group('usersource')
                text = found.group('text')
                action = found.group('action')
                extra = found.group('extra')
                if extra:
                    print "!!! There are extra parameters!"
                outtext = text
                comment = ""
                if action == "groupprms2":
                    outtext = re.sub(
                        r"Special:GlobalUsers/(.+?)\.", r"\1: ", outtext)
                    outtext = re.sub(
                        r"added (.+?);", r"added 04\1; ", outtext)
                    outtext = re.sub(
                        r"removed (.+)", r"removed 04\1", outtext)
                    noco = len(re.findall(":", outtext))
                    if noco >= 2:
                        niz = outtext.split(":")[2:]
                        comment = ":".join(niz)
                        outtext = outtext.replace(":" + comment, "")
                elif action == "groupprms3":
                    outtext = re.sub(
                        r"02Special:GlobalUsers/(.+?)10", r"\1", outtext)
                    outtext = re.sub(r"from (.+?) to (.+)",
                                     r"from 04\1 to 04\2", outtext)
                    noco = len(re.findall(":", outtext))
                    if noco >= 1:
                        niz = outtext.split(":")[1:]
                        comment = ":".join(niz)
                        outtext = outtext.replace(":" + comment, "")
                elif action == "usergroups":
                    outtext = re.sub(
                        r"(02)?User:(.+?)(10)? from", r"\2 from", outtext)
                    outtext = re.sub(r"from (.+?) to (.+)",
                                     r"from 04\1 to 04\2", outtext)
                    noco = len(re.findall(":", outtext))
                    if noco >= 1:
                        niz = outtext.split(":")[1:]
                        comment = ":".join(niz)
                        outtext = outtext.replace(":" + comment, "")
                elif action == "newset":
                    outtext = re.sub(r"opt-(.+?) based wiki set (.+?) with",
                                     r"04opt-\1 based wiki set \2 with", outtext)
                    outtext = re.sub(r"wikis: (.+)", r"wikis: 04\1", outtext)
                    noco = len(re.findall(":", outtext))
                    if noco >= 2:
                        niz = outtext.split(":")[2:]
                        comment = ":".join(niz)
                        outtext = outtext.replace(":" + comment, "")
                elif action == "setchange":
                    outtext = re.sub(r"wikis in \"(.+?)\":",
                                     r"wikis in \1:", outtext)
                    outtext = re.sub(r"added: (.+?);",
                                     r"added: 04\1;", outtext)
                    outtext = re.sub(r"removed: (.+)",
                                     r"removed: 04\1", outtext)
                    noco = len(re.findall(":", outtext))
                    if noco >= 4:
                        niz = outtext.split(":")[4:]
                        comment = ":".join(niz)
                        outtext = outtext.replace(":" + comment, "")
                elif action == "setrename":
                    outtext = re.sub(r"set \"(.+?)\" to \"(.+?)\"",
                                     r"set \1 to \2", outtext)
                    noco = len(re.findall(":", outtext))
                    if noco >= 1:
                        niz = outtext.split(":")[1:]
                        comment = ":".join(niz)
                        outtext = outtext.replace(":" + comment, "")
                elif action == "setnewtype":
                    outtext = re.sub(r"type of \"(.+?)\"",
                                     r"type of \1", outtext)
                    outtext = re.sub(r"opt-(.+?) based to opt-(.+?) based",
                                     r"04opt-\1 based to 04opt-\2 based", outtext)
                    noco = len(re.findall(":", outtext))
                    if noco >= 1:
                        niz = outtext.split(":")[1:]
                        comment = ":".join(niz)
                        outtext = outtext.replace(":" + comment, "")
                else:
                    print "!!! Unrecognized action!"
                if comment:
                    comment = " with the following comment: 07" + \
                        comment.strip(" ") + ""
                bot1.msg("03%s %s%s" % (usersource, outtext, comment))
            else:
                # 14[[07Steward requests/Permissions14]]4 10 02http://meta.wikimedia.org/w/index.php?title=Steward_requests/Permissions&diff=1146717&oldid=1146712&rcid=1190374 5* 03Black Kite 5* (+105) 10/* Black Kite@enwiki */ reply
                comp = re.compile(
                    "14\[\[07(?P<page>.+?)14\]\](.+?)diff=(?P<diff>[0-9]+)&oldid=(.+?) 5\* 03(?P<user>.+?) 5\* \((.+?)\) 10(?P<comment>.*)", re.DOTALL)
                found = comp.search(a)
                if not found:
                    print "*** Not the edit type I need ***"
                    return
                rcpage = found.group('page').strip(" ")
                watched = False
                for pg in self.stalked:
                    if pg in rcpage:
                        watched = True
                        break
                if not watched:
                    print "*** %s: Not a page I'm watching ***" % rcpage
                    return
                rcuser = found.group('user').strip(" ")
                if rcuser in self.ignored:
                    print "*** %s: Not a user I need ***" % rcuser
                    return
                print timestamp + who + a
                rccomment = found.group('comment')
                rcdiff = found.group('diff')
                if not rccomment:
                    comment = section = ""
                else:
                    comp = re.compile("/\* *(?P<section>.+?) *\*/", re.DOTALL)
                    found = comp.search(rccomment)
                    if found:
                        section = "#" + found.group('section')
                    else:
                        section = ""
                    rccomment = re.sub("/\*(.+?)\*/", "", rccomment.strip(" "))
                    if rccomment.replace(" ", "") == "":
                        comment = ""
                    else:
                        comment = " with the following comment: 07" + \
                            rccomment.strip(" ") + ""
                bot1.msg("03%s edited 10[[%s%s]] 02https://meta.wikimedia.org/wiki/?diff=prev&oldid=%s%s" % (
                    rcuser, rcpage, section, rcdiff, comment))

    def randmess(self):
        if bot1.randmess:
            a = int(random.random() * 5000)
            b = int(random.random() * 5000)
            message = "Steward elections are on! Please vote @ https://meta.wikimedia.org/wiki/Stewards/elections_2011 and comment @ https://meta.wikimedia.org/wiki/Stewards/confirm. Live updates: #wikimedia-stewards-elections"
            if a == b:
                bot1.msg(message)


class BotThread(threading.Thread):

    def __init__(self, bot):
        self.b = bot
        threading.Thread.__init__(self)

    def run(self):
        self.startbot(self.b)

    def startbot(self, bot):
        bot.start()


def main():
    global bot1, bot2
    bot1 = FreenodeBot()
    BotThread(bot1).start()
    bot2 = WikimediaBot()
    BotThread(bot2).start()  # can raise ServerNotConnectedError

if __name__ == "__main__":
    global bot1, bot2
    try:
        main()
    except IOError:
        print "No config file! You should start this script from its directory like 'python stewardbot.py'"
    except:
        raise
        bot1.die()
        bot2.die()
        sys.exit()
