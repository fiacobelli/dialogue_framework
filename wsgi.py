"""WSGI entry point for the transplant microsite app under /microsite."""

from web.app import app


class PrefixMiddleware:
    """Expose the Flask app below a URL prefix when served behind nginx."""

    def __init__(self, wsgi_app, prefix):
        self.app = wsgi_app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        if environ['PATH_INFO'].startswith(self.prefix):
            environ['PATH_INFO'] = environ['PATH_INFO'][len(self.prefix):] or '/'
            environ['SCRIPT_NAME'] = self.prefix
        return self.app(environ, start_response)


app.wsgi_app = PrefixMiddleware(app.wsgi_app, '/microsite')
