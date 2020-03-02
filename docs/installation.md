# stewardbot

To get stewardbot running locally, you'll need to do the following:

1. Create `stewardbot` database at your local MySQL database server
2. Populate the table with `/StewardBot/provision_database.sql`
3. Copy config_sample.py to config.py
4. Fill in the details of your IRC account to the newly-created config.py file
5. Make sure you have a `~/.my.cnf` file created with your database credential. Look below for the structure.
6. You should be done!

## my.cnf structure
```
[client]
host = 127.0.0.1
user = stewardbot
password = securepassword
```