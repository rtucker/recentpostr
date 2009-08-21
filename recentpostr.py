#!/usr/bin/python

# Spits out a Javascript embeddable list o' recent RSS stuff.

# Ryan Tucker, August 21 2009, <rtucker@gmail.com>

bloglist = [
    ("Red Wine's Journal", "http://veryfineredwine.livejournal.com/data/rss"),
    ("Mark Walling", "http://markwalling.org/feed/posts/"),
    ("No Jesus, No Peas", "http://nojesusnopeas.blogspot.com/feeds/posts/default"),
           ]

checkevery = 30*60    # check every ~30 minutes

import feedparser
import operator
import sqlite3
import sys
import time

feedparser.USER_AGENT = 'recentpostr/0.1 +http://blog.hoopycat.com/'

def initDB(filename='/tmp/recentpostr.sqlite3'):
    """Connect to and initialize the cache database.

    Optional: Filename of database
    Returns: db object
    """

    db = sqlite3.connect(filename)
    c = db.cursor()
    c.execute('pragma table_info(blogcache)')
    columns = ' '.join(i[1] for i in c.fetchall()).split()
    if columns == []:
        # need to create table
        c.execute("""create table blogcache
            (url text, lasttitle text, lastlink text, lasttime integer,
             lastcheck integer, etag text, lastmodified integer)""")
        db.commit()

    return db

def updateFeed(feedurl, etag=None, lastmodified=None):
    if type(lastmodified) is int:
        lastmod = time.gmtime(lastmodified)
    elif type(lastmodified) in [tuple, time.struct_time]:
        lastmod = lastmodified
    else:
        lastmod = None

    sys.stdout.write('<!-- Checking %s ... -->\n' % feedurl)
    d = feedparser.parse(feedurl, etag=etag, modified=lastmod)

    if d.status is 304:
        # It hasn't been updated.
        return None
    elif len(d.entries) == 0:
        # There's nothing there...?!
        return None
    else:
        # There's something here!
        return d

def fetchMostRecent(d):
    if 'updated_parsed' in d['entries'][0]:
        mostrecent = sorted(d['entries'],
                        key=operator.itemgetter('updated_parsed'),
                        reverse=True)[0]
    else:
        mostrecent = d['entries'][0]
        mostrecent['updated_parsed'] = None
    return (mostrecent.title, mostrecent.link, mostrecent.updated_parsed)

def updateBlogList(db, bloglist, checkevery=30*60):
    c = db.cursor()
    c.execute("select url from blogcache")
    allrows = c.fetchall()
    for i in bloglist:
        if (i[1],) not in allrows:
            c.execute("insert into blogcache values(?,'','',1,1,'',1)", (i[1],))

    lastcheckthreshold = int(time.time()-checkevery)
    c.execute("select url,etag,lasttime from blogcache where lastcheck < ?", (lastcheckthreshold, ))
    rows = c.fetchall()
    for results in rows:
        feed = updateFeed(results[0], results[1], results[2])
        lastcheck = int(time.time())
        if feed:
            if 'etag' in feed:
                etag = str(feed.etag)
            else:
                etag = ''
            if 'modified' in feed:
                lastmodified = int(time.mktime(feed.modified))
            else:
                lastmodified = 1
            if len(feed.entries) > 0:
                lasttitle, lastlink, lasttimetuple = fetchMostRecent(feed)
                if lasttimetuple:
                    lasttime = int(time.mktime(lasttimetuple))
                else:
                    lasttime = -1
                c.execute("""update blogcache set
                        lasttitle=?, lastlink=?, lasttime=?,
                        lastcheck=?, etag=?, lastmodified=?
                        where url=?""",
                    (lasttitle, lastlink, lasttime, lastcheck,
                     etag, lastmodified, results[0]))
                db.commit()
                sys.stdout.write("<!-- updated %s -->\n" % results[0])
            else:
                c.execute("""update blogcache set
                            lastcheck=? where url=?""",
                        (lastcheck, results[0]))
                db.commit()
                sys.stdout.write("<!-- empty feed: %s -->\n" % results[0])
        else:
            sys.stdout.write("<!-- skipped %s -->\n" % results[0])



def __main__():
    db = initDB()
    updateBlogList(db, bloglist)
    print 'done'

if __name__ == '__main__': __main__()

