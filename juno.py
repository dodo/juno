# Built in library imports
import mimetypes
import re
import os
import sys
import traceback
import time
# Server imports
import urllib.parse
import cgi

class Juno(object):
    def __init__(self, configuration=None):
        """Takes an optional configuration dictionary. """
        global _hub
        if _hub is not None:
            print('Warning: there is already a Juno object created;', file=sys.stderr)
            print('         you might get some weird behavior.', file=sys.stderr)
        else: _hub = self
        self.routes = []
        # Find the directory of the user's app, so we can setup static/template_roots
        self.find_user_path(configuration)
        # Set options and merge in user-set options
        self.config = {
                # General settings / meta information
                'log':    True,
                'routes': self.routes,
                'self':   self,
                # Types and encodings
                'charset':      'utf-8',
                'content_type': 'text/html',
                # Server options
                'mode':     'dev',
                'scgi_port': 8000,
                'fcgi_port': 8000,
                'dev_port':  8000,
                'bind_address': '127.0.0.1',
                # Static file handling
                'use_static':     True,
                'static_url':     '/static/*:file/',
                'static_root':    os.path.join(self.app_path, 'static/'),
                'static_handler': static_serve,
                'static_expires': 0,
                # Template options
                'use_templates':           False,
                'template_lib':            'jinja2',
                'get_template_handler':    _get_template_handler,
                'render_template_handler': _render_template_handler,
                'auto_reload_templates':   True,
                'translations':            [],
                'template_kwargs':         {},
                'template_root':           os.path.join(self.app_path, 'templates/'),
                '404_template':            '404.html',
                '500_template':            '500.html',
                '404_mimetype':            None,
                '500_mimetype':            None,
                '500_traceback':           False,
                # Database options
                'use_db':      False,
                'db_type':     'sqlite',
                'db_location': ':memory:',
                'db_models':   {},
                # Session options
                'use_sessions': False,
                'session_lib':  'beaker',
                'session_kwargs': {},
                'session_type': 'cookie',
                'session_key': 'session',
                'session_secret': '',
                # Debugger
                'use_debugger': False,
                'raise_view_exceptions': False,
                # Custom middleware
                'middleware': []
        }
        if configuration is not None: self.config.update(configuration)
        if 'app_apth' not in self.config: self.config['app_path'] = self.app_path
        # Set up the static file handler
        if self.config['use_static']:
            self.setup_static()
        # Set up templating
        if self.config['use_templates']:
            self.setup_templates()
        # Set up the database
        if self.config['use_db']:
            self.setup_database()

    def find_user_path(self, configuration):
        if configuration is not None and 'app_path' in configuration:
            self.app_path = configuration['app_path']
            return
        # This section may look strange, but it seems like the only solution.
        # Basically, we need the directory of the user's app in order to setup
        # the static/template_roots.  When we run under mod_wsgi, we can't use
        # either os.getcwd() or sys.path[0].  This code generates an exception,
        # then goes up to the top stack frame (the user's code), and finds
        # the location of that.
        try:
            raise Exception
        except:
            traceback = sys.exc_info()[2]
            if traceback is None:
                print('Warning: Failed to find current working directory.', file=sys.stderr)
                print('         Default static_root and template_root', file=sys.stderr)
                print('         values may not work correctly.', file=sys.stderr)
                filename = './'
            else:
                frame = traceback.tb_frame
                while traceback is not None:
                    if frame.f_back is None:
                        break
                    frame = frame.f_back
                filename = frame.f_code.co_filename
        self.app_path = os.path.abspath(os.path.dirname(filename))

    def setup_static(self):
        self.route(self.config['static_url'], self.config['static_handler'], '*')

    def setup_templates(self):
        if self.config['template_lib'] == 'jinja2':
            import jinja2
            # If the user specified translation objects, load i18n extension
            if len(self.config['translations']) != 0:
                extensions = ['jinja2.ext.i18n']
            else:
                extensions = []
            kwargs = self.config['template_kwargs']
            if 'extensions' in kwargs: extensions.extend(kwargs['extensions'])
            kwargs.update({
                'loader'      : jinja2.FileSystemLoader(
                                searchpath = self.config['template_root'],
                                encoding   = self.config['charset'],
                              ),
                'auto_reload' : self.config['auto_reload_templates'],
                'extensions' : extensions
            })
            env = self.config['template_env'] = jinja2.Environment(**kwargs)
            for translation in self.config['translations']:
                env.install_gettext_translations(translation)
        if self.config['template_lib'] == 'mako':
            import mako.lookup
            self.config['template_env'] = mako.lookup.TemplateLookup(
                directories       = [self.config['template_root']],
                input_encoding    = self.config['charset'],
                output_encoding   = self.config['charset'],
                filesystem_checks = self.config['auto_reload_templates'],
                **self.config['template_kwargs']
            )

    def setup_database(self):
        # DB library imports
        from sqlalchemy import (create_engine, Table, MetaData, Column, Integer,
                                String, Unicode, Text, UnicodeText, Date, Numeric,
                                Time, Float, DateTime, Interval, Binary, Boolean,
                                PickleType)
        from sqlalchemy.orm import sessionmaker, mapper, scoped_session
        # Create global name mappings for model()
        global column_mapping
        column_mapping = {'string': String,       'str': String,
                         'integer': Integer,      'int': Integer,
                         'unicode': Unicode,     'text': Text,
                     'unicodetext': UnicodeText, 'date': Date,
                         'numeric': Numeric,     'time': Time,
                           'float': Float,   'datetime': DateTime,
                        'interval': Interval,  'binary': Binary,
                         'boolean': Boolean,     'bool': Boolean,
                      'pickletype': PickleType,
        }
        # Add a few SQLAlchemy types to globals() so we can use them in models
        globals().update({'Column': Column, 'Table': Table, 'Integer': Integer,
                          'MetaData': MetaData, 'mapper': mapper})
        # Ensures correct slash number for sqlite
        if self.config['db_type'] == 'sqlite':
            self.config['db_location'] = '/' + self.config['db_location']
        eng_name = self.config['db_type'] + '://' + self.config['db_location']
        self.config['db_engine'] = create_engine(eng_name)
        self.config['db_session'] = scoped_session(sessionmaker(bind=self.config['db_engine']))

    def run(self, mode=None):
        """Runs the Juno hub, in the set mode (default now is dev). """
        # If no mode is specified, use the one from the config
        if mode is None: mode = config('mode')
        # Otherwise store the specified mode
        else: config('mode', mode)

        if   mode == 'dev':  run_dev(config('bind_address'), config('dev_port'),  self.request)
        elif mode == 'scgi': run_scgi(config('bind_address'), config('scgi_port'), self.request)
        elif mode == 'fcgi': run_fcgi(config('bind_address'), config('fcgi_port'), self.request)
        elif mode == 'wsgi': return run_wsgi(self.request)
        elif mode == 'appengine': run_appengine(self.request)
        else:
            print('Error: unrecognized mode', file=sys.stderr)
            print('       exiting juno...', file=sys.stderr)

    def request(self, request, method='*', params=None, **kwargs):
        """Called when a request is received.  Routes a url to its view.
        Returns a 3-tuple (status_string, headers, body) from
        JunoResponse.render()."""
        if config('log'): print('%s request for %s...' %(method, request))
        req_obj = JunoRequest(kwargs)
        # Set the global response object in case the view wants to use it
        global _response
        _response = JunoResponse()
        # Add a slash if there isn't one - avoids frustrating matching bugs
        if request[-1] != '/': request += '/'
        for route in self.routes:
            if not route.match(request, method): continue
            if params:
                org_params = route.params.copy()
                route.params.update(params)
            if config('log'): print('%s matches, calling %s()...\n' %(
                route.old_url, route.func.__name__))
            # Get the return from the view
            if config('raise_view_exceptions') or config('use_debugger'):
                response = route.dispatch(req_obj)
            else:
                try:
                    response = route.dispatch(req_obj)
                except:
                    if params: route.params = org_params
                    return servererror(error=cgi.escape(traceback.format_exc())).render()
            # If nothing returned, use the global object
            if response is None: response = _response
            # If user gives some params, be sure to reset it
            if params: route.params = org_params
            # If we don't have a string, render the Response to one
            if isinstance(response, JunoResponse):
                return response.render()
            return JunoResponse(body=response).render()
        # No matches - 404
        return notfound(error='No matching routes registered').render()

    def route(self, url, func, method):
        """Attaches a view to a url or list of urls, for a given function. """
        # An implicit route - the url is just the function name
        if url is None: url = '/' + func.__name__ + '/'
        # If we just have one url, add it
        if type(url) == str: self.routes.append(JunoRoute(url, func, method))
        # Otherwise add each url in the list
        else:
            for u in url: self.routes.append(JunoRoute(u, func, method))

    def __getattr__(self, attr):
        if attr in list(self.config.keys()):
            return self.config[attr]
        return None

    def __repr__(self): return '<Juno>'

