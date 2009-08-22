#!/usr/bin/python

# Runs recentpostr as a wsgi app.

wsgi = True

from recentpostr import wsgiInterface

if wsgi:
    from flup.server.fcgi import WSGIServer
    WSGIServer(wsgiInterface).run()
else:
    from wsgiref.simple_server import make_server
    srv = make_server('localhost', 5001, wsgiInterface)
    srv.serve_forever()

