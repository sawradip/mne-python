# -*- coding: utf-8 -*-
"""The config functions."""
# Authors: Eric Larson <larson.eric.d@gmail.com>
#
# License: BSD-3-Clause

import atexit
from functools import partial
import json
import os
import os.path as op
import platform
import shutil
import subprocess
import sys
import tempfile
import re

from .check import (_validate_type, _check_qt_version, _check_option,
                    _check_fname)
from .docs import fill_doc
from .misc import _pl
from ._logging import warn, logger


_temp_home_dir = None


def set_cache_dir(cache_dir):
    """Set the directory to be used for temporary file storage.

    This directory is used by joblib to store memmapped arrays,
    which reduces memory requirements and speeds up parallel
    computation.

    Parameters
    ----------
    cache_dir : str or None
        Directory to use for temporary file storage. None disables
        temporary file storage.
    """
    if cache_dir is not None and not op.exists(cache_dir):
        raise IOError('Directory %s does not exist' % cache_dir)

    set_config('MNE_CACHE_DIR', cache_dir, set_env=False)


def set_memmap_min_size(memmap_min_size):
    """Set the minimum size for memmaping of arrays for parallel processing.

    Parameters
    ----------
    memmap_min_size : str or None
        Threshold on the minimum size of arrays that triggers automated memory
        mapping for parallel processing, e.g., '1M' for 1 megabyte.
        Use None to disable memmaping of large arrays.
    """
    if memmap_min_size is not None:
        if not isinstance(memmap_min_size, str):
            raise ValueError('\'memmap_min_size\' has to be a string.')
        if memmap_min_size[-1] not in ['K', 'M', 'G']:
            raise ValueError('The size has to be given in kilo-, mega-, or '
                             'gigabytes, e.g., 100K, 500M, 1G.')

    set_config('MNE_MEMMAP_MIN_SIZE', memmap_min_size, set_env=False)


