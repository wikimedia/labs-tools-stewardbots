#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import logging
import os
import re
import threading
import time
from configparser import ConfigParser
from datetime import datetime

import config
import irc.client
import pymysql
from ib3 import Bot
from ib3.auth import SASL
from ib3.connection import SSL
from ib3.mixins import DisconnectOnError
from ib3.nick import Ghost
from irc.bot import Channel
from irc.client import NickMask
from sseclient import SSEClient as EventSource

# DB data
dbconfig = ConfigParser()
dbconfig.read_string(open(os.path.expanduser("~/.my.cnf"), "r").read())
SQLuser = dbconfig["client"]["user"]
SQLpassword = dbconfig["client"]["password"]
SQLhost = dbconfig["client"]["host"]
SQLdb = config.dbname

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


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logging.captureWarnings(True)

logger = logging.getLogger("stewardbot")
logger.setLevel(logging.DEBUG)


def nm_to_n(nm):
    """Convert nick mask from source to nick."""
    return NickMask(nm).nick


def query(sqlquery, one=True):
    db = pymysql.connect(db=SQLdb, host=SQLhost, user=SQLuser, passwd=SQLpassword)
    cursor = db.cursor()
    cursor.execute(sqlquery)
    db.close()
    res = list(cursor.fetchall())
    res.sort(key=lambda x: x if isinstance(x, str) else "")
    if one:
        return [i[0] for i in res if i]
    return res


def modquery(sqlquery):
    db = pymysql.connect(db=SQLdb, host=SQLhost, user=SQLuser, passwd=SQLpassword)
    cursor = db.cursor()
    cursor.execute(sqlquery)
    db.commit()
    db.close()


