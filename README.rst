xray: N-D labeled arrays and datasets in Python
===============================================

.. image:: https://travis-ci.org/xray/xray.svg?branch=master
    :target: https://travis-ci.org/xray/xray

**xray** is an open source project and Python package that aims to bring the
labeled data power of pandas_ to the physical sciences, by providing
N-dimensional variants of the core pandas_ data structures, ``Series`` and
``DataFrame``: the xray ``DataArray`` and ``Dataset``.

Our goal is to provide a pandas-like and pandas-compatible toolkit for
analytics on multi-dimensional arrays, rather than the tabular data for which
pandas excels. Our approach adopts the `Common Data Model`_ for self-
describing scientific data in widespread use in the Earth sciences (e.g.,
netCDF_ and OPeNDAP_): ``xray.Dataset`` is an in-memory representation of a
netCDF file.

.. _pandas: http://pandas.pydata.org
.. _Common Data Model: http://www.unidata.ucar.edu/software/thredds/current/netcdf-java/CDM
.. _netCDF: http://www.unidata.ucar.edu/software/netcdf
.. _OPeNDAP: http://www.opendap.org/

Important links
---------------

- HTML documentation: http://xray.readthedocs.org
- Issue tracker: http://github.com/xray/xray/issues
- Source code: http://github.com/xray/xray
- PyData talk: https://www.youtube.com/watch?v=T5CZyNwBa9c

Why xray?
---------

Adding dimensions names and coordinate indexes to numpy's ndarray_ makes many
powerful array operations possible:

-  Apply operations over dimensions by name: ``x.sum('time')``.
-  Select values by label instead of integer location:
   ``x.loc['2014-01-01']`` or ``x.sel(time='2014-01-01')``.
-  Mathematical operations (e.g., ``x - y``) vectorize across multiple
   dimensions (known in numpy as "broadcasting") based on dimension
   names, not array shape.
-  Flexible split-apply-combine operations with groupby:
   ``x.groupby('time.dayofyear').mean()``.
-  Database like aligment based on coordinate labels that smoothly
   handles missing values: ``x, y = xray.align(x, y, join='outer')``.
-  Keep track of arbitrary metadata in the form of a Python dictionary:
   ``x.attrs``.

pandas_ excels at working with tabular data. That suffices for many statistical
analyses, but physical scientists rely on N-dimensional arrays -- which is
where **xray** comes in.

**xray** aims to provide a data analysis toolkit as powerful as pandas_ but
designed for working with homogeneous N-dimensional arrays
instead of tabular data. When possible, we copy the pandas API and rely on
pandas's highly optimized internals (in particular, for fast indexing).

Because **xray** implements the same data model as the netCDF_ file format,
xray datasets have a natural and portable serialization format. But it is also
easy to robustly convert an xray ``DataArray`` to and from a numpy ``ndarray``
or a pandas ``DataFrame`` or ``Series``, providing compatibility with the full
`PyData ecosystem <http://pydata.org/>`__.

Our target audience is anyone who needs N-dimensional labeled arrays, but we
are particularly focused on the data analysis needs of physical scientists --
especially geoscientists who already know and love netCDF.

.. _ndarray: http://docs.scipy.org/doc/numpy/reference/arrays.ndarray.html
.. _pandas: http://pandas.pydata.org

Get in touch
------------

- Mailing list: https://groups.google.com/forum/#!forum/xray-dev
- Twitter: http://twitter.com/shoyer

xray is an ambitious project and we have a lot of work to do make it as
powerful as it should be. We would love to hear your thoughts!

History
-------

xray is an evolution of an internal tool developed at `The Climate
Corporation`__, and was originally written by current and former Climate Corp
researchers Stephan Hoyer, Alex Kleeman and Eugene Brevdo.

__ http://climate.com/

License
-------

Copyright 2014, xray Developers

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
