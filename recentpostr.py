#!/usr/bin/python

# Spits out a Javascript embeddable list o' recent RSS stuff.

# Ryan Tucker, August 21 2009, <rtucker@gmail.com>

# TODO:
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
import timelimited
import urllib2

# Set up logging to syslog
logger = logging.getLogger('')
loghandler = logging.handlers.SysLogHandler('/dev/log',
                facility=logging.handlers.SysLogHandler.LOG_DAEMON)
logformatter = logging.Formatter('%(filename)s: %(levelname)s: %(message)s')
loghandler.setFormatter(logformatter)
logger.addHandler(loghandler)
logger.setLevel(logging.DEBUG)

# Set user agent for feedparser
feedparser.USER_AGENT = 'recentpostr/0.1 +http://blog.hoopycat.com/'

cachedout = []
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

def iterFeedList(filename='feedlist.txt'):
    fd = open(filename, 'r')
    for i in fd.readlines():
        if i.startswith("#"):
            pass
        elif i.strip() == '':
            pass
        else:
            splitted = i.strip().split('|')
            if len(splitted) == 1:
                yield {splitted[0]: ''}
            elif len(splitted) == 2:
                yield {splitted[0]: splitted[1]}

def checkRobotOK(url):
    rp = robotparser.RobotFileParser()

    try:
        logging.debug('Checking robot OK for %s' % url)
        request = urllib2.Request(getURLBase(url) + '/robots.txt',
                                  None, {'User-Agent': feedparser.USER_AGENT})
        robotsfd = urllib2.urlopen(request)
        if robotsfd.code != 200:
            logging.debug('robots.txt not found for %s, assuming OK' % url)
            return True
    except AttributeError:
        pass
    except IOError:
        logging.debug('Received IO Error opening robots.txt for %s' % url)
        return False

    rp.parse(robotsfd.readlines())

    result = rp.can_fetch(feedparser.USER_AGENT, url)
    logging.debug('robots.txt for %s says %s' % (url, str(result)))
    return result

def getURLBase(url):
    host = urllib2.splithost(urllib2.splittype(url)[1])[0]
    method = urllib2.splittype(url)[0]

    return method + '://' + host

def updateFeed(feedurl, etag=None, lastmodified=None):
    if etag in ['None', '']:
        etag = None
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

def updateBlogList(db, blogiter, checkevery=30*60):
    c = db.cursor()
    c.execute("select feedurl from blogcache")
    allrows = c.fetchall()
    blogdict = {}
    for i in blogiter:
        key = i.keys()[0]
        value = i[key]
        blogdict[key] = value
        if (key, ) not in allrows:
            logging.debug('New blog found: %s' % key)
            c.execute("insert into blogcache values(?,'','','','',1,1,'',1)", (key,))

    lastcheckthreshold = int(time.time()-checkevery)
    c.execute("select feedurl,etag,lasttime from blogcache where lastcheck < ? order by lastcheck", (lastcheckthreshold, ))
    rows = c.fetchall()
    starttime = time.time()
    deadtime = time.time()+3
    for results in rows:
        if deadtime-starttime < 0:
            logging.info('updateBlogList timeout reached')
            break
        updateFeed_timed = timelimited.TimeLimited(updateFeed,
            max(deadtime-starttime, 1))
        try:
            feed = None
            feed = updateFeed_timed(results[0], results[1], results[2])
        except timelimited.TimeLimitExpired:
            logging.info('updateFeed timeout reached')
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
    return blogdict

def iterCachedBlogRoll(db, blogdict):
    c = db.cursor()
    c.execute("""select feedurl,blogurl,blogtitle,lasttitle,lastlink,lasttime
                 from blogcache
                 order by lasttime desc""")
    rows = c.fetchall()
    for i in rows:
        if i[0] in blogdict:
            if blogdict[i[0]]:
                blogtitle = blogdict[i[0]]
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
    blogiter = iterFeedList()
    blogdict = updateBlogList(db, blogiter)
    element = iterCachedBlogRoll(db, blogdict)
    output = ''
    for i in range(0,displaymax):
        if type == 'javascript':
            output += str(formatOutputRowJavaScript(element.next()))
    return output

def wsgiInterface(environ, start_response):
    global cachedout, cachedgen, cachedttl
    start_response('200 OK', [('Content-Type', 'text/javascript')])
    if cachedout == [] or (cachedgen + cachedttl < time.time()):
        logging.debug('Regenerating cache (age: %i)' % (time.time() - cachedgen))
        cachedout = processOutput().split('\n')
        cachedgen = time.time()
    else:
        logging.debug('Outputting cache (age: %i)' % (time.time() - cachedgen))

    return cachedout

    logging.debug("I'm still running after returning a value... niiice")

def __main__():
    print processOutput()

if __name__ == '__main__': __main__()

