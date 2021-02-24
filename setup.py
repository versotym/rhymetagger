
from distutils.core import setup
setup(
  name = 'rhymetagger',         
  packages = ['rhymetagger'],   
  version = '0.2',      
  license='MIT',        
  description = 'A simple collocation-driven recognition of rhymes',   
  author = 'Petr Plechac',                   
  author_email = 'plechac@ucl.cas.cz',      
  url = 'https://github.com/versotym/rhymetagger',
  download_url = 'https://github.com/versotym/rhymeTagger/archive/v_01.tar.gz',
  keywords = ['poetry', 'rhyme', 'versification'],   # Keywords that define your package best
  install_requires=[            # I get to this in a second
          'ujson',
          'string',
          'nltk',
          'subprocess',
          'collections',
          'ast',
      ],
  classifiers=[
    'Development Status :: 4 - Beta',      # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package
    'Intended Audience :: Developers',      # Define that your audience are developers
    'Topic :: Text Processing :: Linguistic',
    'License :: OSI Approved :: MIT License',   
    'Programming Language :: Python :: 3',      
  ],
)
view rawsetup.py hosted with ❤ by GitHub