# List the known configuration values
known_config_types = (
    'MNE_3D_OPTION_ANTIALIAS',
    'MNE_3D_OPTION_DEPTH_PEELING',
    'MNE_3D_OPTION_MULTI_SAMPLES',
    'MNE_3D_OPTION_SMOOTH_SHADING',
    'MNE_3D_OPTION_THEME',
    'MNE_BROWSE_RAW_SIZE',
    'MNE_BROWSER_BACKEND',
    'MNE_BROWSER_OVERVIEW_MODE',
    'MNE_BROWSER_PRECOMPUTE',
    'MNE_BROWSER_THEME',
    'MNE_BROWSER_USE_OPENGL',
    'MNE_CACHE_DIR',
    'MNE_COREG_ADVANCED_RENDERING',
    'MNE_COREG_COPY_ANNOT',
    'MNE_COREG_FULLSCREEN',
    'MNE_COREG_GUESS_MRI_SUBJECT',
    'MNE_COREG_HEAD_HIGH_RES',
    'MNE_COREG_HEAD_OPACITY',
    'MNE_COREG_HEAD_INSIDE',
    'MNE_COREG_INTERACTION',
    'MNE_COREG_MARK_INSIDE',
    'MNE_COREG_PREPARE_BEM',
    'MNE_COREG_ORIENT_TO_SURFACE',
    'MNE_COREG_SCALE_LABELS',
    'MNE_COREG_SCALE_BY_DISTANCE',
    'MNE_COREG_SCENE_SCALE',
    'MNE_COREG_WINDOW_HEIGHT',
    'MNE_COREG_WINDOW_WIDTH',
    'MNE_COREG_SUBJECTS_DIR',
    'MNE_CUDA_DEVICE',
    'MNE_CUDA_IGNORE_PRECISION',
    'MNE_DATA',
    'MNE_DATASETS_BRAINSTORM_PATH',
    'MNE_DATASETS_EEGBCI_PATH',
    'MNE_DATASETS_EPILEPSY_ECOG_PATH',
    'MNE_DATASETS_HF_SEF_PATH',
    'MNE_DATASETS_MEGSIM_PATH',
    'MNE_DATASETS_MISC_PATH',
    'MNE_DATASETS_MTRF_PATH',
    'MNE_DATASETS_SAMPLE_PATH',
    'MNE_DATASETS_SOMATO_PATH',
    'MNE_DATASETS_MULTIMODAL_PATH',
    'MNE_DATASETS_FNIRS_MOTOR_PATH',
    'MNE_DATASETS_OPM_PATH',
    'MNE_DATASETS_SPM_FACE_DATASETS_TESTS',
    'MNE_DATASETS_SPM_FACE_PATH',
    'MNE_DATASETS_TESTING_PATH',
    'MNE_DATASETS_VISUAL_92_CATEGORIES_PATH',
    'MNE_DATASETS_KILOWORD_PATH',
    'MNE_DATASETS_FIELDTRIP_CMC_PATH',
    'MNE_DATASETS_PHANTOM_4DBTI_PATH',
    'MNE_DATASETS_LIMO_PATH',
    'MNE_DATASETS_REFMEG_NOISE_PATH',
    'MNE_DATASETS_SSVEP_PATH',
    'MNE_DATASETS_ERP_CORE_PATH',
    'MNE_DATASETS_EPILEPSY_ECOG_PATH',
    'MNE_DATASETS_UCL_OPM_AUDITORY_PATH',
    'MNE_FORCE_SERIAL',
    'MNE_KIT2FIFF_STIM_CHANNELS',
    'MNE_KIT2FIFF_STIM_CHANNEL_CODING',
    'MNE_KIT2FIFF_STIM_CHANNEL_SLOPE',
    'MNE_KIT2FIFF_STIM_CHANNEL_THRESHOLD',
    'MNE_LOGGING_LEVEL',
    'MNE_MEMMAP_MIN_SIZE',
    'MNE_REPR_HTML',
    'MNE_SKIP_FTP_TESTS',
    'MNE_SKIP_NETWORK_TESTS',
    'MNE_SKIP_TESTING_DATASET_TESTS',
    'MNE_STIM_CHANNEL',
    'MNE_TQDM',
    'MNE_USE_CUDA',
    'MNE_USE_NUMBA',
    'SUBJECTS_DIR',
)

# These allow for partial matches, e.g. 'MNE_STIM_CHANNEL_1' is okay key
known_config_wildcards = (
    'MNE_STIM_CHANNEL',
    'MNE_DATASETS_FNIRS',
    'MNE_NIRS',
)


def _load_config(config_path, raise_error=False):
    """Safely load a config file."""
    with open(config_path, 'r') as fid:
        try:
            config = json.load(fid)
        except ValueError:
            # No JSON object could be decoded --> corrupt file?
            msg = ('The MNE-Python config file (%s) is not a valid JSON '
                   'file and might be corrupted' % config_path)
            if raise_error:
                raise RuntimeError(msg)
            warn(msg)
            config = dict()
    return config


def get_config_path(home_dir=None):
    r"""Get path to standard mne-python config file.

    Parameters
    ----------
    home_dir : str | None
        The folder that contains the .mne config folder.
        If None, it is found automatically.

    Returns
    -------
    config_path : str
        The path to the mne-python configuration file. On windows, this
        will be '%USERPROFILE%\.mne\mne-python.json'. On every other
        system, this will be ~/.mne/mne-python.json.
    """
    val = op.join(_get_extra_data_path(home_dir=home_dir),
                  'mne-python.json')
    return val


