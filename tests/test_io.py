import shutil
import numpy as np
import pytest
from aict_tools.configuration import AICTConfig


@pytest.fixture(scope='function', params=['tables', 'h5py'])
def hdf5_file(tmpdir_factory, request):
    if request.param == 'h5py':
        fn = tmpdir_factory.mktemp('aict_test_data').join('test_file.hdf5')
        shutil.copy('examples/gamma.hdf5', fn)
        return fn, 'events', AICTConfig.from_yaml('examples/config_energy.yaml')
    else:
        fn = tmpdir_factory.mktemp('aict_test_data').join('test_file.hdf5')
        shutil.copy('examples/cta_tables_file.hdf5', fn)
        return fn, 'telescope_events', AICTConfig.from_yaml('examples/cta_config.yaml')


@pytest.fixture(scope='function')
def tables_file(request, tmpdir_factory):
    fn = tmpdir_factory.mktemp('aict_test_data').join('test_file.hdf5')
    shutil.copy('examples/cta_tables_file.hdf5', fn)
    return fn


@pytest.fixture(scope='function')
def h5py_file(tmpdir_factory):
    fn = tmpdir_factory.mktemp('aict_test_data').join('test_file.hdf5')
    shutil.copy('examples/gamma.hdf5', fn)
    return fn


@pytest.fixture(scope='session')
def fact_config():
    from aict_tools.configuration import AICTConfig

    return AICTConfig.from_yaml('examples/config_energy.yaml')


@pytest.fixture(scope='session')
def cta_config():
    from aict_tools.configuration import AICTConfig

    return AICTConfig.from_yaml('examples/cta_config.yaml')


def test_remove_column(hdf5_file):
    from aict_tools.io import get_column_names_in_file
    from aict_tools.io import remove_column_from_file

    path, table, _ = hdf5_file
    columns = get_column_names_in_file(path, table)
    assert 'width' in columns

    remove_column_from_file(path, table, 'width')
    columns = get_column_names_in_file(path, table)
    assert 'width' not in columns


def test_columns_in_file(hdf5_file):
    from aict_tools.io import get_column_names_in_file

    path, table_name, _ = hdf5_file
    columns = get_column_names_in_file(path, table_name)
    assert 'width' in columns
    assert 'length' in columns


def test_read_data(h5py_file):
    from aict_tools.io import read_data

    df = read_data(h5py_file, 'events')
    assert 'run_id' in df.columns
    assert 'width' in df.columns


def test_read_data_tables(tables_file):
    from aict_tools.io import read_data

    df = read_data(tables_file, 'telescope_events')
    assert 'telescope_id' in df.columns

    df = read_data(tables_file, 'array_events')
    assert 'array_event_id' in df.columns


def test_append_column(hdf5_file):
    from aict_tools.io import read_data
    from aict_tools.io import append_column_to_hdf5

    path, table_name, _ = hdf5_file
    new_column_name = 'foobar'

    df = read_data(path, table_name)
    assert new_column_name not in df.columns

    random_data = np.random.normal(size=len(df))
    append_column_to_hdf5(path, random_data, table_name, new_column_name)

    df = read_data(path, table_name)
    assert new_column_name in df.columns


def test_append_column_chunked(hdf5_file):
    from aict_tools.io import read_telescope_data_chunked, read_data
    from aict_tools.io import HDFColumnAppender

    path, table_name, config = hdf5_file

    new_column_name = 'foobar'
    chunk_size = 125

    df = read_data(path, table_name)

    assert new_column_name not in df.columns

    columns = config.energy.columns_to_read_train
    with HDFColumnAppender(path, table_name) as appender:
        generator = read_telescope_data_chunked(path, config, chunk_size, columns=columns)
        for df, start, stop in generator:
            assert not df.empty
            new_data = np.arange(start, stop, step=1)
            appender.add_data(new_data, new_column_name, start, stop)

    df = read_data(path, table_name)
    assert new_column_name in df.columns
    assert np.array_equal(df.foobar, np.arange(0, len(df)))
    if table_name == 'telescope_events':
        df.set_index(
            ['run_id', 'array_event_id', 'telescope_id'],
            drop=True,
            verify_integrity=True,
            inplace=True,
        )


def test_read_chunks_tables_feature_gen(tables_file, cta_config):
    from aict_tools.io import read_telescope_data_chunked

    chunk_size = 125

    columns = cta_config.energy.columns_to_read_train
    fg = cta_config.energy.feature_generation
    generator = read_telescope_data_chunked(
        tables_file, cta_config, chunk_size, columns=columns, feature_generation_config=fg
    )
    for df, _, _ in generator:
        assert not df.empty
        assert set(df.columns) == set(
            cta_config.energy.features + ['array_event_id', 'run_id']
        ) | set([cta_config.energy.target_column])


def test_read_telescope_data_feature_gen(h5py_file, fact_config):
    from aict_tools.io import read_telescope_data

    columns = fact_config.energy.columns_to_read_train

    feature_gen_config = fact_config.energy.feature_generation
    df = read_telescope_data(
        h5py_file, fact_config, columns=columns, feature_generation_config=feature_gen_config
    )
    assert set(df.columns) == set(fact_config.energy.features) | set(
        [fact_config.energy.target_column]
    )

    # new column with name 'area' should exist after feature generation
    assert 'area' in df.columns


def test_read_chunks(hdf5_file):
    from aict_tools.io import read_telescope_data_chunked
    from aict_tools.io import read_data

    path, table_name, config = hdf5_file

    chunk_size = 125
    generator = read_telescope_data_chunked(path, config, chunk_size, ['width', 'length'])

    stops = []
    for df, _, stop in generator:
        stops.append(stop)
        assert not df.empty

    df = read_data(path, table_name)
    assert stops[-1] == len(df)
    # first chunk shuld have the given chunksize
    assert stops[1] - stops[0] == chunk_size

