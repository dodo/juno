from distutils.core import setup
import sys

try:
    import jinja2
except:
    print '** Jinja2 templates are required by Juno'
    print '** Download from: http://pypi.python.org/pypi/Jinja2'
    sys.exit()

try:
    import sqlalchemy
except:
    print '** SQLAlchemy is required by Juno'
    print '** Download from: http://sqlalchemy.org/download.html'
    sys.exit()

try:
    import flup
except:
    print '** To use SCGI, Juno requires flup'
    print '** Download from: http://trac.saddi.com/flup/'
    print "** If you don't want SCGI, disregard this message"

setup(name         = 'juno',
      description  = 'A lightweight Python web framework',
      author       = 'Brian Reily',
      author_email = 'brian@brianreily.com',
      url          = 'http://brianreily.com/project/juno/',
      version      = '0.1',
      py_modules   = ['juno'],
     )