class JunoRoute(object):
    """Uses a simplified regex to grab url parts:
    i.e., '/hello/*:name/' compiles to '^/hello/(?P<name>\w+)/' """

    # RE to match the splat format
    splat_re = re.compile('^(?P<type>[*w]?):(?P<var>\w+)$')

    def __init__(self, url, func, method):
        # Make sure the url begins and ends in a '/'
        if url[0] != '/': url = '/' + url
        if url[-1] != '/': url += '/'
        # Store the old one before we modify it (we use it for __repr__)
        self.old_url = url
        # Start building our modified url
        buffer = '^'
        for part in url.split('/'):
            # Beginning and end entries are empty, so skip them
            if not part: continue
            md = self.splat_re.match(part)
            # If it doesn't match, just add it without modification
            if not md:
                buffer += '/' + part
            else:
                # Otherwise replace it with python's regex format
                patterns = {'*': '.+', 'w': r'\w+'}
                type_ = md.group('type') or '*'
                if type_ not in patterns:
                    raise ValueError('Invalid parse type: %s'%type_)
                buffer += '/(?P<%s>%s)'%(md.group('var'), patterns[type_])
        # If we don't end with a wildcard, add a end of line modifier
        if buffer[-1] != ')': buffer += '/$'
        else: buffer += '/'
        self.url = re.compile(buffer)
        self.func = func
        self.method = method.upper()
        self.params = {}

    def match(self, request, method):
        """Matches a request uri to this url object. """
        match_obj = self.url.match(request)
        if match_obj is None: return False
        # Make sure the request method matches
        if self.method != '*' and self.method != method: return False
        # Store the parts that matched
        self.params.update(match_obj.groupdict())
        return True

    def dispatch(self, req):
        """Calls the route's view with any named parameters."""
        return self.func(req, **self.params)

    def __repr__(self):
        return '<JunoRoute: %s %s - %s()>' %(self.method, self.old_url,
                                             self.func.__name__)