class LiberaBot(SASL, SSL, DisconnectOnError, Ghost, Bot):
    def __init__(self):
        self.channel = config.channel
        self.nickname = config.nick
        self.owner = config.owner
        self.privileged = query(queries["privcloaks"])
        self.listened = query(queries["listenedchannels"])
        self.optin = query(queries["stewardoptin"])
        self.steward = query(queries["stewardnicks"])
        self.quiet = False
        self.notify = True
        self.randmess = config.randmess
        self.listen = True
        self.badsyntax = "Unrecognized command. Type @help for more info."
        self.emergency_cooldowns = {}

        super().__init__(
            server_list=[(config.server, 6697)],
            nickname=self.nickname,
            realname=self.nickname,
            ident_password=config.password,
            channels=[self.channel] + self.listened,
        )

    def on_ctcp(self, c, event):
        if event.arguments[0] == "VERSION":
            c.ctcp_reply(
                nm_to_n(event.source),
                "Bot for informing Wikimedia stewards on " + self.channel,
            )
        elif event.arguments[0] == "PING" and len(event.arguments) > 1:
            c.ctcp_reply(nm_to_n(event.source), "PING " + event.arguments[1])

    def on_action(self, c, event):
        who = "<" + self.channel + "/" + nm_to_n(event.source) + "> "
        logger.info("* " + who + event.arguments[0])

    def on_privmsg(self, c, e):
        nick = nm_to_n(e.source)
        a = e.arguments[0]
        nocando = "This command cannot be used via query!"
        print(
            "[" + time.strftime("%d.%m.%Y %H:%M:%S") + "] <private/" + nick + "> " + a
        )
        if a[0] == "@" or a.lower().startswith(self.nickname.lower() + ":"):
            if a[0] == "@":
                command = a[1:]
            else:
                command = re.sub("(?i)%s:" % self.nickname.lower(), "", a).strip(" ")
            if command.lower() == "die":
                if self.getcloak(e.source) == self.owner:
                    self.do_command(e.source, command)
                else:
                    self.msg(nocando, nick)
            # Start of Anti-PiR hack
            # elif self.startswitharray(command.lower(), ["help", "privileged list", "ignored list", "stalked list", "listen list", "stew users", "stew nicks", "stew optin", "stew info"]):
            #    self.do_command(e, string.strip(command), nick)
            # elif command.lower().startswith("huggle"):
            #    self.msg(nocando, nick)
            # End of Anti-PiR hack
            elif self.is_privileged(e.source):
                self.do_command(e.source, command.strip(), nick)
            else:
                self.msg(self.badsyntax, nick)
        elif a.lower().startswith("!steward"):
            # self.attention(nick)
            self.msg(nocando, nick)
        elif self.getcloak(e.source).lower() == self.owner:
            if a[0] == "!":
                self.connection.action(self.channel, a[1:])
            else:
                self.msg(a)

    def on_pubmsg(self, c, event):
        if not self.has_primary_nick():
            return

        nick = event.source.nick
        a = event.arguments[0]
        where = event.target
        who = "<" + where + "/" + nick + "> "
        if where == self.channel:
            logger.info(who + a)
            if a[0] == "@" or a.lower().startswith(self.nickname.lower() + ":"):
                # Start of Anti-PiR hack
                evilchars = (";", '"')
                for evilchar in evilchars:
                    if evilchar in a:
                        self.msg(
                            "Your command contains prohibited characters. Please repeat the command without them.",
                            self.channel,
                        )
                        return
                # End of Anti-PiR hack

                if a[0] == "@":
                    command = a[1:]
                else:
                    command = re.sub("(?i)%s:" % self.nickname.lower(), "", a).strip(
                        " "
                    )
                if self.startswitharray(
                    command.lower(),
                    [
                        "steward",
                        "huggle",
                        "help",
                        "privileged list",
                        "ignored list",
                        "stalked list",
                        "listen list",
                        "stew users",
                        "stew nicks",
                        "stew optin",
                        "stew info",
                    ],
                ):
                    self.do_command(event.source, command.strip())
                elif self.is_privileged(event.source):
                    self.do_command(event.source, command.strip())
                else:
                    # if not self.quiet: self.msg("You're not allowed to issue commands.")
                    pass
        if a.lower().startswith("!steward"):
            if where != self.channel:
                logger.info(who + a)
            reason = re.sub("(?i)!steward", "", a).strip(" ")
            self.attention(nick, self.getcloak(event.source), where, reason)

    def do_command(self, e, cmd, target=None):
        nick = nm_to_n(e)
        if not target:
            target = self.channel

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
                self.msg("You have 20 seconds!", target)
                self.quiet = True
                time.sleep(20)
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
            self.msg(
                "Stewards: Attention requested by %s ( %s )"
                % (nick, " ".join(self.optin))
            )

        # Privileged
        elif cmd.lower().startswith("privileged"):
            self.do_privileged(
                re.sub("(?i)^privileged", "", cmd).strip(" "), target, nick
            )

        # Ignored
        elif cmd.lower().startswith("ignored"):
            self.do_ignored(re.sub("(?i)^ignored", "", cmd).strip(" "), target, nick)

        # Stalked
        elif cmd.lower().startswith("stalked"):
            self.do_stalked(re.sub("(?i)^stalked", "", cmd).strip(" "), target, nick)

        # Listen
        elif cmd.lower().startswith("listen"):
            self.do_listen(re.sub("(?i)^listen", "", cmd).strip(" "), target, nick)

        # Stewards
        elif cmd.lower().startswith("stew"):
            self.do_steward(re.sub("(?i)^stew", "", cmd).strip(" "), target, nick)

        # Help
        elif cmd.lower() == "help":
            self.msg(
                "Help = https://stewardbots-legacy.toolforge.org/StewardBot/StewardBot.html",
                nick,
            )

        # Test
        elif cmd.lower() == "test":
            self.msg("The bot seems to see your message")

        # Huggle
        elif cmd.lower().startswith("huggle"):
            who = cmd[6:].strip(" ")
            self.connection.action(self.channel, "huggles " + who)

        # Kubernetes will restart the process if it exists
        elif cmd.lower() == "restart":
            self.msg("See you soon!")
            logger.info("Restarting based on request by %s", e)

            # cause recent changes listener to stop on next event
            bot2.should_exit = True

            self.connection.part(self.channels)
            self.disconnect()

        # Other
        elif not self.quiet:
            pass  # self.msg(self.badsyntax, target)

    def attention(self, nick, cloak, channel=None, reason=None):
        cooldown_remove_threshold = time.time() - 90

        # wrap keys in list() to avoid crashes from cleanup causing the list to be resized during iteration
        for key in list(self.emergency_cooldowns.keys()):
            value = self.emergency_cooldowns[key]

            # if the cooldown has expired, just remove it
            if value < cooldown_remove_threshold:
                del self.emergency_cooldowns[key]
                continue

            # not expired, check if this entry is for the current user and then apply cooldown.
            if key == cloak:
                logger.info(
                    "%s@%s attempted to use !steward on cooldown (last use %i seconds ago)",
                    nick,
                    cloak,
                    (time.time() - value),
                )
                self.msg(
                    "%s: Sorry, you are on a cooldown for having emergencies." % nick,
                    channel,
                )
                return

        if self.notify:
            if not channel or channel == self.channel:
                self.msg(
                    "Stewards: Attention requested by %s ( %s )"
                    % (nick, " ".join(self.steward))
                )
            else:
                self.msg(
                    "Stewards: Attention requested ( %s )" % (" ".join(self.steward))
                )
                messg = "Attention requested by %s on %s" % (nick, channel)
                if reason:
                    messg += " with the following reason: " + reason
                self.msg(messg)
            self.emergency_cooldowns[cloak] = time.time()

    def do_privileged(self, cmd, target, nick):
        if cmd.lower().startswith("list"):
            who = re.sub("(?i)^list", "", cmd).strip(" ")
            who = who.split(" ")[0]
            if who in ["all", "*"]:
                privnicks = query(
                    "(select p_nick from privileged) union (select s_nick from stewards)"
                )
                self.msg(
                    "privileged nicks (including stewards): " + ", ".join(privnicks),
                    nick,
                )
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
                    'select p_cloak from privileged where p_nick="%s"' % who
                )
                if len(privcloak) == 0:
                    self.msg("%s is not in the list of privileged users!" % who, target)
                else:
                    self.msg(
                        "The cloak of privileged user %s is %s" % (who, privcloak[0]),
                        target,
                    )
        elif cmd.lower().startswith("add"):
            who = re.sub("(?i)^add", "", cmd).strip(" ")
            wholist = who.split(" ")
            if len(wholist) < 2:
                if not self.quiet:
                    self.msg("You have to specify a nick and a cloak", target)
            else:
                pnick = wholist[0]
                pcloak = wholist[1].lower()
                if (
                    len(
                        query('select p_nick from privileged where p_nick="%s"' % pnick)
                    )
                    > 0
                ):
                    if not self.quiet:
                        self.msg("%s is already privileged!" % pnick, target)
                else:
                    modquery(
                        'insert into privileged values (0, "%s", "%s")'
                        % (pnick, pcloak)
                    )
                    # update the list of privileged cloaks
                    self.privileged = query(queries["privcloaks"])
                    if not self.quiet:
                        self.msg(
                            "%s added to the list of privileged users!" % pnick, target
                        )
        elif self.startswitharray(cmd.lower(), ["remove", "delete"]):
            who = re.sub("(?i)^(remove|delete)", "", cmd).strip(" ")
            who = who.split(" ")[0]
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a nick", target)
            else:
                if (
                    len(query('select p_nick from privileged where p_nick="%s"' % who))
                    == 0
                ):
                    if not self.quiet:
                        self.msg(
                            "%s is not in the list of privileged users!" % who, target
                        )
                else:
                    modquery('delete from privileged where p_nick="%s"' % who)
                    # update the list of privileged cloaks
                    self.privileged = query(queries["privcloaks"])
                    if not self.quiet:
                        self.msg(
                            "%s removed from the list of privileged users!" % who,
                            target,
                        )
        elif self.startswitharray(cmd.lower(), ["change", "edit", "modify", "rename"]):
            who = re.sub("(?i)^(change|edit|modify|rename)", "", cmd).strip(" ")
            wholist = who.split(" ")
            if len(wholist) < 2:
                if not self.quiet:
                    self.msg(
                        "You have to specify a nick and a cloak or another nick", target
                    )
            else:
                pnick = wholist[0]
                pcloak = wholist[1]
                renamecloak = False
                if "/" in pcloak:
                    pcloak = pcloak.lower()
                    renamecloak = True
                if (
                    len(
                        query('select p_nick from privileged where p_nick="%s"' % pnick)
                    )
                    == 0
                ):
                    if not self.quiet:
                        self.msg(
                            "%s is not in the list of privileged users!" % pnick, target
                        )
                else:
                    if renamecloak:
                        modquery(
                            'update privileged set p_cloak = "%s" where p_nick = "%s"'
                            % (pcloak, pnick)
                        )
                        # update the list of privileged cloaks
                        self.privileged = query(queries["privcloaks"])
                        if not self.quiet:
                            self.msg(
                                "Changed the cloak for %s in the list of privileged users!"
                                % pnick,
                                target,
                            )
                    else:
                        modquery(
                            'update privileged set p_nick = "%s" where p_nick = "%s"'
                            % (pcloak, pnick)
                        )
                        if not self.quiet:
                            self.msg(
                                "Changed the privileged user from %s to %s!"
                                % (pnick, pcloak),
                                target,
                            )
        else:
            if not self.quiet:
                self.msg(self.badsyntax, target)

    def do_ignored(self, cmd, target, nick):
        if cmd.lower().startswith("list"):
            who = re.sub("(?i)^list", "", cmd).strip(" ")
            who = who.split(" ")[0]
            if who in ["all", "*"]:
                ignoredusers = query(queries["ignoredusers"])
                self.msg(
                    "ignored users (including stewards): " + ", ".join(ignoredusers),
                    nick,
                )
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
                if (
                    len(
                        query(
                            'select i_username from ignored where i_username="%s"' % who
                        )
                    )
                    > 0
                ):
                    if not self.quiet:
                        self.msg("%s is already ignored!" % who, target)
                else:
                    modquery('insert into ignored values (0, "%s")' % who)
                    # update the list of ignored users
                    bot2.ignored = query(queries["ignoredusers"])
                    if not self.quiet:
                        self.msg("%s added to the list of ignored users!" % who, target)
        elif self.startswitharray(cmd.lower(), ["remove", "delete"]):
            who = re.sub("(?i)^(remove|delete)", "", cmd).strip(" ")
            who = who.split(" ")[0]
            who = who.replace("_", " ")
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a username", target)
            else:
                who = who[0].upper() + who[1:]
                if (
                    len(
                        query(
                            'select i_username from ignored where i_username="%s"' % who
                        )
                    )
                    == 0
                ):
                    if not self.quiet:
                        self.msg(
                            "%s is not in the list of ignored users!" % who, target
                        )
                else:
                    modquery('delete from ignored where i_username="%s"' % who)
                    # update the list of ignored users
                    bot2.ignored = query(queries["ignoredusers"])
                    if not self.quiet:
                        self.msg(
                            "%s removed from the list of ignored users!" % who, target
                        )
        elif self.startswitharray(cmd.lower(), ["change", "edit", "modify", "rename"]):
            who = re.sub("(?i)^(change|edit|modify|rename)", "", cmd).strip(" ")
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
                if (
                    len(
                        query(
                            'select i_username from ignored where i_username="%s"'
                            % iuser1
                        )
                    )
                    == 0
                ):
                    if not self.quiet:
                        self.msg(
                            "%s is not in the list of ignored users!" % iuser1, target
                        )
                else:
                    modquery(
                        'update ignored set i_username = "%s" where i_username = "%s"'
                        % (iuser2, iuser1)
                    )
                    # update the list of ignored users
                    bot2.ignored = query(queries["ignoredusers"])
                    if not self.quiet:
                        self.msg(
                            "Changed the username of %s in the list of ignored users!"
                            % iuser1,
                            target,
                        )
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
                if (
                    len(query('select f_page from followed where f_page="%s"' % who))
                    > 0
                ):
                    if not self.quiet:
                        self.msg("%s is already stalked!" % who, target)
                else:
                    modquery('insert into followed values (0, "%s")' % who)
                    # update the list of stalked pages
                    bot2.stalked = query(queries["stalkedpages"])
                    if not self.quiet:
                        self.msg("%s added to the list of stalked pages!" % who, target)
        elif self.startswitharray(cmd.lower(), ["remove", "delete"]):
            who = re.sub("(?i)^(remove|delete)", "", cmd).strip(" ")
            who = who.split(" ")[0]
            who = who.replace("_", " ")
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a page name", target)
            else:
                who = who[0].upper() + who[1:]
                if (
                    len(query('select f_page from followed where f_page="%s"' % who))
                    == 0
                ):
                    if not self.quiet:
                        self.msg(
                            "%s is not in the list of stalked pages!" % who, target
                        )
                else:
                    modquery('delete from followed where f_page="%s"' % who)
                    # update the list of stalked pages
                    bot2.stalked = query(queries["stalkedpages"])
                    if not self.quiet:
                        self.msg(
                            "%s removed from the list of stalked pages!" % who, target
                        )
        elif self.startswitharray(cmd.lower(), ["change", "edit", "modify", "rename"]):
            who = re.sub("(?i)^(change|edit|modify|rename)", "", cmd).strip(" ")
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
                if (
                    len(query('select f_page from followed where f_page="%s"' % ipage1))
                    == 0
                ):
                    if not self.quiet:
                        self.msg(
                            "%s is not in the list of stalked pages!" % ipage1, target
                        )
                else:
                    modquery(
                        'update followed set f_page = "%s" where f_page = "%s"'
                        % (ipage2, ipage1)
                    )
                    # update the list of stalked pages
                    bot2.stalked = query(queries["stalkedpages"])
                    if not self.quiet:
                        self.msg(
                            "Changed the username of %s in the list of stalked pages!"
                            % ipage1,
                            target,
                        )
        else:
            if not self.quiet:
                self.msg(self.badsyntax, target)

    def do_listen(self, cmd, target, nick):
        if cmd.lower().startswith("list"):
            listenedchannels = query(queries["listenedchannels"])
            self.msg("'listen' channels: " + ", ".join(listenedchannels), target)
        elif cmd.lower().startswith("add"):
            who = re.sub("(?i)^add", "", cmd).strip(" ")
            who = who.split(" ")[0]
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a channel", target)
            else:
                if not who.startswith("#"):
                    who = "#" + who
                if (
                    len(
                        query('select l_channel from listen where l_channel="%s"' % who)
                    )
                    > 0
                ):
                    if not self.quiet:
                        self.msg(
                            "%s is already in the list of 'listen' channels!" % who,
                            target,
                        )
                else:
                    modquery('insert into listen values (0, "%s")' % who)
                    # update the list of listened channels
                    self.listened = query(queries["listenedchannels"])
                    if not self.quiet:
                        self.msg(
                            "%s added to the list of 'listen' channels!" % who, target
                        )
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
                if (
                    len(
                        query('select l_channel from listen where l_channel="%s"' % who)
                    )
                    == 0
                ):
                    if not self.quiet:
                        self.msg(
                            "%s is not in the list of 'listen' channels!" % who, target
                        )
                else:
                    modquery('delete from listen where l_channel="%s"' % who)
                    # update the list of listened channels
                    self.listened = query(queries["listenedchannels"])
                    if not self.quiet:
                        self.msg(
                            "%s removed from the list of 'listen' channels!" % who,
                            target,
                        )
                    self.connection.part(
                        who, "Requested by " + nick + " in " + self.channel
                    )
        elif self.startswitharray(cmd.lower(), ["change", "edit", "modify", "rename"]):
            who = re.sub("(?i)^(change|edit|modify|rename)", "", cmd).strip(" ")
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
                if (
                    len(
                        query(
                            'select l_channel from listen where l_channel="%s"' % chan1
                        )
                    )
                    == 0
                ):
                    if not self.quiet:
                        self.msg(
                            "%s is not in the list of stalked pages!" % chan1, target
                        )
                else:
                    modquery(
                        'update listen set l_channel = "%s" where l_channel = "%s"'
                        % (chan2, chan1)
                    )
                    # update the list of listened channels
                    bot2.stalked = query(queries["listenedchannels"])
                    if not self.quiet:
                        self.msg(
                            "Changed the name of %s in the list of 'listen' channels!"
                            % chan1,
                            target,
                        )
                    self.connection.part(
                        chan1, "Requested by " + nick + " in " + self.channel
                    )
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
                    'select s_nick, s_cloak, s_optin from stewards where s_username="%s"'
                    % who,
                    False,
                )
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
                        stewout += ". %s is%s in the list of opt-in nicks." % (
                            stewinfo[0][0],
                            soptin,
                        )
                    self.msg(stewout, target)
        elif cmd.lower().startswith("add"):
            who = re.sub("(?i)^add", "", cmd).strip(" ")
            who = re.sub(" +", " ", who)
            wholist = who.split(" ")
            wllen = len(wholist)
            if wllen == 0:
                if not self.quiet:
                    self.msg(
                        "You have to specify username, and optionally nick, cloak and opt-in preference",
                        target,
                    )
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
                if (
                    len(
                        query(
                            'select s_username from stewards where s_username="%s"'
                            % suser
                        )
                    )
                    > 0
                ):
                    if not self.quiet:
                        self.msg(
                            "%s is already in the list of stewards!" % suser, target
                        )
                else:
                    modquery(
                        'insert into stewards values (0, "%s", %s, %s, %s)'
                        % (suser, snick, scloak, soptin)
                    )
                    # update the list of steward nicks
                    self.steward = query(queries["stewardnicks"])
                    # update the list of steward opt-in nicks
                    self.optin = query(queries["stewardoptin"])
                    # update the list of privileged cloaks
                    self.privileged = query(queries["privcloaks"])
                    # update the list of ignored users
                    bot2.ignored = query(queries["ignoredusers"])
                    if not self.quiet:
                        self.msg("%s added to the list of stewards!" % suser, target)
        elif self.startswitharray(cmd.lower(), ["remove", "delete"]):
            who = re.sub("(?i)^(remove|delete)", "", cmd).strip(" ")
            who = who.split(" ")[0]
            who = who.replace("_", " ")
            if not who:
                if not self.quiet:
                    self.msg("You have to specify a username", target)
            else:
                who = who[0].upper() + who[1:]
                if (
                    len(
                        query(
                            'select s_username from stewards where s_username="%s"'
                            % who
                        )
                    )
                    == 0
                ):
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
                        self.msg("%s removed from the list of stewards!" % who, target)
        elif self.startswitharray(cmd.lower(), ["change", "edit", "modify", "rename"]):
            who = re.sub("(?i)^(change|edit|modify|rename)", "", cmd).strip(" ")
            wholist = who.split(" ")
            wllen = len(wholist)
            if wllen < 2:
                if not self.quiet:
                    self.msg(
                        "You have to specify two usernames, and optionally nick, cloak and opt-in preference",
                        target,
                    )
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
                                setlist += ["s_optin = 1"]
                            elif wholist[4].lower() in ["no", "false", "0"]:
                                setlist += ["s_optin = 0"]
                if (
                    len(
                        query(
                            'select s_username from stewards where s_username="%s"'
                            % suser1
                        )
                    )
                    == 0
                ):
                    if not self.quiet:
                        self.msg("%s is not a steward!" % suser1, target)
                else:
                    if len(setlist) == 0:
                        if not self.quiet:
                            self.msg("No change necessary!")
                    else:
                        modquery(
                            'update stewards set %s where s_username = "%s"'
                            % (", ".join(setlist), suser1)
                        )
                        # update the list of steward nicks
                        self.steward = query(queries["stewardnicks"])
                        # update the list of steward opt-in nicks
                        self.optin = query(queries["stewardoptin"])
                        # update the list of privileged cloaks
                        self.privileged = query(queries["privcloaks"])
                        # update the list of ignored users
                        bot2.ignored = query(queries["ignoredusers"])
                        if not self.quiet:
                            self.msg(
                                "Updated information for steward %s!" % suser1, target
                            )
        else:
            if not self.quiet:
                self.msg(self.badsyntax, target)

    def msg(self, message, target=None):
        if not target:
            target = self.channel
        try:
            self.connection.privmsg(target, message)
            logger.info("<%s/[self]> %s", target, message)
        except irc.client.MessageTooLong:
            logger.warning("Attempted to send a message that is too long: %s", message)
            self.connection.privmsg(
                target,
                "The message is too long. Please fill a task in Phabricator under #stewardbots describing what you tried to do.",
            )

    def getcloak(self, doer):
        if re.search("/", doer) and re.search("@", doer):
            return doer.split("@")[1]

    def startswitharray(self, text, array):
        for entry in array:
            if text.startswith(entry):
                return True
        return False

    def is_privileged(self, source: str) -> bool:
        nickmask = NickMask(source)
        channel: Channel = self.channels.get(self.channel)

        if channel.is_oper(nickmask.nick) or channel.is_voiced(nickmask.nick):
            return True

        cloak = self.getcloak(source)
        if cloak:
            return cloak.lower() in self.privileged

        return False


