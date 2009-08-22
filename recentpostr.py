#!/usr/bin/python

# Spits out a Javascript embeddable list o' recent RSS stuff.

# Ryan Tucker, August 21 2009, <rtucker@gmail.com>

# TODO:
# push to github
# limit the number of fetches per load (e.g. don't block for >2 seconds)
# "more sane" file output options
# cache robots.txt result

checkevery = 30*60    # check every ~30 minutes
displaymax = 4

import feedparser
import logging
import logging.handlers
import operator
import robotparser
import signal
import sqlite3
import sys
import time
import urllib

# Set up logging to syslog
logging.getLogger('').addHandler(logging.handlers.SysLogHandler('/dev/log'))
logging.getLogger('').setLevel(logging.DEBUG)

# Set user agent for feedparser
feedparser.USER_AGENT = 'recentpostr/0.1 +http://blog.hoopycat.com/'

# Set user agent for urllib
class URLopener(urllib.FancyURLopener):
    version = feedparser.USER_AGENT

urllib._urlopener = URLopener()

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
        robotsfd = urllib.urlopen(getURLBase(url) + '/robots.txt')
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
    timeoutUpdateBlogList = TimeoutFunction(updateBlogList, 3)
    try:
        blogdict = timeoutUpdateBlogList(db, blogiter)
    except TimeoutFunctionException:
        logging.info("Timed out on updateBlogList")
    element = iterCachedBlogRoll(db, blogdict)
    output = ''
    for i in range(0,displaymax):
        if type == 'javascript':
            output += str(formatOutputRowJavaScript(element.next()))
    return output

# timeout code from http://nick.vargish.org/clues/python-tricks.html
class TimeoutFunctionException(Exception): 
    """Exception to raise on a timeout""" 
    pass 

class TimeoutFunction: 
    def __init__(self, function, timeout): 
        self.timeout = timeout 
        self.function = function 

    def handle_timeout(self, signum, frame): 
        raise TimeoutFunctionException()

    def __call__(self, *args): 
        old = signal.signal(signal.SIGALRM, self.handle_timeout) 
        signal.alarm(self.timeout) 
        try: 
            result = self.function(*args)
        finally: 
            signal.signal(signal.SIGALRM, old)
        signal.alarm(0)
        return result 

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