class JunoRequest(object):
    """Offers following members:
        raw           => the header dict used to construct the JunoRequest
        location      => uri being requested, without query string ('/' from '/?a=6')
        full_location => uri with query string ('/?a=6' from '/?a=6')
        user_agent    => the user agent string of requester
    """
    def __init__(self, request):
        # Make sure we have a request uri, and it ends in '/'
        if request['PATH_INFO'][-1] != '/': request['PATH_INFO'] += '/'
        # Set some instance variables
        self.raw = request
        self.raw['input'] = {}
        self.location = request['PATH_INFO']
        # If we get a REQUEST_URI, store it.  Otherwise copy PATH_INFO
        if 'REQUEST_URI' in request:
            self.full_location = request['REQUEST_URI']
        else: self.full_location = self.location
        # Find the right user agent header
        if 'HTTP_USER_AGENT' in request:
            self.user_agent = request['HTTP_USER_AGENT']
        elif 'User-Agent' in request:
            self.user_agent = request['User-Agent']
        else: self.user_agent = ''
        self.combine_request_dicts()
        # Check for sessions
        if config('use_sessions') and config('session_lib') == 'beaker':
            self.session = request['beaker.session']

    def combine_request_dicts(self):
        input_dict = self.raw['QUERY_DICT'].copy()
        for k, v in list(self.raw['POST_DICT'].items()):
            # Combine repeated keys
            if k in list(input_dict.keys()): input_dict[k].extend(v)
            # Otherwise just add this key
            else: input_dict[k] = v
        # Reduce the dict - change one item lists ([a] to a)
        for k, v in list(input_dict.items()):
            if len(v) == 1: input_dict[k] = v[0]
        self.raw['input'] = input_dict

    def __getattr__(self, attr):
        # Try returning values from self.raw
        if attr in list(self.keys()): return self.raw[attr]
        if attr == 'session' and config('log'):
            print("Error: To use sessions, enable 'use_sessions'", file=sys.stderr)
            print("       when calling juno.init()", file=sys.stderr)
            print("", file=sys.stderr)
        return None

    def input(self, arg=None):
        # No args: return the whole dictionary
        if arg is None: return self.raw['input']
        # Otherwise try to return the value for that key
        if arg in self.raw['input']:
            return self.raw['input'][arg]
        return None

    # Make JunoRequest act as a dictionary for self.raw
    def __getitem__(self, key): return self.raw[key]
    def __setitem__(self, key, val): self.raw[key] = val
    def keys(self): return list(self.raw.keys())
    def items(self): return list(self.raw.items())
    def values(self): return list(self.raw.values())
    def __len__(self): return len(self.raw)
    def __contains__(self, key): return key in self.raw

    def __repr__(self):
        return '<JunoRequest: %s>' %self.location

