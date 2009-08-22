#!/usr/bin/python

# Spits out a Javascript embeddable list o' recent RSS stuff.

# Ryan Tucker, August 21 2009, <rtucker@gmail.com>

# TODO:
# push to github
# "more sane" file output options
# cache robots.txt result

checkevery = 30*60    # check every ~30 minutes
displaymax = 4

import feedparser
import logging
import logging.handlers
import operator
import robotparser
import sqlite3
import sys
import time
import urllib

# external config file
from myblogs import bloglist

# Set up logging to syslog
logging.getLogger('').addHandler(logging.handlers.SysLogHandler('/dev/log'))
logging.getLogger('').setLevel(logging.DEBUG)

# Set user agent for feedparser
feedparser.USER_AGENT = 'recentpostr/0.1 +http://blog.hoopycat.com/'

# Set user agent for urllib
class URLopener(urllib.FancyURLopener):
    version = feedparser.USER_AGENT

urllib._urlopener = URLopener()

cachedout = ''
cachedttl = 314
cachedgen = 0

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
            (feedurl text, blogurl text, blogtitle text, lasttitle text,
             lastlink text, lasttime integer, lastcheck integer, etag text,
             lastmodified integer)""")
        db.commit()

    return db

def checkRobotOK(url):
    rp = robotparser.RobotFileParser()
    robotsfd = urllib.urlopen(getURLBase(url) + '/robots.txt')

    try:
        if robotsfd.code != 200:
            logging.debug('robots.txt not found for %s, assuming OK' % url)
            return True
    except AttributeError:
        pass

    rp.parse(robotsfd.readlines())

    result = rp.can_fetch(feedparser.USER_AGENT, url)
    logging.debug('robots.txt for %s says %s' % (url, str(result)))
    return result

def getURLBase(url):
    host = urllib.splithost(urllib.splittype(url)[1])[0]
    method = urllib.splittype(url)[0]

    return method + '://' + host

def updateFeed(feedurl, etag=None, lastmodified=None):
    if type(lastmodified) is int:
        lastmod = time.gmtime(lastmodified)
    elif type(lastmodified) in [tuple, time.struct_time]:
        lastmod = lastmodified
    else:
        lastmod = None

    logging.debug('Checking %s ...' % feedurl)

    if not checkRobotOK(feedurl):
        return None

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
    c.execute("select feedurl from blogcache")
    allrows = c.fetchall()
    for i in bloglist:
        if (i, ) not in allrows:
            logging.debug('New blog found: %s' % i)
            c.execute("insert into blogcache values(?,'','','','',1,1,'',1)", (i,))

    lastcheckthreshold = int(time.time()-checkevery)
    c.execute("select feedurl,etag,lasttime from blogcache where lastcheck < ?", (lastcheckthreshold, ))
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
            if 'link' in feed.feed:
                blogurl = feed.feed.link
            else:
                blogurl = feedurl
            if 'title' in feed.feed:
                blogtitle = feed.feed.title
            else:
                blogtitle = ''
            lasttitle, lastlink, lasttimetuple = fetchMostRecent(feed)
            if lasttimetuple:
                lasttime = int(time.mktime(lasttimetuple))
            else:
                lasttime = -1
            c.execute("""update blogcache set blogurl=?, blogtitle=?,
                    lasttitle=?, lastlink=?, lasttime=?, lastcheck=?,
                    etag=?, lastmodified=? where feedurl=?""",
                (blogurl, blogtitle, lasttitle, lastlink, lasttime,
                lastcheck, etag, lastmodified, results[0]))
            db.commit()
            logging.debug("Updated %s" % results[0])
        else:
            c.execute("""update blogcache set
                        lastcheck=? where feedurl=?""",
                    (lastcheck, results[0]))
            db.commit()
            logging.debug("No new data on feed: %s" % results[0])

def iterCachedBlogRoll(db, bloglist):
    c = db.cursor()
    c.execute("""select feedurl,blogurl,blogtitle,lasttitle,lastlink,lasttime
                 from blogcache
                 order by lasttime desc""")
    rows = c.fetchall()
    for i in rows:
        if i[0] in bloglist:
            if bloglist[i[0]]:
                blogtitle = bloglist[i[0]]
            else:
                blogtitle = i[2]
            yield {'blogurl': i[1], 'blogtitle': blogtitle,
                   'posttitle': i[3], 'postlink': i[4], 'postts': i[5]}

def formatOutputRowJavaScript(entry):
    entry['isostamp'] = ''
    if entry['postts'] > 1:
        entry['isostamp'] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime(entry['postts']))
    return """
        document.write("<li><b><a href='%(blogurl)s'>%(blogtitle)s</a></b><br><a href='%(postlink)s'>%(posttitle)s<br><i><small>");
        document.write(jQuery.timeago("%(isostamp)s"));
        document.write("</small></i></a></li>");""" % entry

def processOutput(type='javascript'):
    db = initDB()
    updateBlogList(db, bloglist)
    element = iterCachedBlogRoll(db, bloglist)
    output = ''
    for i in range(0,displaymax):
        if type == 'javascript':
            output += str(formatOutputRowJavaScript(element.next()))
    return output

def wsgiInterface(environ, start_response):
    start_response('200 OK', [('Content-Type', 'text/javascript')])
    if not (cachedout and (cachedgen + cachedttl > time.time())):
        logging.debug('Regenerating cache (age: %i)' % (time.time() - cachedgen))
        cachedout = processOutput().split('\n')
        cachedgen = time.time()
    else:
        logging.debug('Outputting cache (age: %i)' % (time.time() - cachedgen))

    return cachedout

def __main__():
    print processOutput()

if __name__ == '__main__': __main__()

