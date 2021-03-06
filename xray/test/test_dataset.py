from copy import copy, deepcopy
from textwrap import dedent
try:
    import cPickle as pickle
except ImportError:
    import pickle

import numpy as np
import pandas as pd

from xray import align, concat, backends, Dataset, DataArray, Variable
from xray.core import indexing, utils
from xray.core.pycompat import iteritems, OrderedDict

from . import TestCase, unittest


def create_test_data(seed=None):
    rs = np.random.RandomState(seed)
    _vars = {'var1': ['dim1', 'dim2'],
             'var2': ['dim1', 'dim2'],
             'var3': ['dim3', 'dim1']}
    _dims = {'dim1': 8, 'dim2': 9, 'dim3': 10}

    obj = Dataset()
    obj['time'] = ('time', pd.date_range('2000-01-01', periods=20))
    obj['dim1'] = ('dim1', np.arange(_dims['dim1']))
    obj['dim2'] = ('dim2', 0.5 * np.arange(_dims['dim2']))
    obj['dim3'] = ('dim3', list('abcdefghij'))
    for v, dims in sorted(_vars.items()):
        data = rs.normal(size=tuple(_dims[d] for d in dims))
        obj[v] = (dims, data, {'foo': 'variable'})
    obj.coords['numbers'] = ('dim3', [0, 1, 2, 0, 0, 1, 1, 2, 2, 3])
    return obj


class UnexpectedDataAccess(Exception):
    pass


class InaccessibleArray(utils.NDArrayMixin):
    def __init__(self, array):
        self.array = array

    def __getitem__(self, key):
        raise UnexpectedDataAccess("Tried accessing data")


class InaccessibleVariableDataStore(backends.InMemoryDataStore):
    def __init__(self):
        self.dims = OrderedDict()
        self._variables = OrderedDict()
        self.attrs = OrderedDict()

    def set_variable(self, name, variable):
        self._variables[name] = variable
        return self._variables[name]

    def open_store_variable(self, var):
        data = indexing.LazilyIndexedArray(InaccessibleArray(var.values))
        return Variable(var.dims, data, var.attrs)

    @property
    def store_variables(self):
        return self._variables