class JunoResponse(object):
    status_codes = {
        200: 'OK',
        301: 'Moved Permanently',
        302: 'Found',
        303: 'See Other',
        304: 'Not Modified',
        400: 'Bad Request',
        403: 'Forbidden',
        404: 'Not Found',
        405: 'Method Not Allowed',
        410: 'Gone',
        500: 'Internal Server Error',
    }
    def __init__(self, configuration=None, **kwargs):
        # Set options and merge in user-set options
        self.config = {
            'body': '',
            'status': 200,
            'headers': { 'Content-Type': "%s; charset=%s"%(config('content_type'),config('charset')), },
        }
        if configuration is None: configuration = {}
        self.config.update(configuration)
        self.config.update(kwargs)
        self.config['headers']['Content-Length'] = get_content_length(self.config['body'])

    # Add text and adjust content-length
    def append(self, text):
        if type(text) is bytes:
            if self.config['headers']['Content-Type'].startswith('text'):
                text = str(text, config('charset'))
            else:
                self.config['body'] = text
                self.config['headers']['Content-Length'] = get_content_length(text)
                return self
        self.config['body'] += str(text)
        self.config['headers']['Content-Length'] = get_content_length(self.config['body'])
        return self

    # Implement +=
    def __iadd__(self, text):
        return self.append(text)

    def render(self):
        """Returns a 3-tuple (status_string, headers, body)."""
        status_string = '%s %s' %(self.config['status'],
                                  self.status_codes[self.config['status']])
        headers = [(k, str(v)) for k, v in list(self.config['headers'].items())]
        return (status_string, headers, self.config['body'])

    # Set a header value
    def header(self, header, value):
        self.config['headers'][header] = value
        return self

    # Modify the headers dictionary when the response is treated like a dict
    def __setitem__(self, header, value): self.header(header, value)
    def __getitem__(self, header): return self.config['headers'][header]

    def __getattr__(self, attr):
        return self.config[attr]

    def __repr__(self):
        return '<JunoResponse: %s %s>' %(self.status, self.status_codes[self.status])

#
#   Functions to deal with the global Juno object (_hub)
#

_hub = None

def init(configuration=None):
    """Set up Juno with an optional configuration."""
    # Only set it up if we haven't already. (Avoids multiple Juno objects)
    global _hub # Use global keyword here to avoid SyntaxWarning
    if _hub is None:
        _hub = Juno(configuration)
    return _hub

def config(key, value=None):
    """Get or set configuration options."""
    if _hub is None: init()
    if value is None:
        # Either pass a configuration dictionary
        if type(key) == dict: _hub.config.update(key)
        # Or retrieve a value
        else:
            if key in list(_hub.config.keys()):
                return _hub.config[key]
            return None
    # Or set a specific value
    else: _hub.config[key] = value

def run(mode=None):
    """Start Juno, with an optional mode argument."""
    if _nut is not None:
        print('Discard starting Juno because there is a nutshell opened.', file=sys.stderr)
        return
    if _hub is None: init()
    if len(sys.argv) > 1:
        if '-mode=' in sys.argv[1]: mode = sys.argv[1].split('=')[1]
        elif '-mode' == sys.argv[1]: mode = sys.argv[2]
    return _hub.run(mode)


_nut = None

def open_nutshell():
    global _nut, _hub
    if _nut is not None:
        print('Warning: there is already a Juno object in the nutshell;', file=sys.stderr)
        print('         there can only be one in by time.', file=sys.stderr)
        return
    _nut, _hub = _hub, None

def close_nutshell():
    global _nut, _hub
    if _nut is not None:
        _hub, _nut = _nut, None

def getHub():
    return _hub

def get_content_length(data):
    if isinstance(data, str):
        return len(bytes(data, config('charset')))
    return len(data)