def get_config(key=None, default=None, raise_error=False, home_dir=None,
               use_env=True):
    """Read MNE-Python preferences from environment or config file.

    Parameters
    ----------
    key : None | str
        The preference key to look for. The os environment is searched first,
        then the mne-python config file is parsed.
        If None, all the config parameters present in environment variables or
        the path are returned. If key is an empty string, a list of all valid
        keys (but not values) is returned.
    default : str | None
        Value to return if the key is not found.
    raise_error : bool
        If True, raise an error if the key is not found (instead of returning
        default).
    home_dir : str | None
        The folder that contains the .mne config folder.
        If None, it is found automatically.
    use_env : bool
        If True, consider env vars, if available.
        If False, only use MNE-Python configuration file values.

        .. versionadded:: 0.18

    Returns
    -------
    value : dict | str | None
        The preference key value.

    See Also
    --------
    set_config
    """
    _validate_type(key, (str, type(None)), "key", 'string or None')

    if key == '':
        return known_config_types

    # first, check to see if key is in env
    if use_env and key is not None and key in os.environ:
        return os.environ[key]

    # second, look for it in mne-python config file
    config_path = get_config_path(home_dir=home_dir)
    if not op.isfile(config_path):
        config = {}
    else:
        config = _load_config(config_path)

    if key is None:
        # update config with environment variables
        if use_env:
            env_keys = (set(config).union(known_config_types).
                        intersection(os.environ))
            config.update({key: os.environ[key] for key in env_keys})
        return config
    elif raise_error is True and key not in config:
        loc_env = 'the environment or in the ' if use_env else ''
        meth_env = ('either os.environ["%s"] = VALUE for a temporary '
                    'solution, or ' % key) if use_env else ''
        extra_env = (' You can also set the environment variable before '
                     'running python.' if use_env else '')
        meth_file = ('mne.utils.set_config("%s", VALUE, set_env=True) '
                     'for a permanent one' % key)
        raise KeyError('Key "%s" not found in %s'
                       'the mne-python config file (%s). '
                       'Try %s%s.%s'
                       % (key, loc_env, config_path, meth_env, meth_file,
                          extra_env))
    else:
        return config.get(key, default)


def set_config(key, value, home_dir=None, set_env=True):
    """Set a MNE-Python preference key in the config file and environment.

    Parameters
    ----------
    key : str
        The preference key to set.
    value : str |  None
        The value to assign to the preference key. If None, the key is
        deleted.
    home_dir : str | None
        The folder that contains the .mne config folder.
        If None, it is found automatically.
    set_env : bool
        If True (default), update :data:`os.environ` in addition to
        updating the MNE-Python config file.

    See Also
    --------
    get_config
    """
    _validate_type(key, 'str', "key")
    # While JSON allow non-string types, we allow users to override config
    # settings using env, which are strings, so we enforce that here
    _validate_type(value, (str, 'path-like', type(None)), 'value')
    if value is not None:
        value = str(value)

    if key not in known_config_types and not \
            any(key.startswith(k) for k in known_config_wildcards):
        warn('Setting non-standard config type: "%s"' % key)

    # Read all previous values
    config_path = get_config_path(home_dir=home_dir)
    if op.isfile(config_path):
        config = _load_config(config_path, raise_error=True)
    else:
        config = dict()
        logger.info('Attempting to create new mne-python configuration '
                    'file:\n%s' % config_path)
    if value is None:
        config.pop(key, None)
        if set_env and key in os.environ:
            del os.environ[key]
    else:
        config[key] = value
        if set_env:
            os.environ[key] = value

    # Write all values. This may fail if the default directory is not
    # writeable.
    directory = op.dirname(config_path)
    if not op.isdir(directory):
        os.mkdir(directory)
    with open(config_path, 'w') as fid:
        json.dump(config, fid, sort_keys=True, indent=0)


