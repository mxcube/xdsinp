from distutils.core import setup

setup(name="xdsinp", version="0.1",
      description="Data analysis input files server",
      author="T. Boeglin (ESRF)",
      package_dir={"xdsinp": "xdsinp"},
      packages=["xdsinp", 'xdsinp.templates'],
      package_data={'xdsinp.templates':['*']},
      scripts=["bin/xdsinp"])