#
#   Decorators to add routes based on request methods
#

def route(url=None, method='*'):
    if _hub is None: init()
    def wrap(f): _hub.route(url, f, method)
    return wrap

def post(url=None):   return route(url, 'post')
def get(url=None):    return route(url, 'get')
def head(url=None):   return route(url, 'head')
def put(url=None):    return route(url, 'put')
def delete(url=None): return route(url, 'delete')

#
#   Functions to deal with the global response object (_response)
#

_response = None

def append(body):
    """Add text to response body. """
    global _response
    return _response.append(body)

def header(key, value):
    """Set a response header. """
    global _response
    return _response.header(key, value)

def content_type(type):
    """Set the content type header. """
    header('Content-Type', type)

def status(code):
    _response.config['status'] = code

#
#   Convenience functions for 404s and redirects
#

def subdirect(web, hub, request):
    global _hub
    if request == '': request = '/'
    if request[-1] != '/': request += '/'
    if request[ 0] != '/': request = '/' + request
    if config('log'): print('subdirecting from %s to %s' % (web['PATH_INFO'], request))
    org, _hub = _hub, hub
    status_string, headers, body = hub.request(request, web['REQUEST_METHOD'], **web.raw)
    _hub = org
    for key, value in headers: header(key, value)
    status(int(status_string.split()[0]))
    if _response.body != body: append(body) #FIXME
    return _response

def redirect(url, code=302):
    status(code)
    # clear the response headers and add the location header
    _response.config['headers'] = { 'Location': url }
    return _response

def direct(web, request, **kwargs):
    status_string, headers, body = _hub.request(
        request, web['REQUEST_METHOD'], params=kwargs, **web.raw)
    for key, value in headers: header(key, value)
    status(int(status_string.split()[0]))
    if _response.body != body: append(body) #FIXME
    return _response

def assign(from_, to):
    if type(from_) not in (list, tuple): from_ = [from_]
    for url in from_:
        @route(url)
        def temp(web): redirect(to)

def notfound(error='Unspecified error', file=None):
    """Sets the response to a 404, sets the body to 404_template."""
    if config('log'): print('Not Found: %s' % error, file=sys.stderr)
    status(404)
    mt = config('404_mimetype')
    if mt:
        content_type(mt)
    if file is None: file = config('404_template')
    return template(file, error=error)

def servererror(error='Unspecified error', file=None):
    """Sets the response to a 500, sets the body to 500_template."""
    t, v, tb = sys.exc_info()
    if config('log'):
        print('Error: (%s, %s)' % (t, v), file=sys.stderr)
        if config('500_traceback'):
            traceback.print_tb(tb)
    status(500)
    mt = config('500_mimetype')
    if mt:
        content_type(mt)
    if file is None: file = config('500_template')
    # Resets the response, in case the error occurred as we added data to it
    _response.config['body'] = ''
    return template(file, error=error)

#
#   Serve static files.
#

def static_serve(web, file):
    """The default static file serve function. Maps arguments to dir structure."""
    file = os.path.join(config('static_root'), file)
    realfile = os.path.realpath(file)
    if not realfile.startswith(os.path.realpath(config('static_root'))):
        notfound("that file could not be found/served")
    elif yield_file(file) != 7:
        notfound("that file could not be found/served")
    mtime = os.stat(file).st_mtime
    header('Last-Modified', time.strftime('%a, %d %b %Y %H:%M:%S +0000', time.gmtime(mtime)))
    if config('static_expires'):
        header('Expires', time.strftime('%a, %d %b %Y %H:%M:%S +0000', time.gmtime(time.time() + config('static_expires'))))

def yield_file(filename, type=None):
    """Append the content of a file to the response. Guesses file type if not
    included.  Returns 1 if requested file can't be accessed (often means doesn't
    exist).  Returns 2 if requested file is a directory.  Returns 7 on success. """
    if not os.access(filename, os.F_OK): return 1
    if os.path.isdir(filename): return 2
    if type is None:
        guess = mimetypes.guess_type(filename)[0]
        if guess is None: content_type('text/plain')
        else: content_type(guess)
    else: content_type(type)
    append(open(filename, 'rb').read())
    return 7

#
#   Templating
#