def _get_extra_data_path(home_dir=None):
    """Get path to extra data (config, tables, etc.)."""
    global _temp_home_dir
    if home_dir is None:
        home_dir = os.environ.get('_MNE_FAKE_HOME_DIR')
    if home_dir is None:
        # this has been checked on OSX64, Linux64, and Win32
        if 'nt' == os.name.lower():
            APPDATA_DIR = os.getenv('APPDATA')
            USERPROFILE_DIR = os.getenv('USERPROFILE')
            if (
                APPDATA_DIR is not None
                and op.isdir(op.join(APPDATA_DIR, '.mne'))  # backward-compat
            ):
                home_dir = APPDATA_DIR
            elif USERPROFILE_DIR is not None:
                home_dir = USERPROFILE_DIR
            else:
                raise FileNotFoundError(
                    "The USERPROFILE environment variable is not set, cannot "
                    "determine the location of the MNE-Python configuration "
                    "folder"
                )
            del APPDATA_DIR, USERPROFILE_DIR
        else:
            # This is a more robust way of getting the user's home folder on
            # Linux platforms (not sure about OSX, Unix or BSD) than checking
            # the HOME environment variable. If the user is running some sort
            # of script that isn't launched via the command line (e.g. a script
            # launched via Upstart) then the HOME environment variable will
            # not be set.
            if os.getenv('MNE_DONTWRITE_HOME', '') == 'true':
                if _temp_home_dir is None:
                    _temp_home_dir = tempfile.mkdtemp()
                    atexit.register(partial(shutil.rmtree, _temp_home_dir,
                                            ignore_errors=True))
                home_dir = _temp_home_dir
            else:
                home_dir = os.path.expanduser('~')

        if home_dir is None:
            raise ValueError('mne-python config file path could '
                             'not be determined, please report this '
                             'error to mne-python developers')

    return op.join(home_dir, '.mne')


def get_subjects_dir(subjects_dir=None, raise_error=False):
    """Safely use subjects_dir input to return SUBJECTS_DIR.

    Parameters
    ----------
    subjects_dir : str | None
        If a value is provided, return subjects_dir. Otherwise, look for
        SUBJECTS_DIR config and return the result.
    raise_error : bool
        If True, raise a KeyError if no value for SUBJECTS_DIR can be found
        (instead of returning None).

    Returns
    -------
    value : str | None
        The SUBJECTS_DIR value.
    """
    _validate_type(item=subjects_dir, types=('path-like', None),
                   item_name='subjects_dir', type_name='str or path-like')

    if subjects_dir is None:
        subjects_dir = get_config('SUBJECTS_DIR', raise_error=raise_error)
    if subjects_dir is not None:
        subjects_dir = _check_fname(
            fname=subjects_dir, overwrite='read', must_exist=True,
            need_dir=True, name='subjects_dir'
        )

    return subjects_dir


@fill_doc
def _get_stim_channel(stim_channel, info, raise_error=True):
    """Determine the appropriate stim_channel.

    First, 'MNE_STIM_CHANNEL', 'MNE_STIM_CHANNEL_1', 'MNE_STIM_CHANNEL_2', etc.
    are read. If these are not found, it will fall back to 'STI 014' if
    present, then fall back to the first channel of type 'stim', if present.

    Parameters
    ----------
    stim_channel : str | list of str | None
        The stim channel selected by the user.
    %(info_not_none)s

    Returns
    -------
    stim_channel : str | list of str
        The name of the stim channel(s) to use
    """
    if stim_channel is not None:
        if not isinstance(stim_channel, list):
            _validate_type(stim_channel, 'str', "Stim channel")
            stim_channel = [stim_channel]
        for channel in stim_channel:
            _validate_type(channel, 'str', "Each provided stim channel")
        return stim_channel

    stim_channel = list()
    ch_count = 0
    ch = get_config('MNE_STIM_CHANNEL')
    while ch is not None and ch in info['ch_names']:
        stim_channel.append(ch)
        ch_count += 1
        ch = get_config('MNE_STIM_CHANNEL_%d' % ch_count)
    if ch_count > 0:
        return stim_channel

    if 'STI101' in info['ch_names']:  # combination channel for newer systems
        return ['STI101']
    if 'STI 014' in info['ch_names']:  # for older systems
        return ['STI 014']

    from ..io.pick import pick_types
    stim_channel = pick_types(info, meg=False, ref_meg=False, stim=True)
    if len(stim_channel) > 0:
        stim_channel = [info['ch_names'][ch_] for ch_ in stim_channel]
    elif raise_error:
        raise ValueError("No stim channels found. Consider specifying them "
                         "manually using the 'stim_channel' parameter.")
    return stim_channel