class TestDataset(TestCase):
    def test_repr(self):
        data = create_test_data(seed=123)
        data.attrs['foo'] = 'bar'
        # need to insert str dtype at runtime to handle both Python 2 & 3
        expected = dedent("""\
        <xray.Dataset>
        Dimensions:  (dim1: 8, dim2: 9, dim3: 10, time: 20)
        Coordinates:
          * dim1     (dim1) int64 0 1 2 3 4 5 6 7
          * dim2     (dim2) float64 0.0 0.5 1.0 1.5 2.0 2.5 3.0 3.5 4.0
          * dim3     (dim3) %s 'a' 'b' 'c' 'd' 'e' 'f' 'g' 'h' 'i' 'j'
          * time     (time) datetime64[ns] 2000-01-01 2000-01-02 2000-01-03 2000-01-04 ...
            numbers  (dim3) int64 0 1 2 0 0 1 1 2 2 3
        Variables:
            var1     (dim1, dim2) float64 -1.086 0.9973 0.283 -1.506 -0.5786 1.651 -2.427 -0.4289 ...
            var2     (dim1, dim2) float64 1.162 -1.097 -2.123 1.04 -0.4034 -0.126 -0.8375 -1.606 ...
            var3     (dim3, dim1) float64 0.5565 -0.2121 0.4563 1.545 -0.2397 0.1433 0.2538 ...
        Attributes:
            foo: bar""") % data['dim3'].dtype
        actual = '\n'.join(x.rstrip() for x in repr(data).split('\n'))
        print(actual)

        expected = dedent("""\
        <xray.Dataset>
        Dimensions:  ()
        Coordinates:
            *empty*
        Variables:
            *empty*""")
        actual = '\n'.join(x.rstrip() for x in repr(Dataset()).split('\n'))
        print(actual)
        self.assertEqual(expected, actual)

        # verify that ... doesn't appear for scalar coordinates
        data = Dataset({'foo': ('x', np.ones(10))}).mean()
        expected = dedent("""\
        <xray.Dataset>
        Dimensions:  ()
        Coordinates:
            *empty*
        Variables:
            foo      float64 1.0""")
        actual = '\n'.join(x.rstrip() for x in repr(data).split('\n'))
        print(actual)
        self.assertEqual(expected, actual)

    def test_constructor(self):
        x1 = ('x', 2 * np.arange(100))
        x2 = ('x', np.arange(1000))
        z = (['x', 'y'], np.arange(1000).reshape(100, 10))

        with self.assertRaisesRegexp(ValueError, 'conflicting sizes'):
            Dataset({'a': x1, 'b': x2})
        with self.assertRaisesRegexp(ValueError, 'must be defined with 1-d'):
            Dataset({'a': x1, 'x': z})

        # verify handling of DataArrays
        expected = Dataset({'x': x1, 'z': z})
        actual = Dataset({'z': expected['z']})
        self.assertDatasetIdentical(expected, actual)

    def test_constructor_1d(self):
        expected = Dataset({'x': (['x'], 5.0 + np.arange(5))})
        actual = Dataset({'x': 5.0 + np.arange(5)})
        self.assertDatasetIdentical(expected, actual)

        actual = Dataset({'x': [5, 6, 7, 8, 9]})
        self.assertDatasetIdentical(expected, actual)

    def test_constructor_0d(self):
        expected = Dataset({'x': ([], 1)})
        for arg in [1, np.array(1), expected['x']]:
            actual = Dataset({'x': arg})
            self.assertDatasetIdentical(expected, actual)

        d = pd.Timestamp('2000-01-01T12')
        args = [True, None, 3.4, np.nan, 'hello', u'uni', b'raw',
                np.datetime64('2000-01-01T00'), d, d.to_datetime()]
        for arg in args:
            print(arg)
            expected = Dataset({'x': ([], arg)})
            actual = Dataset({'x': arg})
            self.assertDatasetIdentical(expected, actual)

    def test_constructor_with_coords(self):
        with self.assertRaisesRegexp(ValueError, 'redundant variables and co'):
            Dataset({'a': ('x', [1])}, {'a': ('x', [1])})

        ds = Dataset({}, {'a': ('x', [1])})
        self.assertFalse(ds.vars)
        self.assertItemsEqual(ds.coords.keys(), ['x', 'a'])

    def test_properties(self):
        ds = create_test_data()
        self.assertEqual(ds.dims,
                         {'dim1': 8, 'dim2': 9, 'dim3': 10, 'time': 20})

        self.assertItemsEqual(ds, list(ds._arrays))
        self.assertItemsEqual(ds.keys(), list(ds._arrays))
        self.assertEqual(len(ds), 8)

        self.assertItemsEqual(ds.vars, ['var1', 'var2', 'var3'])
        self.assertItemsEqual(ds.vars.keys(), ['var1', 'var2', 'var3'])
        self.assertIn('var1', ds.vars)
        self.assertNotIn('dim1', ds.vars)
        self.assertNotIn('numbers', ds.vars)
        self.assertEqual(len(ds.vars), 3)

        self.assertItemsEqual(ds.indexes, ['dim1', 'dim2', 'dim3', 'time'])
        self.assertEqual(len(ds.indexes), 4)

        self.assertItemsEqual(ds.coords,
                              ['time', 'dim1', 'dim2', 'dim3', 'numbers'])
        self.assertIn('dim1', ds.coords)
        self.assertIn('numbers', ds.coords)
        self.assertNotIn('var1', ds.coords)
        self.assertEqual(len(ds.coords), 5)

    def test_variable(self):
        a = Dataset()
        d = np.random.random((10, 3))
        a['foo'] = (('time', 'x',), d)
        self.assertTrue('foo' in a._arrays)
        self.assertTrue('foo' in a)
        a['bar'] = (('time', 'x',), d)
        # order of creation is preserved
        self.assertEqual(list(a),  ['foo', 'time', 'x', 'bar'])
        self.assertTrue(all([a['foo'][i].values == d[i]
                             for i in np.ndindex(*d.shape)]))
        # try to add variable with dim (10,3) with data that's (3,10)
        with self.assertRaises(ValueError):
            a['qux'] = (('time', 'x'), d.T)

    def test_modify_inplace(self):
        a = Dataset()
        vec = np.random.random((10,))
        attributes = {'foo': 'bar'}
        a['x'] = ('x', vec, attributes)
        self.assertTrue('x' in a.coords)
        self.assertIsInstance(a.coords['x'].to_index(),
            pd.Index)
        self.assertVariableIdentical(a.coords['x'], a._arrays['x'])
        b = Dataset()
        b['x'] = ('x', vec, attributes)
        self.assertVariableIdentical(a['x'], b['x'])
        self.assertEqual(a.dims, b.dims)
        # this should work
        a['x'] = ('x', vec[:5])
        a['z'] = ('x', np.arange(5))
        with self.assertRaises(ValueError):
            # now it shouldn't, since there is a conflicting length
            a['x'] = ('x', vec[:4])
        arr = np.random.random((10, 1,))
        scal = np.array(0)
        with self.assertRaises(ValueError):
            a['y'] = ('y', arr)
        with self.assertRaises(ValueError):
            a['y'] = ('y', scal)
        self.assertTrue('y' not in a.dims)

    def test_coords_properties(self):
        # use an OrderedDict for coordinates to ensure order across python
        # versions
        data = Dataset(OrderedDict([('x', ('x', [-1, -2])),
                                    ('y', ('y', [0, 1, 2])),
                                    ('foo', (['x', 'y'],
                                             np.random.randn(2, 3)))]),
                       OrderedDict([('a', ('x', [4, 5])), ('b', -10)]))

        self.assertEqual(4, len(data.coords))

        self.assertItemsEqual(['x', 'y', 'a', 'b'], list(data.coords))

        self.assertVariableIdentical(data.coords['x'], data['x'].variable)
        self.assertVariableIdentical(data.coords['y'], data['y'].variable)

        self.assertIn('x', data.coords)
        self.assertIn('a', data.coords)
        self.assertNotIn(0, data.coords)
        self.assertNotIn('foo', data.coords)

        with self.assertRaises(KeyError):
            data.coords['foo']
        with self.assertRaises(KeyError):
            data.coords[0]

        expected = dedent("""\
        Coordinates:
          * x        (x) int64 -1 -2
          * y        (y) int64 0 1 2
            a        (x) int64 4 5
            b        int64 -10""")
        actual = repr(data.coords)
        self.assertEqual(expected, actual)

        self.assertEqual({'x': 2, 'y': 3}, data.coords.dims)

    def test_coords_modify(self):
        data = Dataset({'x': ('x', [-1, -2]),
                        'y': ('y', [0, 1, 2]),
                        'foo': (['x', 'y'], np.random.randn(2, 3))},
                       {'a': ('x', [4, 5]), 'b': -10})

        actual = data.copy(deep=True)
        actual.coords['x'] = ('x', ['a', 'b'])
        self.assertArrayEqual(actual['x'], ['a', 'b'])

        actual = data.copy(deep=True)
        actual.coords['z'] = ('z', ['a', 'b'])
        self.assertArrayEqual(actual['z'], ['a', 'b'])

        with self.assertRaisesRegexp(ValueError, 'conflicting sizes'):
            data.coords['x'] = ('x', [-1])

        actual = data.copy()
        del actual.coords['b']
        expected = data.reset_coords('b', drop=True)
        self.assertDatasetIdentical(expected, actual)

        with self.assertRaises(KeyError):
            del data.coords['not_found']

        with self.assertRaises(KeyError):
            del data.coords['foo']

    def test_coords_set(self):
        one_coord = Dataset({'x': ('x', [0]),
                             'yy': ('x', [1]),
                             'zzz': ('x', [2])})
        two_coords = Dataset({'zzz': ('x', [2])},
                             {'x': ('x', [0]),
                              'yy': ('x', [1])})
        all_coords = Dataset(coords={'x': ('x', [0]),
                                     'yy': ('x', [1]),
                                     'zzz': ('x', [2])})

        actual = one_coord.set_coords('x')
        self.assertDatasetIdentical(one_coord, actual)
        actual = one_coord.set_coords(['x'])
        self.assertDatasetIdentical(one_coord, actual)

        actual = one_coord.set_coords('yy')
        self.assertDatasetIdentical(two_coords, actual)

        actual = one_coord.set_coords(['yy', 'zzz'])
        self.assertDatasetIdentical(all_coords, actual)

        actual = one_coord.reset_coords()
        self.assertDatasetIdentical(one_coord, actual)
        actual = two_coords.reset_coords()
        self.assertDatasetIdentical(one_coord, actual)
        actual = all_coords.reset_coords()
        self.assertDatasetIdentical(one_coord, actual)

        actual = all_coords.reset_coords(['yy', 'zzz'])
        self.assertDatasetIdentical(one_coord, actual)
        actual = all_coords.reset_coords('zzz')
        self.assertDatasetIdentical(two_coords, actual)

        with self.assertRaisesRegexp(ValueError, 'cannot remove index'):
            one_coord.reset_coords('x')

        actual = all_coords.reset_coords('zzz', drop=True)
        expected = all_coords.drop_vars('zzz')
        self.assertDatasetIdentical(expected, actual)
        expected = two_coords.drop_vars('zzz')
        self.assertDatasetIdentical(expected, actual)

    def test_coords_to_dataset(self):
        orig = Dataset({'foo': ('y', [-1, 0, 1])}, {'x': 10, 'y': [2, 3, 4]})
        expected = Dataset(coords={'x': 10, 'y': [2, 3, 4]})
        actual = orig.coords.to_dataset()
        self.assertDatasetIdentical(expected, actual)

    def test_coords_merge(self):
        orig_coords = Dataset(coords={'a': ('x', [1, 2])}).coords
        other_coords = Dataset(coords={'b': ('x', ['a', 'b'])}).coords
        expected = Dataset(coords={'a': ('x', [1, 2]),
                                   'b': ('x', ['a', 'b'])})
        actual = orig_coords.merge(other_coords)
        self.assertDatasetIdentical(expected, actual)
        actual = other_coords.merge(orig_coords)
        self.assertDatasetIdentical(expected, actual)

        other_coords = Dataset(coords={'x': ('x', ['a', 'b'])}).coords
        with self.assertRaisesRegexp(ValueError, 'not aligned'):
            orig_coords.merge(other_coords)

        other_coords = Dataset(coords={'a': ('x', [8, 9])}).coords
        expected = Dataset(coords={'x': range(2)})
        actual = orig_coords.merge(other_coords)
        self.assertDatasetIdentical(expected, actual)
        actual = other_coords.merge(orig_coords)
        self.assertDatasetIdentical(expected, actual)

        other_coords = Dataset(coords={'x': np.nan}).coords
        actual = orig_coords.merge(other_coords)
        self.assertDatasetIdentical(orig_coords.to_dataset(), actual)
        actual = other_coords.merge(orig_coords)
        self.assertDatasetIdentical(orig_coords.to_dataset(), actual)

    def test_equals_and_identical(self):
        data = create_test_data(seed=42)
        self.assertTrue(data.equals(data))
        self.assertTrue(data.identical(data))

        data2 = create_test_data(seed=42)
        data2.attrs['foobar'] = 'baz'
        self.assertTrue(data.equals(data2))
        self.assertFalse(data.identical(data2))

        del data2['time']
        self.assertFalse(data.equals(data2))

        data = create_test_data(seed=42).rename({'var1': None})
        self.assertTrue(data.equals(data))
        self.assertTrue(data.identical(data))

        data2 = data.reset_coords()
        self.assertFalse(data2.equals(data))
        self.assertFalse(data2.identical(data))

    def test_attrs(self):
        data = create_test_data(seed=42)
        data.attrs = {'foobar': 'baz'}
        self.assertTrue(data.attrs['foobar'], 'baz')
        self.assertIsInstance(data.attrs, OrderedDict)

    def test_isel(self):
        data = create_test_data()
        slicers = {'dim1': slice(None, None, 2), 'dim2': slice(0, 2)}
        ret = data.isel(**slicers)

        # Verify that only the specified dimension was altered
        self.assertItemsEqual(data.dims, ret.dims)
        for d in data.dims:
            if d in slicers:
                self.assertEqual(ret.dims[d],
                                 np.arange(data.dims[d])[slicers[d]].size)
            else:
                self.assertEqual(data.dims[d], ret.dims[d])
        # Verify that the data is what we expect
        for v in data:
            self.assertEqual(data[v].dims, ret[v].dims)
            self.assertEqual(data[v].attrs, ret[v].attrs)
            slice_list = [slice(None)] * data[v].values.ndim
            for d, s in iteritems(slicers):
                if d in data[v].dims:
                    inds = np.nonzero(np.array(data[v].dims) == d)[0]
                    for ind in inds:
                        slice_list[ind] = s
            expected = data[v].values[slice_list]
            actual = ret[v].values
            np.testing.assert_array_equal(expected, actual)

        with self.assertRaises(ValueError):
            data.isel(not_a_dim=slice(0, 2))

        ret = data.isel(dim1=0)
        self.assertEqual({'time': 20, 'dim2': 9, 'dim3': 10}, ret.dims)
        self.assertItemsEqual(data.vars, ret.vars)
        self.assertItemsEqual(data.coords, ret.coords)
        self.assertItemsEqual(data.indexes, list(ret.indexes) + ['dim1'])

        ret = data.isel(time=slice(2), dim1=0, dim2=slice(5))
        self.assertEqual({'time': 2, 'dim2': 5, 'dim3': 10}, ret.dims)
        self.assertItemsEqual(data.vars, ret.vars)
        self.assertItemsEqual(data.coords, ret.coords)
        self.assertItemsEqual(data.indexes, list(ret.indexes) + ['dim1'])

        ret = data.isel(time=0, dim1=0, dim2=slice(5))
        self.assertItemsEqual({'dim2': 5, 'dim3': 10}, ret.dims)
        self.assertItemsEqual(data.vars, ret.vars)
        self.assertItemsEqual(data.coords, ret.coords)
        self.assertItemsEqual(data.indexes,
                              list(ret.indexes) + ['dim1', 'time'])

    def test_sel(self):
        data = create_test_data()
        int_slicers = {'dim1': slice(None, None, 2),
                       'dim2': slice(2),
                       'dim3': slice(3)}
        loc_slicers = {'dim1': slice(None, None, 2),
                       'dim2': slice(0, 0.5),
                       'dim3': slice('a', 'c')}
        self.assertDatasetEqual(data.isel(**int_slicers),
                                data.sel(**loc_slicers))
        data['time'] = ('time', pd.date_range('2000-01-01', periods=20))
        self.assertDatasetEqual(data.isel(time=0),
                                data.sel(time='2000-01-01'))
        self.assertDatasetEqual(data.isel(time=slice(10)),
                                data.sel(time=slice('2000-01-01',
                                                   '2000-01-10')))
        self.assertDatasetEqual(data, data.sel(time=slice('1999', '2005')))
        times = pd.date_range('2000-01-01', periods=3)
        self.assertDatasetEqual(data.isel(time=slice(3)),
                                data.sel(time=times))
        self.assertDatasetEqual(data.isel(time=slice(3)),
                                data.sel(time=(data['time.dayofyear'] <= 3)))

    def test_reindex_like(self):
        data = create_test_data()
        data['letters'] = ('dim3', 10 * ['a'])

        expected = data.isel(dim1=slice(10), time=slice(13))
        actual = data.reindex_like(expected)
        self.assertDatasetIdentical(actual, expected)

        expected = data.copy(deep=True)
        expected['dim3'] = ('dim3', list('cdefghijkl'))
        expected['var3'][:-2] = expected['var3'][2:]
        expected['var3'][-2:] = np.nan
        expected['letters'] = expected['letters'].astype(object)
        expected['letters'][-2:] = np.nan
        expected['numbers'] = expected['numbers'].astype(float)
        expected['numbers'][:-2] = expected['numbers'][2:].values
        expected['numbers'][-2:] = np.nan
        actual = data.reindex_like(expected)
        self.assertDatasetIdentical(actual, expected)

    def test_reindex(self):
        data = create_test_data()
        self.assertDatasetIdentical(data, data.reindex())

        expected = data.isel(dim1=slice(10))
        actual = data.reindex(dim1=data['dim1'][:10])
        self.assertDatasetIdentical(actual, expected)

        actual = data.reindex(dim1=data['dim1'][:10].values)
        self.assertDatasetIdentical(actual, expected)

        actual = data.reindex(dim1=data['dim1'][:10].to_index())
        self.assertDatasetIdentical(actual, expected)

    def test_align(self):
        left = create_test_data()
        right = left.copy(deep=True)
        right['dim3'] = ('dim3', list('cdefghijkl'))
        right['var3'][:-2] = right['var3'][2:]
        right['var3'][-2:] = np.random.randn(*right['var3'][-2:].shape)
        right['numbers'][:-2] = right['numbers'][2:]
        right['numbers'][-2:] = -10

        intersection = list('cdefghij')
        union = list('abcdefghijkl')

        left2, right2 = align(left, right, join='inner')
        self.assertArrayEqual(left2['dim3'], intersection)
        self.assertDatasetIdentical(left2, right2)

        left2, right2 = align(left, right, join='outer')
        self.assertVariableEqual(left2['dim3'], right2['dim3'])
        self.assertArrayEqual(left2['dim3'], union)
        self.assertDatasetIdentical(left2.sel(dim3=intersection),
                                    right2.sel(dim3=intersection))
        self.assertTrue(np.isnan(left2['var3'][-2:]).all())
        self.assertTrue(np.isnan(right2['var3'][:2]).all())

        left2, right2 = align(left, right, join='left')
        self.assertVariableEqual(left2['dim3'], right2['dim3'])
        self.assertVariableEqual(left2['dim3'], left['dim3'])
        self.assertDatasetIdentical(left2.sel(dim3=intersection),
                                    right2.sel(dim3=intersection))
        self.assertTrue(np.isnan(right2['var3'][:2]).all())

        left2, right2 = align(left, right, join='right')
        self.assertVariableEqual(left2['dim3'], right2['dim3'])
        self.assertVariableEqual(left2['dim3'], right['dim3'])
        self.assertDatasetIdentical(left2.sel(dim3=intersection),
                                    right2.sel(dim3=intersection))
        self.assertTrue(np.isnan(left2['var3'][-2:]).all())

    def test_variable_indexing(self):
        data = create_test_data()
        v = data['var1']
        d1 = data['dim1']
        d2 = data['dim2']
        self.assertVariableEqual(v, v[d1.values])
        self.assertVariableEqual(v, v[d1])
        self.assertVariableEqual(v[:3], v[d1 < 3])
        self.assertVariableEqual(v[:, 3:], v[:, d2 >= 1.5])
        self.assertVariableEqual(v[:3, 3:], v[d1 < 3, d2 >= 1.5])
        self.assertVariableEqual(v[:3, :2], v[range(3), range(2)])
        self.assertVariableEqual(v[:3, :2], v.loc[d1[:3], d2[:2]])

    def test_drop_vars(self):
        data = create_test_data()

        self.assertDatasetIdentical(data, data.drop_vars())

        expected = Dataset(dict((k, data[k]) for k in data if k != 'time'))
        actual = data.drop_vars('time')
        self.assertDatasetIdentical(expected, actual)

        expected = Dataset(dict((k, data[k]) for
                                k in ['dim2', 'dim3', 'time', 'numbers']))
        actual = data.drop_vars('dim1')
        self.assertDatasetIdentical(expected, actual)

        with self.assertRaisesRegexp(ValueError, 'cannot be found'):
            data.drop_vars('not_found_here')

    def test_copy(self):
        data = create_test_data()

        for copied in [data.copy(deep=False), copy(data)]:
            self.assertDatasetIdentical(data, copied)
            for k in data:
                v0 = data._arrays[k]
                v1 = copied._arrays[k]
                self.assertIs(v0, v1)
            copied['foo'] = ('z', np.arange(5))
            self.assertNotIn('foo', data)

        for copied in [data.copy(deep=True), deepcopy(data)]:
            self.assertDatasetIdentical(data, copied)
            for k in data:
                v0 = data._arrays[k]
                v1 = copied._arrays[k]
                self.assertIsNot(v0, v1)

    def test_rename(self):
        data = create_test_data()
        newnames = {'var1': 'renamed_var1', 'dim2': 'renamed_dim2'}
        renamed = data.rename(newnames)

        variables = OrderedDict(data._arrays)
        for k, v in iteritems(newnames):
            variables[v] = variables.pop(k)

        for k, v in iteritems(variables):
            dims = list(v.dims)
            for name, newname in iteritems(newnames):
                if name in dims:
                    dims[dims.index(name)] = newname

            self.assertVariableEqual(Variable(dims, v.values, v.attrs),
                                     renamed[k])
            self.assertEqual(v.encoding, renamed[k].encoding)
            self.assertEqual(type(v), type(renamed._arrays[k]))

        self.assertTrue('var1' not in renamed)
        self.assertTrue('dim2' not in renamed)

        with self.assertRaisesRegexp(ValueError, "cannot rename 'not_a_var'"):
            data.rename({'not_a_var': 'nada'})

        # verify that we can rename a variable without accessing the data
        var1 = data['var1']
        data['var1'] = (var1.dims, InaccessibleArray(var1.values))
        renamed = data.rename(newnames)
        with self.assertRaises(UnexpectedDataAccess):
            renamed['renamed_var1'].values

    def test_rename_inplace(self):
        times = pd.date_range('2000-01-01', periods=3)
        data = Dataset({'z': ('x', [2, 3, 4]), 't': ('t', times)})
        copied = data.copy()
        renamed = data.rename({'x': 'y'})
        data.rename({'x': 'y'}, inplace=True)
        self.assertDatasetIdentical(data, renamed)
        self.assertFalse(data.equals(copied))
        self.assertEquals(data.dims, {'y': 3, 't': 3})
        # check virtual variables
        self.assertArrayEqual(data['t.dayofyear'], [1, 2, 3])

    def test_update(self):
        data = create_test_data(seed=0)
        expected = data.copy()
        var2 = Variable('dim1', np.arange(8))
        actual = data.update({'var2': var2})
        expected['var2'] = var2
        self.assertDatasetIdentical(expected, actual)

        actual = data.copy()
        actual_result = actual.update(data, inplace=True)
        self.assertIs(actual_result, actual)
        self.assertDatasetIdentical(expected, actual)

        actual = data.update(data, inplace=False)
        expected = data
        self.assertIsNot(actual, expected)
        self.assertDatasetIdentical(expected, actual)

    def test_merge(self):
        data = create_test_data()
        ds1 = data[['var1']]
        ds2 = data[['var3']]
        expected = data[['var1', 'var3']]
        actual = ds1.merge(ds2)
        self.assertDatasetIdentical(expected, actual)

        actual = ds2.merge(ds1)
        self.assertDatasetIdentical(expected, actual)

        actual = data.merge(data)
        self.assertDatasetIdentical(data, actual)
        actual = data.reset_coords(drop=True).merge(data)
        self.assertDatasetIdentical(data, actual)
        actual = data.merge(data.reset_coords(drop=True))
        self.assertDatasetIdentical(data, actual)

        with self.assertRaises(ValueError):
            ds1.merge(ds2.isel(dim1=slice(2)))
        with self.assertRaises(ValueError):
            ds1.merge(ds2.rename({'var3': 'var1'}))
        with self.assertRaisesRegexp(ValueError, 'coordinates with these'):
            data.reset_coords().merge(data)
        with self.assertRaisesRegexp(ValueError, 'variables with these'):
            data.merge(data.reset_coords())

    def test_getitem(self):
        data = create_test_data()
        self.assertIsInstance(data['var1'], DataArray)
        self.assertVariableEqual(data['var1'], data._arrays['var1'])
        with self.assertRaises(KeyError):
            data['notfound']
        with self.assertRaises(KeyError):
            data[['var1', 'notfound']]

        actual = data[['var1', 'var2']]
        expected = Dataset({'var1': data['var1'], 'var2': data['var2']})
        self.assertDatasetEqual(expected, actual)

        actual = data['numbers']
        expected = DataArray(data['numbers'].variable, [data['dim3']],
                             name='numbers')
        self.assertDataArrayIdentical(expected, actual)

    def test_virtual_variables(self):
        # access virtual variables
        data = create_test_data()
        self.assertVariableEqual(data['time.dayofyear'],
                                 Variable('time', 1 + np.arange(20)))
        self.assertArrayEqual(data['time.month'].values,
                              data._arrays['time'].to_index().month)
        self.assertArrayEqual(data['time.season'].values, 1)
        # test virtual variable math
        self.assertArrayEqual(data['time.dayofyear'] + 1, 2 + np.arange(20))
        self.assertArrayEqual(np.sin(data['time.dayofyear']),
                              np.sin(1 + np.arange(20)))
        # ensure they become coordinates
        expected = Dataset({}, {'time.dayofyear': data['time.dayofyear']})
        actual = data[['time.dayofyear']]
        self.assertDatasetEqual(expected, actual)

    def test_slice_virtual_variable(self):
        data = create_test_data()
        self.assertVariableEqual(data['time.dayofyear'][:10],
                                 Variable(['time'], 1 + np.arange(10)))
        self.assertVariableEqual(data['time.dayofyear'][0], Variable([], 1))

    def test_setitem(self):
        # assign a variable
        var = Variable(['dim1'], np.random.randn(8))
        data1 = create_test_data()
        data1['A'] = var
        data2 = data1.copy()
        data2['A'] = var
        self.assertDatasetIdentical(data1, data2)
        # assign a dataset array
        dv = 2 * data2['A']
        data1['B'] = dv.variable
        data2['B'] = dv
        self.assertDatasetIdentical(data1, data2)
        # can't assign an ND array without dimensions
        with self.assertRaisesRegexp(ValueError,
                                     'dimensions .* must have the same len'):
            data2['C'] = var.values.reshape(2, 4)
        # but can assign a 1D array
        data1['C'] = var.values
        data2['C'] = ('C', var.values)
        self.assertDatasetIdentical(data1, data2)
        # can assign a scalar
        data1['scalar'] = 0
        data2['scalar'] = ([], 0)
        self.assertDatasetIdentical(data1, data2)
        # can't use the same dimension name as a scalar var
        with self.assertRaisesRegexp(ValueError, 'already exists as a scalar'):
            data1['newvar'] = ('scalar', [3, 4, 5])
        # can't resize a used dimension
        with self.assertRaisesRegexp(ValueError, 'conflicting sizes'):
            data1['dim1'] = data1['dim1'][:5]
        # override an existing value
        data1['A'] = 3 * data2['A']
        self.assertVariableEqual(data1['A'], 3 * data2['A'])

    def test_delitem(self):
        data = create_test_data()
        all_items = set(data)
        self.assertItemsEqual(data, all_items)
        del data['var1']
        self.assertItemsEqual(data, all_items - set(['var1']))
        del data['dim1']
        self.assertItemsEqual(data, set(['time', 'dim2', 'dim3', 'numbers']))
        self.assertNotIn('dim1', data.dims)
        self.assertNotIn('dim1', data.coords)

    def test_squeeze(self):
        data = Dataset({'foo': (['x', 'y', 'z'], [[[1], [2]]])})
        for args in [[], [['x']], [['x', 'z']]]:
            def get_args(v):
                return [set(args[0]) & set(v.dims)] if args else []
            expected = Dataset(dict((k, v.squeeze(*get_args(v)))
                                    for k, v in iteritems(data._arrays)))
            expected.set_coords(data.coords, inplace=True)
            self.assertDatasetIdentical(expected, data.squeeze(*args))
        # invalid squeeze
        with self.assertRaisesRegexp(ValueError, 'cannot select a dimension'):
            data.squeeze('y')

    def test_groupby(self):
        data = Dataset({'z': (['x', 'y'], np.random.randn(3, 5))},
                       {'x': ('x', list('abc')),
                        'c': ('x', [0, 1, 0])})
        groupby = data.groupby('x')
        self.assertEqual(len(groupby), 3)
        expected_groups = {'a': 0, 'b': 1, 'c': 2}
        self.assertEqual(groupby.groups, expected_groups)
        expected_items = [('a', data.isel(x=0)),
                          ('b', data.isel(x=1)),
                          ('c', data.isel(x=2))]
        for actual, expected in zip(groupby, expected_items):
            self.assertEqual(actual[0], expected[0])
            self.assertDatasetEqual(actual[1], expected[1])

        identity = lambda x: x
        for k in ['x', 'c', 'y']:
            actual = data.groupby(k, squeeze=False).apply(identity)
            self.assertDatasetEqual(data, actual)

    def test_groupby_returns_new_type(self):
        data = Dataset({'z': (['x', 'y'], np.random.randn(3, 5))})

        actual = data.groupby('x').apply(lambda ds: ds['z'])
        expected = data['z']
        self.assertDataArrayIdentical(expected, actual)

        actual = data['z'].groupby('x').apply(lambda x: x.to_dataset())
        expected = data
        self.assertDatasetIdentical(expected, actual)

    def test_groupby_iter(self):
        data = create_test_data()
        for n, (t, sub) in enumerate(list(data.groupby('dim1'))[:3]):
            self.assertEqual(data['dim1'][n], t)
            self.assertVariableEqual(data['var1'][n], sub['var1'])
            self.assertVariableEqual(data['var2'][n], sub['var2'])
            self.assertVariableEqual(data['var3'][:, n], sub['var3'])

    def test_groupby_errors(self):
        data = create_test_data()
        with self.assertRaisesRegexp(ValueError, 'must be 1 dimensional'):
            data.groupby('var1')
        with self.assertRaisesRegexp(ValueError, 'must have a name'):
            data.groupby(np.arange(10))
        with self.assertRaisesRegexp(ValueError, 'length does not match'):
            data.groupby(data['dim1'][:3])
        with self.assertRaisesRegexp(ValueError, "must have a 'dims'"):
            data.groupby(data.coords['dim1'].to_index())

    def test_groupby_reduce(self):
        data = Dataset({'xy': (['x', 'y'], np.random.randn(3, 4)),
                        'xonly': ('x', np.random.randn(3)),
                        'yonly': ('y', np.random.randn(4)),
                        'letters': ('y', ['a', 'a', 'b', 'b'])})

        expected = data.mean('y')
        actual = data.groupby('x').mean()
        self.assertDatasetAllClose(expected, actual)

        actual = data.groupby('x').mean('y')
        self.assertDatasetAllClose(expected, actual)

        letters = data['letters']
        expected = Dataset({'xy': data['xy'].groupby(letters).mean(),
                            'xonly': data['xonly'].mean(),
                            'yonly': data['yonly'].groupby(letters).mean()})
        actual = data.groupby('letters').mean()
        self.assertDatasetAllClose(expected, actual)

    def test_groupby_math(self):
        reorder_dims = lambda x: x.transpose('dim1', 'dim2', 'dim3', 'time')

        ds = create_test_data()
        for squeeze in [True, False]:
            grouped = ds.groupby('dim1', squeeze=squeeze)

            expected = reorder_dims(ds + ds.coords['dim1'])
            actual = grouped + ds.coords['dim1']
            self.assertDatasetIdentical(expected, reorder_dims(actual))

            actual = ds.coords['dim1'] + grouped
            self.assertDatasetIdentical(expected, reorder_dims(actual))

            ds2 = 2 * ds
            expected = reorder_dims(ds + ds2)
            actual = grouped + ds2
            self.assertDatasetIdentical(expected, reorder_dims(actual))

            actual = ds2 + grouped
            self.assertDatasetIdentical(expected, reorder_dims(actual))

        grouped = ds.groupby('numbers')
        zeros = DataArray([0, 0, 0, 0], [('numbers', range(4))])
        expected = ds
        actual = grouped + zeros
        self.assertDatasetEqual(expected, actual)

        actual = zeros + grouped
        self.assertDatasetEqual(expected, actual)

        with self.assertRaisesRegexp(TypeError, 'only support arithmetic'):
            grouped + 1
        with self.assertRaisesRegexp(TypeError, 'only support arithmetic'):
            grouped + grouped

    def test_groupby_math_virtual(self):
        ds = Dataset({'x': ('t', [1, 2, 3])},
                     {'t': pd.date_range('20100101', periods=3)})
        grouped = ds.groupby('t.day')
        actual = grouped - grouped.mean()
        expected = Dataset({'x': ('t', [0, 0, 0])},
                           {'t': ds['t'], 't.day': ds['t.day']})
        self.assertDatasetIdentical(actual, expected)

    def test_concat(self):
        data = create_test_data()

        split_data = [data.isel(dim1=slice(10)),
                      data.isel(dim1=slice(10, None))]
        self.assertDatasetIdentical(data, concat(split_data, 'dim1'))

        def rectify_dim_order(dataset):
            # return a new dataset with all variable dimensions tranposed into
            # the order in which they are found in `data`
            return Dataset(dict((k, v.transpose(*data[k].dims))
                                for k, v in iteritems(dataset.vars)),
                           dataset.coords, attrs=dataset.attrs)

        for dim in ['dim1', 'dim2', 'dim3']:
            datasets = [g for _, g in data.groupby(dim, squeeze=False)]
            self.assertDatasetIdentical(data, concat(datasets, dim))
            self.assertDatasetIdentical(
                data, concat(datasets, data[dim]))
            self.assertDatasetIdentical(
                data, concat(datasets, data[dim], mode='minimal'))

            datasets = [g for _, g in data.groupby(dim, squeeze=True)]
            concat_over = [k for k, v in iteritems(data)
                           if dim in v.dims and k != dim]
            actual = concat(datasets, data[dim], concat_over=concat_over)
            self.assertDatasetIdentical(data, rectify_dim_order(actual))

            actual = concat(datasets, data[dim], mode='different')
            self.assertDatasetIdentical(data, rectify_dim_order(actual))

        # Now add a new variable that doesn't depend on any of the current
        # dims and make sure the mode argument behaves as expected
        data['var4'] = ('dim4', np.arange(data.dims['dim3']))
        for dim in ['dim1', 'dim2', 'dim3']:
            datasets = [g for _, g in data.groupby(dim, squeeze=False)]
            actual = concat(datasets, data[dim], mode='all')
            expected = np.array([data['var4'].values
                                 for _ in range(data.dims[dim])])
            self.assertArrayEqual(actual['var4'].values, expected)

            actual = concat(datasets, data[dim], mode='different')
            self.assertDataArrayEqual(data['var4'], actual['var4'])
            actual = concat(datasets, data[dim], mode='minimal')
            self.assertDataArrayEqual(data['var4'], actual['var4'])

        # verify that the dim argument takes precedence over
        # concatenating dataset variables of the same name
        dim = (2 * data['dim1']).rename('dim1')
        datasets = [g for _, g in data.groupby('dim1', squeeze=False)]
        expected = data.copy()
        expected['dim1'] = dim
        self.assertDatasetIdentical(expected, concat(datasets, dim))

    def test_concat_errors(self):
        data = create_test_data()
        split_data = [data.isel(dim1=slice(10)),
                      data.isel(dim1=slice(10, None))]

        with self.assertRaisesRegexp(ValueError, 'must supply at least one'):
            concat([], 'dim1')

        with self.assertRaisesRegexp(ValueError, 'not all elements in'):
            concat(split_data, 'dim1', concat_over=['not_found'])

        with self.assertRaisesRegexp(ValueError, 'global attributes not'):
            data0, data1 = deepcopy(split_data)
            data1.attrs['foo'] = 'bar'
            concat([data0, data1], 'dim1', compat='identical')
        self.assertDatasetIdentical(
            data, concat([data0, data1], 'dim1', compat='equals'))

        with self.assertRaisesRegexp(ValueError, 'encountered unexpected'):
            data0, data1 = deepcopy(split_data)
            data1['foo'] = ('bar', np.random.randn(10))
            concat([data0, data1], 'dim1')

        with self.assertRaisesRegexp(ValueError, 'not equal across datasets'):
            data0, data1 = deepcopy(split_data)
            data1['dim2'] = 2 * data1['dim2']
            concat([data0, data1], 'dim1')

    def test_to_and_from_dataframe(self):
        x = np.random.randn(10)
        y = np.random.randn(10)
        t = list('abcdefghij')
        ds = Dataset(OrderedDict([('a', ('t', x)),
                                  ('b', ('t', y)),
                                  ('t', ('t', t))]))
        expected = pd.DataFrame(np.array([x, y]).T, columns=['a', 'b'],
                                index=pd.Index(t, name='t'))
        actual = ds.to_dataframe()
        # use the .equals method to check all DataFrame metadata
        assert expected.equals(actual), (expected, actual)

        # verify coords are included
        actual = ds.set_coords('b').to_dataframe()
        assert expected.equals(actual), (expected, actual)

        # check roundtrip
        self.assertDatasetIdentical(ds, Dataset.from_dataframe(actual))

        # test a case with a MultiIndex
        w = np.random.randn(2, 3)
        ds = Dataset({'w': (('x', 'y'), w)})
        ds['y'] = ('y', list('abc'))
        exp_index = pd.MultiIndex.from_arrays(
            [[0, 0, 0, 1, 1, 1], ['a', 'b', 'c', 'a', 'b', 'c']],
            names=['x', 'y'])
        expected = pd.DataFrame(w.reshape(-1), columns=['w'], index=exp_index)
        actual = ds.to_dataframe()
        self.assertTrue(expected.equals(actual))

        # check roundtrip
        self.assertDatasetIdentical(ds, Dataset.from_dataframe(actual))

        # check pathological cases
        df = pd.DataFrame([1])
        actual = Dataset.from_dataframe(df)
        expected = Dataset({0: ('index', [1])})
        self.assertDatasetIdentical(expected, actual)

        df = pd.DataFrame()
        actual = Dataset.from_dataframe(df)
        expected = Dataset()
        self.assertDatasetIdentical(expected, actual)

    def test_pickle(self):
        data = create_test_data()
        roundtripped = pickle.loads(pickle.dumps(data))
        self.assertDatasetIdentical(data, roundtripped)
        # regression test for #167:
        self.assertEqual(data.dims, roundtripped.dims)

    def test_lazy_load(self):
        store = InaccessibleVariableDataStore()
        create_test_data().dump_to_store(store)

        for decode_cf in [False, True]:
            ds = Dataset.load_store(store, decode_cf=decode_cf)
            with self.assertRaises(UnexpectedDataAccess):
                ds.load_data()
            with self.assertRaises(UnexpectedDataAccess):
                ds['var1'].values

            # these should not raise UnexpectedDataAccess:
            ds.isel(time=10)
            ds.isel(time=slice(10), dim1=[0]).isel(dim1=0, dim2=-1)

    def test_reduce(self):
        data = create_test_data()

        self.assertEqual(len(data.mean().coords), 0)

        actual = data.max()
        expected = Dataset(dict((k, v.max())
                                for k, v in iteritems(data.vars)))
        self.assertDatasetEqual(expected, actual)

        self.assertDatasetEqual(data.min(dim=['dim1']),
                                data.min(dim='dim1'))

        for reduct, expected in [('dim2', ['dim1', 'dim3', 'time']),
                                 (['dim2', 'time'], ['dim1', 'dim3']),
                                 (('dim2', 'time'), ['dim1', 'dim3']),
                                 ((), ['dim1', 'dim2', 'dim3', 'time'])]:
            actual = data.min(dim=reduct).dims
            print(reduct, actual, expected)
            self.assertItemsEqual(actual, expected)

        self.assertDatasetEqual(data.mean(dim=[]), data)

    def test_reduce_bad_dim(self):
        data = create_test_data()
        with self.assertRaisesRegexp(ValueError, 'Dataset does not contain'):
            ds = data.mean(dim='bad_dim')

    def test_reduce_non_numeric(self):
        data1 = create_test_data(seed=44)
        data2 = create_test_data(seed=44)
        add_vars = {'var4': ['dim1', 'dim2']}
        for v, dims in sorted(add_vars.items()):
            size = tuple(data1.dims[d] for d in dims)
            data = np.random.random_integers(0, 100, size=size).astype(np.str_)
            data1[v] = (dims, data, {'foo': 'variable'})

        self.assertTrue('var4' not in data1.mean())
        self.assertDatasetEqual(data1.mean(), data2.mean())
        self.assertDatasetEqual(data1.mean(dim='dim1'),
                                data2.mean(dim='dim1'))

    def test_reduce_keep_attrs(self):
        data = create_test_data()
        _attrs = {'attr1': 'value1', 'attr2': 2929}

        attrs = OrderedDict(_attrs)
        data.attrs = attrs

        # Test dropped attrs
        ds = data.mean()
        self.assertEqual(len(ds.attrs), 0)
        self.assertEqual(ds.attrs, OrderedDict())

        # Test kept attrs
        ds = data.mean(keep_attrs=True)
        self.assertEqual(len(ds.attrs), len(_attrs))
        self.assertTrue(ds.attrs, attrs)

    def test_reduce_argmin(self):
        # regression test for #205
        ds = Dataset({'a': ('x', [0, 1])})
        expected = Dataset({'a': ([], 0)})
        actual = ds.argmin()
        self.assertDatasetIdentical(expected, actual)

        actual = ds.argmin('x')
        self.assertDatasetIdentical(expected, actual)

    @unittest.skip('see github issue 209')
    def test_reduce_only_one_axis(self):

        def mean_only_one_axis(x, axis):
            if not isinstance(axis, (int, np.integer)):
                raise TypeError('non-integer axis')
            return x.mean(axis)

        ds = Dataset({'a': (['x', 'y'], [[0, 1, 2, 3, 4]])})
        expected = Dataset({'a': ('x', [2])})
        actual = ds.reduce(mean_only_one_axis, 'y')
        self.assertDatasetIdentical(expected, actual)

        with self.assertRaisesRegexp(TypeError, 'non-integer axis'):
            ds.reduce(mean_only_one_axis)

        with self.assertRaisesRegexp(TypeError, 'non-integer axis'):
            ds.reduce(mean_only_one_axis, ['x', 'y'])

    def test_apply(self):
        data = create_test_data()
        data.attrs['foo'] = 'bar'

        self.assertDatasetIdentical(data.apply(np.mean), data.mean())
        self.assertDatasetIdentical(data.apply(np.mean, keep_attrs=True),
                                    data.mean(keep_attrs=True))

        self.assertDatasetIdentical(data.apply(lambda x: x, keep_attrs=True),
                                    data.drop_vars('time'))

        def scale(x, multiple=1):
            return multiple * x

        actual = data.apply(scale, multiple=2)
        self.assertDataArrayEqual(actual['var1'], 2 * data['var1'])
        self.assertDataArrayIdentical(actual['numbers'], data['numbers'])

    def make_example_math_dataset(self):
        variables = OrderedDict(
            [('bar', ('x', np.arange(100, 400, 100))),
             ('foo', (('x', 'y'), 1.0 * np.arange(12).reshape(3, 4)))])
        coords = {'abc': ('x', ['a', 'b', 'c']),
                  'y': 10 * np.arange(4)}
        ds = Dataset(variables, coords)
        ds['foo'][0, 0] = np.nan
        return ds

    def test_dataset_number_math(self):
        ds = self.make_example_math_dataset()

        self.assertDatasetIdentical(ds, +ds)
        self.assertDatasetIdentical(ds, ds + 0)
        self.assertDatasetIdentical(ds, 0 + ds)
        self.assertDatasetIdentical(ds, ds + np.array(0))
        self.assertDatasetIdentical(ds, np.array(0) + ds)

        actual = ds.copy(deep=True)
        actual += 0
        self.assertDatasetIdentical(ds, actual)

    def test_unary_ops(self):
        ds = self.make_example_math_dataset()

        self.assertDatasetIdentical(ds.apply(abs), abs(ds))
        self.assertDatasetIdentical(ds.apply(lambda x: x + 4), ds + 4)

        for func in [lambda x: x.isnull(),
                     lambda x: x.round(),
                     lambda x: x.astype(int)]:
            self.assertDatasetIdentical(ds.apply(func), func(ds))

        self.assertDatasetIdentical(ds.isnull(), ~ds.notnull())

        # don't actually patch these methods in
        with self.assertRaises(AttributeError):
            ds.item
        with self.assertRaises(AttributeError):
            ds.searchsorted

    def test_dataset_array_math(self):
        ds = self.make_example_math_dataset()

        expected = ds.apply(lambda x: x + ds['foo'])
        self.assertDatasetIdentical(expected, ds + ds['foo'])
        self.assertDatasetIdentical(expected, ds['foo'] + ds)
        self.assertDatasetIdentical(expected, ds + ds['foo'].variable)
        self.assertDatasetIdentical(expected, ds['foo'].variable + ds)
        with self.assertRaisesRegexp(ValueError, 'dimensions cannot change'):
            ds += ds['foo']

        expected = ds.apply(lambda x: x + ds['bar'])
        self.assertDatasetIdentical(expected, ds + ds['bar'])
        actual = ds.copy(deep=True)
        actual += ds['bar']
        self.assertDatasetIdentical(expected, actual)

        expected = Dataset({'bar': ds['bar'] + np.arange(3)})
        self.assertDatasetIdentical(expected, ds[['bar']] + np.arange(3))
        self.assertDatasetIdentical(expected, np.arange(3) + ds[['bar']])

    def test_dataset_dataset_math(self):
        ds = self.make_example_math_dataset()

        self.assertDatasetIdentical(ds, ds + 0 * ds)
        self.assertDatasetIdentical(ds, ds + {'foo': 0, 'bar': 0})

        expected = ds.apply(lambda x: 2 * x)
        self.assertDatasetIdentical(expected, 2 * ds)
        self.assertDatasetIdentical(expected, ds + ds)
        self.assertDatasetIdentical(expected, ds + ds.vars)
        self.assertDatasetIdentical(expected, ds + dict(ds.vars))

        actual = ds.copy(deep=True)
        actual += ds
        self.assertDatasetIdentical(expected, actual)

        self.assertDatasetIdentical(ds == ds, ds.notnull())

    def test_dataset_math_errors(self):
        ds = self.make_example_math_dataset()

        with self.assertRaises(TypeError):
            ds['foo'] += ds
        with self.assertRaises(TypeError):
            ds['foo'].variable += ds
        with self.assertRaisesRegexp(ValueError, 'do not have the same'):
            ds + ds[['bar']]

        # verify we can rollback in-place operations if something goes wrong
        # nb. inplace datetime64 math actually will work with an integer array
        # but not floats thanks to numpy's inconsistent handling
        other = DataArray(np.datetime64('2000-01-01T12'), coords={'c': 2})
        actual = ds.copy(deep=True)
        with self.assertRaises(TypeError):
            actual += other
        self.assertDatasetIdentical(actual, ds)

    def test_dataset_transpose(self):
        ds = Dataset({'a': (('x', 'y'), np.random.randn(3, 4)),
                      'b': (('y', 'x'), np.random.randn(4, 3))})

        actual = ds.transpose()
        expected = ds.apply(lambda x: x.transpose())
        self.assertDatasetIdentical(expected, actual)

        actual = ds.T
        self.assertDatasetIdentical(expected, actual)

        actual = ds.transpose('x', 'y')
        expected = ds.apply(lambda x: x.transpose('x', 'y'))
        self.assertDatasetIdentical(expected, actual)

        ds = create_test_data()
        actual = ds.transpose()
        for k in ds:
            self.assertEqual(actual[k].dims[::-1], ds[k].dims)

        new_order = ('dim2', 'dim3', 'dim1', 'time')
        actual = ds.transpose(*new_order)
        for k in ds:
            expected_dims = tuple(d for d in new_order if d in ds[k].dims)
            self.assertEqual(actual[k].dims, expected_dims)

        with self.assertRaisesRegexp(ValueError, 'arguments to transpose'):
            ds.transpose('dim1', 'dim2', 'dim3')
        with self.assertRaisesRegexp(ValueError, 'arguments to transpose'):
            ds.transpose('dim1', 'dim2', 'dim3', 'time', 'extra_dim')