def template(template_path, template_dict=None, **kwargs):
    """Append a rendered template to response.  If template_dict is provided,
    it is passed to the render function.  If not, kwargs is."""
    # Retreive a template object.
    t = get_template(template_path)
    # Render it without arguments.
    if not kwargs and not template_dict:
        return append(render_template(t))
    # Render the template with a provided template dictionary
    if template_dict:
        return append(render_template(t, **template_dict))
    # Render the template with **kwargs
    return append(render_template(t, **kwargs))

def get_template(template_path):
    """Returns a template object by calling the default value of
    'get_template_handler'.  Allows getting a template to be the same
    regardless of template library."""
    return config('get_template_handler')(template_path)

# The default value of config('get_template_handler')
def _get_template_handler(template_path):
    """Return a template object.  This is defined for the Jinja2 and
    Mako libraries, otherwise you have to override it.  Takes one
    parameter: a string containing the desired template path.  Needs
    to return an object that will be passed to your rendering function."""
    return config('template_env').get_template(template_path)

def render_template(template_obj, **kwargs):
    """Renders a template object by using the default value of
    'render_template_handler'.  Allows rendering a template to be consistent
    regardless of template library."""
    return config('render_template_handler')(template_obj, **kwargs)

# The default value of config('render_template_handler')
def _render_template_handler(template_obj, **kwargs):
    """Renders template object with an optional dictionary of values.
    Defined for Jinja2 and Mako - override it if you use another
    library.  Takes a template object as the first parameter, with an
    optional **kwargs parameter.  Needs to return a string."""
    return template_obj.render(**kwargs)

def autotemplate(urls, template_path, **kwargs):
    """Automatically renders a template for a given path.  Currently can't
    use any arguments in the url."""
    if type(urls) not in (list, tuple): urls = [urls]
    for url in urls:
        @route(url)
        def temp(web,**tempkwargs):
            tempkwargs.update(kwargs)
            template(template_path,tempkwargs)

####
#   Data modeling functions
####

# Map SQLAlchemy's types to string versions of them for convenience
column_mapping = {} # Constructed in Juno.setup_database

session = lambda: config('db_session')()

def model(model_name, **kwargs):
    if not _hub: init()
    # Functions for the class
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
    def add(self):
        session().add(self)
        return self
    def save(self):
        s = session()
        if self not in s: s.add(self)
        s.commit()
        return self
    def __repr__(self):
        return '<%s: id = %s>' %(self.__name__, self.id)
    def __str__(self):
        return '<%s: id = %s>' %(self.__name__, self.id)
    # Some static functions for the class
    def find_func(cls, *args):
        return session().query(cls, *args)
    # Build the class's __dict__
    cls_dict = {'__init__': __init__,
                'add':      add,
                'save':     save,
                '__name__': model_name,
                '__repr__': __repr__,
                '__str__':  __str__,
                'find':     None,       # Defined later
               }
    # Parse kwargs to get column definitions
    cols = [ Column('id', Integer, primary_key=True), ]
    for k, v in kwargs.items():
        if hasattr(v, '__call__'):
            cls_dict[k] = v
        elif isinstance(v, Column):
            if not v.name: v.name = k
            cols.append(v)
        elif type(v) == str:
            v = v.lower()
            if v in column_mapping: v = column_mapping[v]
            else: raise NameError("'%s' is not an allowed database column" %v)
            cols.append(Column(k, v))
    # Create the class
    tmp = type(model_name, (object,), cls_dict)
    # Add the functions that need an instance of the class
    tmp.find = classmethod(find_func)
    # Create the table
    metadata = MetaData()
    tmp_table = Table(model_name + 's', metadata, *cols)
    metadata.create_all(config('db_engine'))
    # Map the table to the created class
    mapper(tmp, tmp_table)
    # Track the class
    config('db_models')[model_name] = tmp
    return tmp

def find(model_cls):
    if isinstance(model_cls, str):
        try: model_cls = config('db_models')[model_cls]
        except: raise NameError("No such model exists ('%s')" %model_cls)
    return session().query(model_cls)

####
#   Juno's Servers - Development (using WSGI), and SCGI (using Flup)
####