class RecentChangesBot:
    def __init__(self):
        self.stalked = query(queries["stalkedpages"])
        self.ignored = query(queries["ignoredusers"])
        self.should_exit = False
        self.RE_SECTION = re.compile(r"/\* *(?P<section>.+?) *\*/", re.DOTALL)

    def start(self):
        stream = "https://stream.wikimedia.org/v2/stream/recentchange"
        while not self.should_exit:
            try:
                logger.info("Starting EventStream listener")
                for event in EventSource(stream):
                    if self.should_exit:
                        logger.info("Exiting EventStream listener")
                        break

                    if bot1.quiet:
                        continue

                    if event.event != "message":
                        continue

                    try:
                        change = json.loads(event.data)
                    except ValueError:
                        continue

                    if change["wiki"] != "metawiki":
                        continue

                    if change["bot"]:
                        if change["type"] == "log":
                            if change["log_type"] != "rights":
                                continue
                            if (
                                "bot" not in change["log_params"]["newgroups"]
                                and "flood" not in change["log_params"]["newgroups"]
                            ):
                                continue
                        else:
                            continue

                    if change["type"] == "edit":
                        if change["title"] not in self.stalked:
                            continue
                        if change["user"] in self.ignored:
                            continue

                        rccomment = change["comment"].strip()
                        m = self.RE_SECTION.search(rccomment)
                        if m:
                            section = "#" + m.group("section")
                        else:
                            section = ""
                        comment = (
                            " with the following comment: 07"
                            + rccomment.strip(" ")
                            + ""
                        )
                        bot1.msg(
                            "03%s edited 10[[%s%s]] 02https://meta.wikimedia.org/wiki/Special:Diff/%s%s"
                            % (
                                change["user"],
                                change["title"],
                                section,
                                change["revision"]["new"],
                                comment,
                            )
                        )
                    elif change["type"] == "log":
                        if change["log_type"] == "rights":
                            performer = change["user"]
                            target = change["title"].replace("User:", "")
                            selff = ""
                            bott = ""
                            if performer == re.sub(r"@.*", "", target):
                                selff = "06(self) "
                            if (
                                "bot" in change["log_params"]["newgroups"]
                                or "bot" in change["log_params"]["oldgroups"]
                            ):
                                bott = "06(bot) "

                            # construct from_rights
                            from_rights = []
                            for i in range(len(change["log_params"]["oldgroups"])):
                                group = change["log_params"]["oldgroups"][i]
                                if change["log_params"]["oldmetadata"][i] == []:
                                    from_rights.append(group)
                                else:
                                    expiry = datetime.strptime(
                                        change["log_params"]["oldmetadata"][i][
                                            "expiry"
                                        ],
                                        "%Y%m%d%H%M%S",
                                    )
                                    from_rights.append(
                                        "%s (expiry: %s)"
                                        % (
                                            group,
                                            expiry.strftime("%H:%M, %d %B %Y"),
                                        )
                                    )

                            # construct to_rights
                            to_rights = []
                            for i in range(len(change["log_params"]["newgroups"])):
                                group = change["log_params"]["newgroups"][i]
                                metadata = change["log_params"]["newmetadata"][i]
                                if metadata == []:
                                    to_rights.append(group)
                                else:
                                    expiry = datetime.strptime(
                                        metadata["expiry"], "%Y%m%d%H%M%S"
                                    )
                                    to_rights.append(
                                        "%s (expiry: %s)"
                                        % (
                                            group,
                                            expiry.strftime("%H:%M, %d %B %Y"),
                                        )
                                    )

                            from_rights_text = "(none)"
                            if len(from_rights) > 0:
                                from_rights_text = ", ".join(from_rights)

                            to_rights_text = "(none)"
                            if len(to_rights) > 0:
                                to_rights_text = ", ".join(to_rights)
                            bot1.msg(
                                "%s%s03%s changed user rights for %s from 04%s to 04%s: 07%s"
                                % (
                                    selff,
                                    bott,
                                    performer,
                                    target,
                                    from_rights_text,
                                    to_rights_text,
                                    change["comment"],
                                )
                            )
                        elif change["log_type"] == "gblblock":
                            target = change["title"].replace("User:", "")
                            performer = change["user"]
                            expiry = ""
                            comment = (
                                " with the following comment: 7"
                                + change["comment"].strip(" ")
                                + ""
                            )
                            if change["log_action"] == "gblock2":
                                expiry = change["log_params"][0]
                                action_description = "globally blocked"
                            elif change["log_action"] == "gunblock":
                                action_description = "removed global block on"
                            else:
                                expiry = change["log_params"][0]
                                action_description = "modified the global block on"
                            bot1.msg(
                                "03%s %s %s (%s) %s"
                                % (
                                    performer,
                                    action_description,
                                    target,
                                    expiry,
                                    comment,
                                )
                            )
                        elif change["log_type"] == "globalauth":
                            target = (
                                change["title"]
                                .replace("User:", "")
                                .replace("@global", "")
                                .strip()
                            )
                            comment = change["comment"]
                            if comment != "":
                                comment = (
                                    "with the following comment: 07"
                                    + comment.strip(" ")
                                    + ""
                                )

                            action_description = ""
                            if len(change["log_params"]["added"]) > 0:
                                action_description += ", ".join(
                                    change["log_params"]["added"]
                                )
                            if len(change["log_params"]["removed"]) > 0:
                                if len(action_description) > 0:
                                    action_description += ", "
                                action_description += ", ".join(
                                    [
                                        f"un{action}"
                                        for action in change["log_params"]["removed"]
                                    ]
                                )

                            action_description += " account"

                            bot1.msg(
                                "03%s %s %s %s"
                                % (
                                    change["user"],
                                    action_description,
                                    target,
                                    comment,
                                )
                            )
                        elif change["log_type"] == "gblrights":
                            if change["log_action"] == "usergroups":
                                target = change["title"].replace("User:", "")

                                oldGroups = change["log_params"]["oldGroups"]
                                if len(oldGroups) == 0:
                                    oldGroups = "(none)"
                                else:
                                    oldGroups = ", ".join(oldGroups)
                                newGroups = change["log_params"]["newGroups"]
                                if len(newGroups) == 0:
                                    newGroups = "(none)"
                                else:
                                    newGroups = ", ".join(newGroups)

                                bot1.msg(
                                    "03%s changed global group membership for %s from 04%s to 04%s: 07%s"
                                    % (
                                        change["user"],
                                        target,
                                        oldGroups,
                                        newGroups,
                                        change["comment"],
                                    )
                                )
                            elif change["log_action"] == "groupprms2":
                                addedRights = change["log_params"]["addRights"]
                                removedRights = change["log_params"]["removeRights"]

                                bot1.msg(
                                    "03%s changed global group permissions for %s, added 04%s, removed 04%s: 07%s"
                                    % (
                                        change["user"],
                                        change["title"].replace(
                                            "Special:GlobalUsers/", ""
                                        ),
                                        addedRights,
                                        removedRights,
                                        change["comment"],
                                    )
                                )
                            elif change["log_action"] == "groupprms3":
                                oldSet = change["log_params"]["old"]
                                newSet = change["log_params"]["new"]
                                bot1.msg(
                                    "03%s changed group restricted wikis set for %s from 04%s to 04%s: 07%s"
                                    % (
                                        change["user"],
                                        change["title"].replace(
                                            "Special:GlobalUsers/", ""
                                        ),
                                        oldSet,
                                        newSet,
                                        change["comment"],
                                    )
                                )
                            elif change["log_action"] == "newset":
                                wikis = ", ".join(change["log_params"]["wikis"])
                                bot1.msg(
                                    "03%s created 12%s wiki set %s containing 04%s: 07%s"
                                    % (
                                        change["user"],
                                        change["log_params"][1],
                                        change["log_params"][0],
                                        wikis,
                                        change["comment"],
                                    )
                                )
                            elif change["log_action"] == "deleteset":
                                bot1.msg(
                                    "03%s deleted wiki set %s: 07%s"
                                    % (
                                        change["user"],
                                        change["log_params"][0],
                                        change["comment"],
                                    )
                                )
                            elif change["log_action"] == "setchange":
                                message = "03%s changed wikis in %s" % (
                                    change["user"],
                                    change["log_params"][0],
                                )
                                added_wikis = change["log_params"]["added"]
                                removed_wikis = change["log_params"]["removed"]
                                if added_wikis != "":
                                    message += ", added 04%s" % added_wikis
                                if removed_wikis != "":
                                    message += ", removed 04%s" % removed_wikis
                                bot1.msg(message + ": 07%s" % change["comment"])
                            elif change["log_action"] == "setrename":
                                bot1.msg(
                                    "03%s renamed wiki set %s to 04%s: 07%s"
                                    % (
                                        change["user"],
                                        change["log_params"][1],
                                        change["log_params"][0],
                                        change["comment"],
                                    )
                                )
                            elif change["log_action"] == "setnewtype":
                                bot1.msg(
                                    "03%s changed type of %s from 04%s to 04%s: 07%s"
                                    % (
                                        change["user"],
                                        change["log_params"][0],
                                        change["log_params"][1],
                                        change["log_params"][2],
                                        change["comment"],
                                    )
                                )
            except StopIteration:
                pass
            except Exception:
                logger.exception("Recent changes listener encountered an error")


class BotThread(threading.Thread):
    def __init__(self, bot):
        threading.Thread.__init__(self)
        self.b = bot

    def run(self):
        self.b.start()


if __name__ == "__main__":
    global bot1, bot2
    bot1 = LiberaBot()
    bot2 = RecentChangesBot()

    try:
        liberaThread = BotThread(bot1)
        rcThread = BotThread(bot2)

        liberaThread.start()
        rcThread.start()
    except KeyboardInterrupt:
        bot1.disconnect("Killed by a KeyboardInterrupt")
    except Exception:
        logger.exception("Killed by an unhandled exception")
        bot1.disconnect("StewardBot encountered an unhandled exception")
    finally:
        # no matter how something failed, just get out of here
        raise SystemExit()