def _get_root_dir():
    """Get as close to the repo root as possible."""
    root_dir = op.abspath(op.join(op.dirname(__file__), '..'))
    up_dir = op.join(root_dir, '..')
    if op.isfile(op.join(up_dir, 'setup.py')) and all(
            op.isdir(op.join(up_dir, x)) for x in ('mne', 'examples', 'doc')):
        root_dir = op.abspath(up_dir)
    return root_dir


def _get_numpy_libs():
    bad_lib = 'unknown linalg bindings'
    try:
        from threadpoolctl import threadpool_info
    except Exception as exc:
        return bad_lib + f' (threadpoolctl module not found: {exc})'
    pools = threadpool_info()
    rename = dict(
        openblas='OpenBLAS',
        mkl='MKL',
    )
    for pool in pools:
        if pool['internal_api'] in ('openblas', 'mkl'):
            return (
                f'{rename[pool["internal_api"]]} '
                f'{pool["version"]} with '
                f'{pool["num_threads"]} thread{_pl(pool["num_threads"])}')
    return bad_lib


_gpu_cmd = """\
from pyvista import GPUInfo; \
gi = GPUInfo(); \
print(gi.version); \
print(gi.renderer)"""


def _get_gpu_info():
    # Once https://github.com/pyvista/pyvista/pull/2250 is merged and PyVista
    # does a release, we can triage based on version > 0.33.2
    proc = subprocess.run(
        [sys.executable, '-c', _gpu_cmd], check=False, capture_output=True)
    out = proc.stdout.decode().strip().replace('\r', '').split('\n')
    if proc.returncode or len(out) != 2:
        return None, None
    return out


