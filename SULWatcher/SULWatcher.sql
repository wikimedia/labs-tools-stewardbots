DROP TABLE IF EXISTS setup;
CREATE TABLE setup (
    s_id int unsigned NOT NULL PRIMARY KEY AUTO_INCREMENT,
    s_param varchar(255) binary NOT NULL,
    s_value varchar(255) binary NOT NULL
);

CREATE INDEX param_value ON setup (s_param, s_value);

DROP TABLE IF EXISTS regex;
CREATE TABLE regex (
    r_id int unsigned NOT NULL PRIMARY KEY AUTO_INCREMENT,
    r_regex varchar(255) binary NOT NULL,
    r_active tinyint unsigned NOT NULL default 1,
    r_case tinyint unsigned NOT NULL default 0,
    r_cloak varchar(255) binary NOT NULL,
    r_reason varchar(255) binary NOT NULL default '',
    r_timestamp binary(14) NOT NULL default '19700101000000'
);

CREATE UNIQUE INDEX r_regex ON regex (r_regex, r_case);
CREATE INDEX regex ON regex (r_regex, r_case, r_timestamp);
CREATE INDEX cloak ON regex (r_cloak, r_timestamp);

DROP TABLE IF EXISTS logging;
CREATE TABLE logging (
    l_id int unsigned NOT NULL PRIMARY KEY AUTO_INCREMENT,
    l_regex varchar(255) binary NOT NULL,
    l_user varchar(255) binary NOT NULL,
    l_project varchar(255) binary NOT NULL,
    l_timestamp binary(14) NOT NULL default '19700101000000'
);

CREATE INDEX regex ON logging (l_regex, l_user, l_project, l_timestamp);
CREATE INDEX project ON logging (l_project, l_timestamp);
CREATE INDEX times ON logging (l_timestamp);