def get_application(process_func):
    def application(environ, start_response):
        # This may be temporary - I was getting weird errors where
        # the `environ` was None.  Seems to have stopped, but I don't
        # know why.  This message was to clarify what happened.
        if environ is None:
            print('Error: environ is None for some reason.', file=sys.stderr)
            print('Error: environ=%s' %environ, file=sys.stderr)
            sys.exit()
        # Ensure some variable exist (WSGI doesn't guarantee them)
        if 'PATH_INFO' not in list(environ.keys()) or not environ['PATH_INFO']:
            environ['PATH_INFO'] = '/'
        if 'QUERY_STRING' not in list(environ.keys()):
            environ['QUERY_STRING'] = ''
        if 'CONTENT_LENGTH' not in list(environ.keys()) or not environ['CONTENT_LENGTH']:
            environ['CONTENT_LENGTH'] = '0'
        # Standardize some header names
        environ['DOCUMENT_URI'] = environ['PATH_INFO']
        if environ['QUERY_STRING']:
            environ['REQUEST_URI'] = environ['PATH_INFO']+'?'+environ['QUERY_STRING']
        else:
            environ['REQUEST_URI'] = environ['DOCUMENT_URI']
        # Parse query string arguments
        environ['QUERY_DICT'] = urllib.parse.parse_qs(environ['QUERY_STRING'],
                                             keep_blank_values=1)
        if environ['REQUEST_METHOD'] in ('POST', 'PUT') \
            and environ['CONTENT_TYPE'] in ('application/x-www-form-urlencoded', \
                'multipart/form-data'):
            fs = cgi.FieldStorage(fp=environ['wsgi.input'],
                                  environ=environ,
                                  keep_blank_values=True)

            post_dict = {}
            if fs.list:
                for field in fs.list:
                    if field.filename:
                        value = field
                    else:
                        value = field.value

                    # Each element of post_dict will be a list, even if it contains only
                    # one item. This is in line with QUERY_DICT which also works like this.
                    if not field.name in post_dict:
                        post_dict[field.name] = [value]
                    else:
                        post_dict[field.name].append(value)

            environ['POST_DICT'] = post_dict
        else: environ['POST_DICT'] = {}
        # Done parsing inputs, now ready to send to Juno
        status_str, headers, body = process_func(environ['PATH_INFO'],
                                                 environ['REQUEST_METHOD'],
                                                 **environ)
        start_response(status_str, headers)
        if config('use_sessions'): session().close()
        if isinstance(body, str): body = body.encode(config('charset'))
        return [body]

    middleware_list = []
    if config('use_debugger'):
        middleware_list.append(('werkzeug.DebuggedApplication', {'evalex': True}))
    if config('use_sessions') and config('session_lib') == 'beaker':
        opts = {'session.key': config('session_key'), 'session.secret': config('session_secret'), 'session.cookie_expires': False}
        opts.update(config('session_kwargs'))
        if config('session_type') == 'cookie':
            opts['session.type'] = 'cookie'
            opts['session.validate_key'] = config('session_secret')
        else:
            opts['session.type'] = 'ext:database'
            opts['session.url'] = config('db_type') + '://' + config('db_location')
        middleware_list.append(('beaker.middleware.SessionMiddleware', opts))
    middleware_list.extend(config('middleware'))
    application = _load_middleware(application, middleware_list)

    return application

def _load_middleware(application, middleware_list):
    for middleware, args in middleware_list:
        parts = middleware.split('.')
        module = '.'.join(parts[:-1])
        name = parts[-1]
        try:
            obj = getattr(__import__(module, None, None, [name]), name)
            application = obj(application, **args)
        except (ImportError, AttributeError):
            print('Warning: failed to load middleware %s' % name)
    return application

def run_dev(addr, port, process_func):
    from wsgiref.simple_server import make_server
    app = get_application(process_func)
    print('')
    print('running Juno development server, <C-c> to exit...')
    print('connect to 127.0.0.1:%s to use your app...' %port)
    print('')
    srv = make_server(addr, port, app)
    try:
        srv.serve_forever()
    except:
        print('interrupted; exiting juno...')
        srv.socket.close()

def run_scgi(addr, port, process_func):
    from flup.server.scgi_fork import WSGIServer as SCGI
    app = get_application(process_func)
    SCGI(application=app, bindAddress=(addr, port)).run()

def run_fcgi(addr, port, process_func):
    from flup.server.fcgi import WSGIServer as FCGI
    app = get_application(process_func)
    FCGI(app, bindAddress=(addr, port)).run()

def run_wsgi(process_func):
    sys.stdout = sys.stderr
    return get_application(process_func)

def run_appengine(process_func):
    sys.stdout = sys.stderr
    from google.appengine.ext.webapp.util import run_wsgi_app
    run_wsgi_app(get_application(process_func))