def sys_info(fid=None, show_paths=False, *, dependencies='user'):
    """Print the system information for debugging.

    This function is useful for printing system information
    to help triage bugs.

    Parameters
    ----------
    fid : file-like | None
        The file to write to. Will be passed to :func:`print()`.
        Can be None to use :data:`sys.stdout`.
    show_paths : bool
        If True, print paths for each module.
    dependencies : 'user' | 'developer'
        Show dependencies relevant for users (default) or for developers
        (i.e., output includes additional dependencies).

        .. versionadded:: 0.24

    Examples
    --------
    Running this function with no arguments prints an output that is
    useful when submitting bug reports::

        >>> import mne
        >>> mne.sys_info() # doctest: +SKIP
        Platform:      Linux-4.15.0-1067-aws-x86_64-with-glibc2.2.5
        Python:        3.8.1 (default, Feb  2 2020, 08:37:37)  [GCC 8.3.0]
        Executable:    /usr/local/bin/python
        CPU:           : 36 cores
        Memory:        68.7 GB

        mne:           0.21.dev0
        numpy:         1.19.0 {blas=openblas, lapack=openblas}
        scipy:         1.5.1
        matplotlib:    3.2.2 {backend=Qt5Agg}

        sklearn:       0.23.1
        numba:         0.50.1
        nibabel:       3.1.1
        nilearn:       0.7.0
        dipy:          1.1.1
        cupy:          Not found
        pandas:        1.0.5
        pyvista:       0.25.3 {pyvistaqt=0.1.1, OpenGL 3.3 (Core Profile) Mesa 18.3.6 via llvmpipe (LLVM 7.0, 256 bits)}
        vtk:           9.0.1
        qtpy:          2.0.1 {PySide6=6.2.4}
        pyqtgraph:     0.12.4
        pooch:         v1.5.1
    """  # noqa: E501
    _validate_type(dependencies, str)
    _check_option('dependencies', dependencies, ('user', 'developer'))
    ljust = 21 if dependencies == 'developer' else 18
    platform_str = platform.platform()
    if platform.system() == 'Darwin' and sys.version_info[:2] < (3, 8):
        # platform.platform() in Python < 3.8 doesn't call
        # platform.mac_ver() if we're on Darwin, so we don't get a nice macOS
        # version number. Therefore, let's do this manually here.
        macos_ver = platform.mac_ver()[0]
        macos_architecture = re.findall('Darwin-.*?-(.*)', platform_str)
        if macos_architecture:
            macos_architecture = macos_architecture[0]
            platform_str = f'macOS-{macos_ver}-{macos_architecture}'
        del macos_ver, macos_architecture

    out = partial(print, end='', file=fid)
    out('Platform:'.ljust(ljust) + platform_str + '\n')
    out('Python:'.ljust(ljust) + str(sys.version).replace('\n', ' ') + '\n')
    out('Executable:'.ljust(ljust) + sys.executable + '\n')
    out('CPU:'.ljust(ljust) + f'{platform.processor()}: ')
    try:
        import multiprocessing
    except ImportError:
        out('number of processors unavailable '
            '(requires "multiprocessing" package)\n')
    else:
        out(f'{multiprocessing.cpu_count()} cores\n')
    out('Memory:'.ljust(ljust))
    try:
        import psutil
    except ImportError:
        out('Unavailable (requires "psutil" package)')
    else:
        out(f'{psutil.virtual_memory().total / float(2 ** 30):0.1f} GB\n')
    out('\n')
    libs = _get_numpy_libs()
    use_mod_names = ('mne', 'numpy', 'scipy', 'matplotlib', '', 'sklearn',
                     'numba', 'nibabel', 'nilearn', 'dipy', 'openmeeg', 'cupy',
                     'pandas', 'pyvista', 'pyvistaqt', 'ipyvtklink', 'vtk',
                     'qtpy', 'ipympl', 'pyqtgraph', 'pooch', '', 'mne_bids',
                     'mne_nirs', 'mne_features', 'mne_qt_browser',
                     'mne_connectivity', 'mne_icalabel')
    if dependencies == 'developer':
        use_mod_names += (
            '', 'sphinx', 'sphinx_gallery', 'numpydoc', 'pydata_sphinx_theme',
            'pytest', 'nbclient')
    for mod_name in use_mod_names:
        if mod_name == '':
            out('\n')
            continue
        out(f'{mod_name}:'.ljust(ljust))
        try:
            mod = __import__(mod_name)
        except Exception:
            out('Not found\n')
        else:
            if mod_name == 'vtk':
                vtk_version = mod.vtkVersion()
                # 9.0 dev has VersionFull but 9.0 doesn't
                for attr in ('GetVTKVersionFull', 'GetVTKVersion'):
                    if hasattr(vtk_version, attr):
                        version = getattr(vtk_version, attr)()
                        if version != '':
                            out(version)
                            break
                else:
                    out('unknown')
            else:
                out(mod.__version__)
            if mod_name == 'numpy':
                out(f' {{{libs}}}')
            elif mod_name == 'qtpy':
                version, api = _check_qt_version(return_api=True)
                out(f' {{{api}={version}}}')
            elif mod_name == 'matplotlib':
                out(f' {{backend={mod.get_backend()}}}')
            elif mod_name == 'pyvista':
                version, renderer = _get_gpu_info()
                if version is None:
                    out(' {OpenGL could not be initialized}')
                else:
                    out(f' {{OpenGL {version} via {renderer}}}')
            if show_paths:
                out(f'\n{" " * ljust}•{op.dirname(mod.__file__)}')
            out('\n')
