import numpy as np
import pandas as pd
from copy import deepcopy
from textwrap import dedent

from xray import concat, Dataset, DataArray, Coordinate, Variable, align
from xray.core.pycompat import iteritems, OrderedDict
from . import TestCase, ReturnItem, source_ndarray, unittest


class TestDataArray(TestCase):
    def setUp(self):
        self.attrs = {'attr1': 'value1', 'attr2': 2929}
        self.x = np.random.random((10, 20))
        self.v = Variable(['x', 'y'], self.x)
        self.va = Variable(['x', 'y'], self.x, self.attrs)
        self.ds = Dataset({'foo': self.v})
        self.dv = self.ds['foo']

    def test_repr(self):
        v = Variable(['time', 'x'], [[1, 2, 3], [4, 5, 6]], {'foo': 'bar'})
        data_array = DataArray(v, {'other': ([], 0)}, name='my_variable')
        expected = dedent("""\
        <xray.DataArray 'my_variable' (time: 2, x: 3)>
        array([[1, 2, 3],
               [4, 5, 6]])
        Coordinates:
            other    int64 0
          * time     (time) int64 0 1
          * x        (x) int64 0 1 2
        Attributes:
            foo: bar""")
        self.assertEqual(expected, repr(data_array))

    def test_properties(self):
        self.assertVariableEqual(self.dv.variable, self.v)
        self.assertArrayEqual(self.dv.values, self.v.values)
        for attr in ['dims', 'dtype', 'shape', 'size', 'ndim', 'attrs']:
            self.assertEqual(getattr(self.dv, attr), getattr(self.v, attr))
        self.assertEqual(len(self.dv), len(self.v))
        self.assertVariableEqual(self.dv, self.v)
        self.assertItemsEqual(list(self.dv.coords), list(self.ds.coords))
        for k, v in iteritems(self.dv.coords):
            self.assertArrayEqual(v, self.ds.coords[k])
        with self.assertRaises(AttributeError):
            self.dv.dataset = self.ds
        self.assertIsInstance(self.ds['x'].to_index(), pd.Index)
        with self.assertRaisesRegexp(ValueError, 'must be 1-dimensional'):
            self.ds['foo'].to_index()
        with self.assertRaises(AttributeError):
            self.dv.variable = self.v

    def test_name(self):
        arr = self.dv
        self.assertEqual(arr.name, 'foo')

        copied = arr.copy()
        arr.name = 'bar'
        self.assertEqual(arr.name, 'bar')
        self.assertDataArrayEqual(copied, arr)

        actual = DataArray(Coordinate('x', [3]))
        actual.name = 'y'
        expected = DataArray(Coordinate('y', [3]))
        self.assertDataArrayIdentical(actual, expected)

    def test_dims(self):
        arr = self.dv
        self.assertEqual(arr.dims, ('x', 'y'))

        arr.dims = ('w', 'z')
        self.assertEqual(arr.dims, ('w', 'z'))

        x = Dataset({'x': ('x', np.arange(5))})['x']
        x.dims = ('y',)
        self.assertEqual(x.dims, ('y',))
        self.assertEqual(x.name, 'y')

    def test_encoding(self):
        expected = {'foo': 'bar'}
        self.dv.encoding['foo'] = 'bar'
        self.assertEquals(expected, self.dv.encoding)

        expected = {'baz': 0}
        self.dv.encoding = expected
        self.assertEquals(expected, self.dv.encoding)
        self.assertIsNot(expected, self.dv.encoding)

    def test_constructor(self):
        data = np.random.random((2, 3))

        actual = DataArray(data)
        expected = Dataset({None: (['dim_0', 'dim_1'], data)})[None]
        self.assertDataArrayIdentical(expected, actual)

        actual = DataArray(data, [['a', 'b'], [-1, -2, -3]])
        expected = Dataset({None: (['dim_0', 'dim_1'], data),
                            'dim_0': ('dim_0', ['a', 'b']),
                            'dim_1': ('dim_1', [-1, -2, -3])})[None]
        self.assertDataArrayIdentical(expected, actual)

        actual = DataArray(data, [pd.Index(['a', 'b'], name='x'),
                                  pd.Index([-1, -2, -3], name='y')])
        expected = Dataset({None: (['x', 'y'], data),
                            'x': ('x', ['a', 'b']),
                            'y': ('y', [-1, -2, -3])})[None]
        self.assertDataArrayIdentical(expected, actual)

        coords = [['a', 'b'], [-1, -2, -3]]
        actual = DataArray(data, coords, ['x', 'y'])
        self.assertDataArrayIdentical(expected, actual)

        coords = [pd.Index(['a', 'b'], name='A'),
                  pd.Index([-1, -2, -3], name='B')]
        actual = DataArray(data, coords, ['x', 'y'])
        self.assertDataArrayIdentical(expected, actual)

        coords = {'x': ['a', 'b'], 'y': [-1, -2, -3]}
        actual = DataArray(data, coords, ['x', 'y'])
        self.assertDataArrayIdentical(expected, actual)

        coords = [('x', ['a', 'b']), ('y', [-1, -2, -3])]
        actual = DataArray(data, coords)
        self.assertDataArrayIdentical(expected, actual)

        actual = DataArray(data, OrderedDict(coords))
        self.assertDataArrayIdentical(expected, actual)

        expected = Dataset({None: (['x', 'y'], data),
                            'x': ('x', ['a', 'b'])})[None]
        actual = DataArray(data, {'x': ['a', 'b']}, ['x', 'y'])
        self.assertDataArrayIdentical(expected, actual)

        actual = DataArray(data, dims=['x', 'y'])
        expected = Dataset({None: (['x', 'y'], data)})[None]
        self.assertDataArrayIdentical(expected, actual)

        actual = DataArray(data, dims=['x', 'y'], name='foo')
        expected = Dataset({'foo': (['x', 'y'], data)})['foo']
        self.assertDataArrayIdentical(expected, actual)

        actual = DataArray(data, name='foo')
        expected = Dataset({'foo': (['dim_0', 'dim_1'], data)})['foo']
        self.assertDataArrayIdentical(expected, actual)

        actual = DataArray(data, dims=['x', 'y'], attrs={'bar': 2})
        expected = Dataset({None: (['x', 'y'], data, {'bar': 2})})[None]
        self.assertDataArrayIdentical(expected, actual)

        actual = DataArray(data, dims=['x', 'y'], encoding={'bar': 2})
        expected = Dataset({None: (['x', 'y'], data, {}, {'bar': 2})})[None]
        self.assertDataArrayIdentical(expected, actual)

    def test_constructor_invalid(self):
        data = np.random.randn(3, 2)

        with self.assertRaisesRegexp(ValueError, 'coords is not dict-like'):
            DataArray(data, [[0, 1, 2]], ['x', 'y'])

        with self.assertRaisesRegexp(ValueError, 'not a subset of the .* dim'):
            DataArray(data, {'x': [0, 1, 2]}, ['a', 'b'])
        with self.assertRaisesRegexp(ValueError, 'not a subset of the .* dim'):
            DataArray(data, {'x': [0, 1, 2]})

        with self.assertRaisesRegexp(TypeError, 'is not a string'):
            DataArray(data, dims=['x', None])

    def test_constructor_from_self_described(self):
        data = [[-0.1, 21], [0, 2]]
        expected = DataArray(data,
                             coords={'x': ['a', 'b'], 'y': [-1, -2]},
                             dims=['x', 'y'], name='foobar',
                             attrs={'bar': 2}, encoding={'foo': 3})
        actual = DataArray(expected)
        self.assertDataArrayIdentical(expected, actual)

        actual = DataArray(expected.values, actual.coords)
        self.assertDataArrayEqual(expected, actual)

        frame = pd.DataFrame(data, index=pd.Index(['a', 'b'], name='x'),
                             columns=pd.Index([-1, -2], name='y'))
        actual = DataArray(frame)
        self.assertDataArrayEqual(expected, actual)

        series = pd.Series(data[0], index=pd.Index([-1, -2], name='y'))
        actual = DataArray(series)
        self.assertDataArrayEqual(expected[0].reset_coords('x', drop=True),
                                  actual)

        panel = pd.Panel({0: frame})
        actual = DataArray(panel)
        expected = DataArray([data], expected.coords, ['dim_0', 'x', 'y'])
        self.assertDataArrayIdentical(expected, actual)

        expected = DataArray(data,
                             coords={'x': ['a', 'b'], 'y': [-1, -2],
                                     'a': 0, 'z': ('x', [-0.5, 0.5])},
                             dims=['x', 'y'])
        actual = DataArray(expected)
        self.assertDataArrayIdentical(expected, actual)

        actual = DataArray(expected.values, expected.coords)
        self.assertDataArrayIdentical(expected, actual)

        expected = Dataset({'foo': ('foo', ['a', 'b'])})['foo']
        actual = DataArray(pd.Index(['a', 'b'], name='foo'))
        self.assertDataArrayIdentical(expected, actual)

        actual = DataArray(Coordinate('foo', ['a', 'b']))
        self.assertDataArrayIdentical(expected, actual)

        s = pd.Series(range(2), pd.MultiIndex.from_product([['a', 'b'], [0]]))
        with self.assertRaisesRegexp(NotImplementedError, 'MultiIndex'):
            DataArray(s)

    def test_constructor_from_0d(self):
        expected = Dataset({None: ([], 0)})[None]
        actual = DataArray(0)
        self.assertDataArrayIdentical(expected, actual)

    def test_equals_and_identical(self):
        orig = DataArray(np.arange(5.0), {'a': 42}, dims='x')

        expected = orig
        actual = orig.copy()
        self.assertTrue(expected.equals(actual))
        self.assertTrue(expected.identical(actual))

        actual = expected.rename('baz')
        self.assertTrue(expected.equals(actual))
        self.assertFalse(expected.identical(actual))

        actual = expected.rename({'x': 'xxx'})
        self.assertFalse(expected.equals(actual))
        self.assertFalse(expected.identical(actual))

        actual = expected.copy()
        actual.attrs['foo'] = 'bar'
        self.assertTrue(expected.equals(actual))
        self.assertFalse(expected.identical(actual))

        actual = expected.copy()
        actual['x'] = ('x', -np.arange(5))
        self.assertFalse(expected.equals(actual))
        self.assertFalse(expected.identical(actual))

        actual = expected.reset_coords(drop=True)
        self.assertFalse(expected.equals(actual))
        self.assertFalse(expected.identical(actual))

        actual = orig.copy()
        actual[0] = np.nan
        expected = actual.copy()
        self.assertTrue(expected.equals(actual))
        self.assertTrue(expected.identical(actual))

        actual[:] = np.nan
        self.assertFalse(expected.equals(actual))
        self.assertFalse(expected.identical(actual))

        actual = expected.copy()
        actual['a'] = 100000
        self.assertFalse(expected.equals(actual))
        self.assertFalse(expected.identical(actual))

    def test_getitem(self):
        # strings pull out dataarrays
        self.assertDataArrayIdentical(self.dv, self.ds['foo'])
        x = self.dv['x']
        y = self.dv['y']
        self.assertDataArrayIdentical(self.ds['x'], x)
        self.assertDataArrayIdentical(self.ds['y'], y)

        I = ReturnItem()
        for i in [I[:], I[...], I[x.values], I[x.variable], I[x], I[x, y],
                  I[x.values > -1], I[x.variable > -1], I[x > -1],
                  I[x > -1, y > -1]]:
            self.assertVariableEqual(self.dv, self.dv[i])
        for i in [I[0], I[:, 0], I[:3, :2],
                  I[x.values[:3]], I[x.variable[:3]], I[x[:3]], I[x[:3], y[:4]],
                  I[x.values > 3], I[x.variable > 3], I[x > 3], I[x > 3, y > 3]]:
            self.assertVariableEqual(self.v[i], self.dv[i])

    def test_getitem_coords(self):
        orig = DataArray([[10], [20]],
                         {'x': [1, 2], 'y': [3], 'z': 4,
                          'x2': ('x', ['a', 'b']),
                          'y2': ('y', ['c']),
                          'xy': (['y', 'x'], [['d', 'e']])},
                         dims=['x', 'y'])

        self.assertDataArrayIdentical(orig, orig[:])
        self.assertDataArrayIdentical(orig, orig[:, :])
        self.assertDataArrayIdentical(orig, orig[...])
        self.assertDataArrayIdentical(orig, orig[:2, :1])
        self.assertDataArrayIdentical(orig, orig[[0, 1], [0]])

        actual = orig[0, 0]
        expected = DataArray(
            10, {'x': 1, 'y': 3, 'z': 4, 'x2': 'a', 'y2': 'c', 'xy': 'd'})
        self.assertDataArrayIdentical(expected, actual)

        actual = orig[0, :]
        expected = DataArray(
            [10], {'x': 1, 'y': [3], 'z': 4, 'x2': 'a', 'y2': ('y', ['c']),
                   'xy': ('y', ['d'])},
            dims='y')
        self.assertDataArrayIdentical(expected, actual)

        actual = orig[:, 0]
        expected = DataArray(
            [10, 20], {'x': [1, 2], 'y': 3, 'z': 4, 'x2': ('x', ['a', 'b']),
                       'y2': 'c', 'xy': ('x', ['d', 'e'])},
            dims='x')
        self.assertDataArrayIdentical(expected, actual)

    def test_isel(self):
        self.assertDatasetIdentical(self.dv[0].to_dataset(), self.ds.isel(x=0))
        self.assertDatasetIdentical(self.dv[:3, :5].to_dataset(),
                                    self.ds.isel(x=slice(3), y=slice(5)))
        self.assertDataArrayIdentical(self.dv, self.dv.isel(x=slice(None)))
        self.assertDataArrayIdentical(self.dv[:3], self.dv.isel(x=slice(3)))

    def test_sel(self):
        self.ds['x'] = ('x', np.array(list('abcdefghij')))
        da = self.ds['foo']
        self.assertDataArrayIdentical(da, da.sel(x=slice(None)))
        self.assertDataArrayIdentical(da[1], da.sel(x='b'))
        self.assertDataArrayIdentical(da[:3], da.sel(x=slice('c')))
        self.assertDataArrayIdentical(da[:3], da.sel(x=['a', 'b', 'c']))
        self.assertDataArrayIdentical(da[:, :4], da.sel(y=(self.ds['y'] < 4)))

    def test_loc(self):
        self.ds['x'] = ('x', np.array(list('abcdefghij')))
        da = self.ds['foo']
        self.assertDataArrayIdentical(da[:3], da.loc[:'c'])
        self.assertDataArrayIdentical(da[1], da.loc['b'])
        self.assertDataArrayIdentical(da[:3], da.loc[['a', 'b', 'c']])
        self.assertDataArrayIdentical(da[:3, :4],
                                      da.loc[['a', 'b', 'c'], np.arange(4)])
        self.assertDataArrayIdentical(da[:, :4], da.loc[:, self.ds['y'] < 4])
        da.loc['a':'j'] = 0
        self.assertTrue(np.all(da.values == 0))

    def test_loc_single_boolean(self):
        data = DataArray([0, 1], coords=[[True, False]])
        self.assertEqual(data.loc[True], 0)
        self.assertEqual(data.loc[False], 1)

    def test_time_components(self):
        dates = pd.date_range('2000-01-01', periods=10)
        da = DataArray(np.arange(1, 11), [('time', dates)])

        self.assertArrayEqual(da['time.dayofyear'], da.values)
        self.assertArrayEqual(da.coords['time.dayofyear'], da.values)

    def test_coords(self):
        coords = [Coordinate('x', [-1, -2]), Coordinate('y', [0, 1, 2])]
        da = DataArray(np.random.randn(2, 3), coords, name='foo')

        self.assertEquals(2, len(da.coords))

        self.assertEqual(['x', 'y'], list(da.coords))

        self.assertTrue(coords[0].identical(da.coords['x']))
        self.assertTrue(coords[1].identical(da.coords['y']))

        self.assertIn('x', da.coords)
        self.assertNotIn(0, da.coords)
        self.assertNotIn('foo', da.coords)

        with self.assertRaises(KeyError):
            da.coords[0]
        with self.assertRaises(KeyError):
            da.coords['foo']

        expected = dedent("""\
        Coordinates:
          * x        (x) int64 -1 -2
          * y        (y) int64 0 1 2""")
        actual = repr(da.coords)
        self.assertEquals(expected, actual)

    def test_coord_coords(self):
        orig = DataArray([10, 20],
                         {'x': [1, 2], 'x2': ('x', ['a', 'b']), 'z': 4},
                         dims='x')

        actual = orig.coords['x']
        expected = DataArray([1, 2], {'z': 4, 'x2': ('x', ['a', 'b'])},
                             dims='x', name='x')
        self.assertDataArrayIdentical(expected, actual)

        del actual.coords['x2']
        self.assertDataArrayIdentical(
            expected.reset_coords('x2', drop=True), actual)

        actual.coords['x3'] = ('x', ['a', 'b'])
        expected = DataArray([1, 2], {'z': 4, 'x3': ('x', ['a', 'b'])},
                             dims='x', name='x')
        self.assertDataArrayIdentical(expected, actual)

    def test_reset_coords(self):
        data = DataArray(np.zeros((3, 4)),
                         {'bar': ('x', ['a', 'b', 'c']),
                          'baz': ('y', range(4))},
                         dims=['x', 'y'],
                         name='foo')

        actual = data.reset_coords()
        expected = Dataset({'foo': (['x', 'y'], np.zeros((3, 4))),
                            'bar': ('x', ['a', 'b', 'c']),
                            'baz': ('y', range(4))})
        self.assertDatasetIdentical(actual, expected)

        actual = data.reset_coords(['bar', 'baz'])
        self.assertDatasetIdentical(actual, expected)

        actual = data.reset_coords('bar')
        expected = Dataset({'foo': (['x', 'y'], np.zeros((3, 4))),
                            'bar': ('x', ['a', 'b', 'c'])},
                           {'baz': ('y', range(4))})
        self.assertDatasetIdentical(actual, expected)

        actual = data.reset_coords(['bar'])
        self.assertDatasetIdentical(actual, expected)

        actual = data.reset_coords(drop=True)
        expected = DataArray(np.zeros((3, 4)), dims=['x', 'y'], name='foo')
        self.assertDataArrayIdentical(actual, expected)

        actual = data.copy()
        actual.reset_coords(drop=True, inplace=True)
        self.assertDataArrayIdentical(actual, expected)

        actual = data.reset_coords('bar', drop=True)
        expected = DataArray(np.zeros((3, 4)), {'baz': ('y', range(4))},
                             dims=['x', 'y'], name='foo')
        self.assertDataArrayIdentical(actual, expected)

        with self.assertRaisesRegexp(ValueError, 'cannot reset coord'):
            data.reset_coords(inplace=True)
        with self.assertRaises(KeyError):
            data.reset_coords('foo', drop=True)
        with self.assertRaisesRegexp(ValueError, 'cannot be found'):
            data.reset_coords('not_found')
        with self.assertRaisesRegexp(ValueError, 'cannot remove index'):
            data.reset_coords('y')

    def test_reindex(self):
        foo = self.dv
        bar = self.dv[:2, :2]
        self.assertDataArrayIdentical(foo.reindex_like(bar), bar)

        expected = foo.copy()
        expected[:] = np.nan
        expected[:2, :2] = bar
        self.assertDataArrayIdentical(bar.reindex_like(foo), expected)

    def test_rename(self):
        renamed = self.dv.rename('bar')
        self.assertDatasetIdentical(
            renamed.to_dataset(), self.ds.rename({'foo': 'bar'}))
        self.assertEqual(renamed.name, 'bar')

        renamed = self.dv.rename({'foo': 'bar'})
        self.assertDatasetIdentical(
            renamed.to_dataset(), self.ds.rename({'foo': 'bar'}))
        self.assertEqual(renamed.name, 'bar')

    def test_dataset_getitem(self):
        dv = self.ds['foo']
        self.assertDataArrayIdentical(dv, self.dv)

    def test_array_interface(self):
        self.assertArrayEqual(np.asarray(self.dv), self.x)
        # test patched in methods
        self.assertArrayEqual(self.dv.astype(float), self.v.astype(float))
        self.assertVariableEqual(self.dv.argsort(), self.v.argsort())
        self.assertVariableEqual(self.dv.clip(2, 3), self.v.clip(2, 3))
        # test ufuncs
        expected = deepcopy(self.ds)
        expected['foo'][:] = np.sin(self.x)
        self.assertDataArrayEqual(expected['foo'], np.sin(self.dv))
        self.assertDataArrayEqual(self.dv, np.maximum(self.v, self.dv))
        bar = Variable(['x', 'y'], np.zeros((10, 20)))
        self.assertDataArrayEqual(self.dv, np.maximum(self.dv, bar))

    def test_is_null(self):
        x = np.random.RandomState(42).randn(5, 6)
        x[x < 0] = np.nan
        original = DataArray(x, [-np.arange(5), np.arange(6)], ['x', 'y'])
        expected = DataArray(pd.isnull(x), [-np.arange(5), np.arange(6)],
                             ['x', 'y'])
        self.assertDataArrayIdentical(expected, original.isnull())
        self.assertDataArrayIdentical(~expected, original.notnull())

    def test_math(self):
        x = self.x
        v = self.v
        a = self.dv
        # variable math was already tested extensively, so let's just make sure
        # that all types are properly converted here
        self.assertDataArrayEqual(a, +a)
        self.assertDataArrayEqual(a, a + 0)
        self.assertDataArrayEqual(a, 0 + a)
        self.assertDataArrayEqual(a, a + 0 * v)
        self.assertDataArrayEqual(a, 0 * v + a)
        self.assertDataArrayEqual(a, a + 0 * x)
        self.assertDataArrayEqual(a, 0 * x + a)
        self.assertDataArrayEqual(a, a + 0 * a)
        self.assertDataArrayEqual(a, 0 * a + a)
        # test different indices
        b = a.copy()
        b.coords['x'] = 3 + np.arange(10)
        with self.assertRaisesRegexp(ValueError, 'not aligned'):
            a + b
        with self.assertRaisesRegexp(ValueError, 'not aligned'):
            b + a

    def test_inplace_math_basics(self):
        x = self.x
        v = self.v
        a = self.dv
        b = a
        b += 1
        self.assertIs(b, a)
        self.assertIs(b.variable, v)
        self.assertArrayEqual(b.values, x)
        self.assertIs(source_ndarray(b.values), x)
        self.assertDatasetIdentical(b._dataset, self.ds)

    def test_math_name(self):
        # Verify that name is preserved only when it can be done unambiguously.
        # The rule (copied from pandas.Series) is keep the current name only if
        # the other object has the same name or no name attribute and this
        # object isn't a coordinate; otherwise reset to None.
        a = self.dv
        self.assertEqual((+a).name, 'foo')
        self.assertEqual((a + 0).name, 'foo')
        self.assertIs((a + a.rename(None)).name, None)
        self.assertIs((a + a.rename('bar')).name, None)
        self.assertEqual((a + a).name, 'foo')
        self.assertIs((+a['x']).name, None)
        self.assertIs((a['x'] + 0).name, None)
        self.assertIs((a + a['x']).name, None)

    def test_math_with_coords(self):
        coords = {'x': [-1, -2], 'y': ['ab', 'cd', 'ef'],
                  'lat': (['x', 'y'], [[1, 2, 3], [-1, -2, -3]]),
                  'c': -999}
        orig = DataArray(np.random.randn(2, 3), coords, dims=['x', 'y'])

        actual = orig + 1
        expected = DataArray(orig.values + 1, orig.coords)
        self.assertDataArrayIdentical(expected, actual)

        actual = 1 + orig
        self.assertDataArrayIdentical(expected, actual)

        actual = orig + orig[0, 0]
        exp_coords = dict((k, v) for k, v in coords.items() if k != 'lat')
        expected = DataArray(orig.values + orig.values[0, 0],
                             exp_coords, dims=['x', 'y'])
        self.assertDataArrayIdentical(expected, actual)

        actual = orig[0, 0] + orig
        self.assertDataArrayIdentical(expected, actual)

        actual = orig[0, 0] + orig[-1, -1]
        expected = DataArray(orig.values[0, 0] + orig.values[-1, -1],
                             {'c': -999})
        self.assertDataArrayIdentical(expected, actual)

        actual = orig[:, 0] + orig[0, :]
        exp_values = orig[:, 0].values[:, None] + orig[0, :].values[None, :]
        expected = DataArray(exp_values, exp_coords, dims=['x', 'y'])
        self.assertDataArrayIdentical(expected, actual)

        actual = orig[0, :] + orig[:, 0]
        self.assertDataArrayIdentical(expected.T, actual)

        actual = orig - orig.T
        expected = DataArray(np.zeros((2, 3)), orig.coords)
        self.assertDataArrayIdentical(expected, actual)

        actual = orig.T - orig
        self.assertDataArrayIdentical(expected.T, actual)

        alt = DataArray([1, 1], {'x': [-1, -2], 'c': 'foo', 'd': 555}, 'x')
        actual = orig + alt
        expected = orig + 1
        expected.coords['d'] = 555
        del expected.coords['c']
        self.assertDataArrayIdentical(expected, actual)

        actual = alt + orig
        self.assertDataArrayIdentical(expected, actual)

    def test_index_math(self):
        orig = DataArray(range(3), dims='x', name='x')
        actual = orig + 1
        expected = DataArray(1 + np.arange(3), coords=[('x', range(3))])
        self.assertDataArrayIdentical(expected, actual)

    def test_dataset_math(self):
        # more comprehensive tests with multiple dataset variables
        obs = Dataset({'tmin': ('x', np.arange(5)),
                       'tmax': ('x', 10 + np.arange(5))},
                      {'x': ('x', 0.5 * np.arange(5)),
                       'loc': ('x', range(-2, 3))})

        actual = 2 * obs['tmax']
        expected = DataArray(2 * (10 + np.arange(5)), obs.coords, name='tmax')
        self.assertDataArrayIdentical(actual, expected)

        actual = obs['tmax'] - obs['tmin']
        expected = DataArray(10 * np.ones(5), obs.coords)
        self.assertDataArrayIdentical(actual, expected)

        sim = Dataset({'tmin': ('x', 1 + np.arange(5)),
                       'tmax': ('x', 11 + np.arange(5)),
                       # does *not* include 'loc' as a coordinate
                       'x': ('x', 0.5 * np.arange(5))})

        actual = sim['tmin'] - obs['tmin']
        expected = DataArray(np.ones(5), obs.coords, name='tmin')
        self.assertDataArrayIdentical(actual, expected)

        actual = -obs['tmin'] + sim['tmin']
        self.assertDataArrayIdentical(actual, expected)

        actual = sim['tmin'].copy()
        actual -= obs['tmin']
        self.assertDataArrayIdentical(actual, expected)

        actual = sim.copy()
        actual['tmin'] = sim['tmin'] - obs['tmin']
        expected = Dataset({'tmin': ('x', np.ones(5)),
                            'tmax': ('x', sim['tmax'].values)},
                            obs.coords)
        self.assertDatasetIdentical(actual, expected)

        actual = sim.copy()
        actual['tmin'] -= obs['tmin']
        self.assertDatasetIdentical(actual, expected)

    def test_transpose(self):
        self.assertVariableEqual(self.dv.variable.transpose(),
                                 self.dv.transpose())

    def test_squeeze(self):
        self.assertVariableEqual(self.dv.variable.squeeze(), self.dv.squeeze())

    def test_reduce(self):
        coords = {'x': [-1, -2], 'y': ['ab', 'cd', 'ef'],
                  'lat': (['x', 'y'], [[1, 2, 3], [-1, -2, -3]]),
                  'c': -999}
        orig = DataArray([[-1, 0, 1], [-3, 0, 3]], coords, dims=['x', 'y'])

        actual = orig.mean()
        expected = DataArray(0, {'c': -999})
        self.assertDataArrayIdentical(expected, actual)

        actual = orig.mean(['x', 'y'])
        self.assertDataArrayIdentical(expected, actual)

        actual = orig.mean('x')
        expected = DataArray([-2, 0, 2], {'y': coords['y'], 'c': -999}, 'y')
        self.assertDataArrayIdentical(expected, actual)

        actual = orig.mean(['x'])
        self.assertDataArrayIdentical(expected, actual)

        actual = orig.mean('y')
        expected = DataArray([0, 0], {'x': coords['x'], 'c': -999}, 'x')
        self.assertDataArrayIdentical(expected, actual)

        self.assertVariableEqual(self.dv.reduce(np.mean, 'x'),
                                 self.v.reduce(np.mean, 'x'))

    def test_reduce_keep_attrs(self):
        # Test dropped attrs
        vm = self.va.mean()
        self.assertEqual(len(vm.attrs), 0)
        self.assertEqual(vm.attrs, OrderedDict())

        # Test kept attrs
        vm = self.va.mean(keep_attrs=True)
        self.assertEqual(len(vm.attrs), len(self.attrs))
        self.assertEqual(vm.attrs, self.attrs)

    def test_groupby_iter(self):
        for ((act_x, act_dv), (exp_x, exp_ds)) in \
                zip(self.dv.groupby('y'), self.ds.groupby('y')):
            self.assertEqual(exp_x, act_x)
            self.assertDataArrayIdentical(exp_ds['foo'], act_dv)
        for ((_, exp_dv), act_dv) in zip(self.dv.groupby('x'), self.dv):
            self.assertDataArrayIdentical(exp_dv, act_dv)

    def make_groupby_example_array(self):
        da = self.dv.copy()
        da.coords['abc'] = ('y', np.array(['a'] * 9 + ['c'] + ['b'] * 10))
        da.coords['y'] = 20 + 100 * da['y']
        return da

    def test_groupby_properties(self):
        grouped = self.make_groupby_example_array().groupby('abc')
        expected_unique = Variable('abc', ['a', 'b', 'c'])
        self.assertVariableEqual(expected_unique, grouped.unique_coord)
        self.assertEqual(3, len(grouped))

    def test_groupby_apply_identity(self):
        expected = self.make_groupby_example_array()
        idx = expected.coords['y']
        identity = lambda x: x
        for g in ['x', 'y', 'abc', idx]:
            for shortcut in [False, True]:
                for squeeze in [False, True]:
                    grouped = expected.groupby(g, squeeze=squeeze)
                    actual = grouped.apply(identity, shortcut=shortcut)
                    self.assertDataArrayIdentical(expected, actual)

    def test_groupby_sum(self):
        array = self.make_groupby_example_array()
        grouped = array.groupby('abc')

        expected_sum_all = Dataset(
            {'foo': Variable(['abc'], np.array([self.x[:, :9].sum(),
                                                self.x[:, 10:].sum(),
                                                self.x[:, 9:10].sum()]).T),
             'abc': Variable(['abc'], np.array(['a', 'b', 'c']))})['foo']
        self.assertDataArrayAllClose(expected_sum_all, grouped.reduce(np.sum))
        self.assertDataArrayAllClose(expected_sum_all, grouped.sum())

        expected = DataArray([array['y'].values[idx].sum() for idx
                              in [slice(9), slice(10, None), slice(9, 10)]],
                             [['a', 'b', 'c']], ['abc'])
        actual = array['y'].groupby('abc').apply(np.sum)
        self.assertDataArrayAllClose(expected, actual)
        actual = array['y'].groupby('abc').sum()
        self.assertDataArrayAllClose(expected, actual)

        expected_sum_axis1 = Dataset(
            {'foo': (['x', 'abc'], np.array([self.x[:, :9].sum(1),
                                             self.x[:, 10:].sum(1),
                                             self.x[:, 9:10].sum(1)]).T),
             'x': self.ds['x'],
             'abc': Variable(['abc'], np.array(['a', 'b', 'c']))})['foo']
        self.assertDataArrayAllClose(expected_sum_axis1,
                                     grouped.reduce(np.sum, 'y'))
        self.assertDataArrayAllClose(expected_sum_axis1, grouped.sum('y'))

    @unittest.skip('needs to be fixed for shortcut=False, keep_attrs=False')
    def test_groupby_reduce_attrs(self):
        array = self.make_groupby_example_array()
        array.attrs['foo'] = 'bar'

        for shortcut in [True, False]:
            for keep_attrs in [True, False]:
                print('shortcut=%s, keep_attrs=%s' % (shortcut, keep_attrs))
                actual = array.groupby('abc').reduce(
                    np.mean, keep_attrs=keep_attrs, shortcut=shortcut)
                expected = array.groupby('abc').mean()
                if keep_attrs:
                    expected.attrs['foo'] = 'bar'
                self.assertDataArrayIdentical(expected, actual)

    def test_groupby_apply_center(self):
        def center(x):
            return x - np.mean(x)

        array = self.make_groupby_example_array()
        grouped = array.groupby('abc')

        expected_ds = array.to_dataset()
        exp_data = np.hstack([center(self.x[:, :9]),
                              center(self.x[:, 9:10]),
                              center(self.x[:, 10:])])
        expected_ds['foo'] = (['x', 'y'], exp_data)
        expected_centered = expected_ds['foo']
        self.assertDataArrayAllClose(expected_centered, grouped.apply(center))

    def test_groupby_math(self):
        array = self.make_groupby_example_array()
        for squeeze in [True, False]:
            grouped = array.groupby('x', squeeze=squeeze)

            expected = array + array.coords['x']
            actual = grouped + array.coords['x']
            self.assertDataArrayIdentical(expected, actual)

            actual = array.coords['x'] + grouped
            self.assertDataArrayIdentical(expected, actual)

            ds = array.coords['x'].to_dataset()
            expected = array + ds
            actual = grouped + ds
            self.assertDatasetIdentical(expected, actual)

            actual = ds + grouped
            self.assertDatasetIdentical(expected, actual)

        grouped = array.groupby('abc')
        expected_agg = (grouped.mean() - np.arange(3)).rename(None)
        actual = grouped - DataArray(range(3), [('abc', ['a', 'b', 'c'])])
        actual_agg = actual.groupby('abc').mean()
        self.assertDataArrayAllClose(expected_agg, actual_agg)

        with self.assertRaisesRegexp(TypeError, 'only support arithmetic'):
            grouped + 1
        with self.assertRaisesRegexp(TypeError, 'only support arithmetic'):
            grouped + grouped

    def test_concat(self):
        self.ds['bar'] = Variable(['x', 'y'], np.random.randn(10, 20))
        foo = self.ds['foo']
        bar = self.ds['bar']
        # from dataset array:
        expected = DataArray(np.array([foo.values, bar.values]),
                             dims=['w', 'x', 'y'])
        actual = concat([foo, bar], 'w')
        self.assertDataArrayEqual(expected, actual)
        # from iteration:
        grouped = [g for _, g in foo.groupby('x')]
        stacked = concat(grouped, self.ds['x'])
        self.assertDataArrayIdentical(foo, stacked)
        # with an index as the 'dim' argument
        stacked = concat(grouped, self.ds.indexes['x'])
        self.assertDataArrayIdentical(foo, stacked)

        actual = concat([foo[0], foo[1]], pd.Index([0, 1])).reset_coords(drop=True)
        expected = foo[:2].rename({'x': 'concat_dim'})
        self.assertDataArrayIdentical(expected, actual)

        actual = concat([foo[0], foo[1]], [0, 1]).reset_coords(drop=True)
        expected = foo[:2].rename({'x': 'concat_dim'})
        self.assertDataArrayIdentical(expected, actual)

        with self.assertRaisesRegexp(ValueError, 'not identical'):
            concat([foo, bar], compat='identical')

    def test_align(self):
        self.ds['x'] = ('x', np.array(list('abcdefghij')))
        with self.assertRaises(ValueError):
            self.dv + self.dv[:5]
        dv1, dv2 = align(self.dv, self.dv[:5], join='inner')
        self.assertDataArrayIdentical(dv1, self.dv[:5])
        self.assertDataArrayIdentical(dv2, self.dv[:5])

    def test_to_and_from_series(self):
        expected = self.dv.to_dataframe()['foo']
        actual = self.dv.to_series()
        self.assertArrayEqual(expected.values, actual.values)
        self.assertArrayEqual(expected.index.values, actual.index.values)
        self.assertEqual('foo', actual.name)
        # test roundtrip
        self.assertDataArrayIdentical(self.dv, DataArray.from_series(actual))
        # test name is None
        actual.name = None
        expected_da = self.dv.rename(None)
        self.assertDataArrayIdentical(expected_da,
                                      DataArray.from_series(actual))

    def test_to_dataset(self):
        unnamed = DataArray([1, 2], dims='x')
        actual = unnamed.to_dataset()
        expected = Dataset({None: ('x', [1, 2])})
        self.assertDatasetIdentical(expected, actual)
        self.assertIsNot(unnamed._dataset, actual)

        actual = unnamed.to_dataset('foo')
        expected = Dataset({'foo': ('x', [1, 2])})
        self.assertDatasetIdentical(expected, actual)

        named = DataArray([1, 2], dims='x', name='foo')
        actual = named.to_dataset()
        expected = Dataset({'foo': ('x', [1, 2])})
        self.assertDatasetIdentical(expected, actual)

        actual = named.to_dataset('bar')
        expected = Dataset({'bar': ('x', [1, 2])})
        self.assertDatasetIdentical(expected, actual)
