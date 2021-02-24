
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
  download_url = 'https://github.com/versotym/rhymeTagger/archive/v0.2.tar.gz',
  keywords = ['poetry', 'rhyme', 'versification'],   
  install_requires=[            
          'ujson',
          'string',
          'nltk',
          'subprocess',
          'collections',
          'ast',
      ],
  classifiers=[
    'Development Status :: 4 - Beta',      
    'Intended Audience :: Developers',      
    'Topic :: Text Processing :: Linguistic',
    'License :: OSI Approved :: MIT License',   
    'Programming Language :: Python :: 3',      
  ],
)
