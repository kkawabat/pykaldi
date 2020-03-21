#!/usr/bin/env python
"""Setup configuration."""
from __future__ import print_function

import os
import platform
import shutil
import subprocess
import sys
import traceback
import distutils.command.build
import setuptools.command.build_ext
import setuptools.command.install_lib
import setuptools.command.test
import setuptools.extension
from setuptools import setup, find_packages, Command

CWD = os.path.dirname(os.path.abspath(__file__))


def run_macos_clang_setup():
    # For macOS we first check to see if clang is available and if not prompt installation of it
    # then depending on macOS version it might not have all the standard libraries (e.g. stdio.h) in the default folder
    # and depending on the macOS version they might have different default folders in which case we will have to symlink it
    # for debugging use: "gcc -Wp,-v -E -" in terminal to view paths

    # Find the path to the xcode-select directory which contains a large suite of unix libraries including c++ compiler
    # if not found then raise an error and instruction on how to install it
    try:
        xcode_sel_path = subprocess.check_output(['xcode-select', '-p']).decode().strip()
        if 'CommandLineTools' in xcode_sel_path:
            system_header_path = os.path.join(xcode_sel_path, 'SDKs', 'MacOSX.sdk')
        elif 'Xcode.app' in xcode_sel_path:
            system_header_path = os.path.join(xcode_sel_path, 'Platforms', 'MacOSX.platform', 'Developer', 'SDKs', 'MacOSX.sdk')
        else:
            raise FileNotFoundError('expected `xcode-select -p` to return xcode.app path or commandlinetools path'
                                    'please set your xcode-select to one of these paths')
    except FileNotFoundError:
        raise FileNotFoundError('xcode-select is not found please run "xcode-select --install" in terminal to install it')

    # using the solution here https://stackoverflow.com/a/58349403
    # if /usr/include is not found then default header libraries directory are probably moved to /usr/local/include
    # if stdio.h is missing from default header libraries directory then we need to symlink them from the commandline tool sdk

    if not os.path.exists(os.path.join('/', 'usr', 'include')):
        if not os.path.exists(os.path.join('/', 'usr', 'local', 'include', 'stdio.h')):
            raise FileNotFoundError('could not find standard library for clang please run the following command in a terminal:\n'
                                    f'\t"sudo ln -s {system_header_path}/usr/include/* /usr/local/include/"')

    else:
        if not os.path.exists(os.path.join('usr', 'include', 'stdio.h')):
            raise FileNotFoundError("could not find standard library for clang please run the following command in a terminal:\n"
                                    f'\t"sudo ln -s {system_header_path}/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/* /usr/include/"')

    # these flags are set so that make can see the header files stored in MacOSX.sdk see https://stackoverflow.com/a/58359366
    os.environ['CFLAGS'] = os.environ.get('CFLAGS', "") + f' -isysroot {system_header_path}'
    os.environ['CCFLAGS'] = os.environ.get('CCFLAGS', "") + f' -isysroot {system_header_path}'
    os.environ['CXXFLAGS'] = os.environ.get('CXXFLAGS', "") + f' -isysroot {system_header_path}'
    os.environ['CPPFLAGS'] = os.environ.get('CPPFLAGS', "") + f' -isysroot {system_header_path}'


def check_output(*args, **kwargs):
    return subprocess.check_output(*args, **kwargs).decode("utf-8").strip()


def check_call(*args, **kwargs):
    return subprocess.check_call(*args, **kwargs)


def remove_directory(path):
    if os.path.exists(path):
        print(f"directory: {path} already exists in pykaldi/tools...")
        print("deleting folder for a clean build...")
        shutil.rmtree(path)


def run_custom_command(command_list, cwd=CWD):
    print(f'Running command: {" ".join(command_list)}')
    p = subprocess.Popen(command_list, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # Can use communicate(input='y\n'.encode()) if the command run requires
    # some confirmation.
    while p.returncode is None:
        for pline in p.stdout:
            print(pline.decode(), end='')  # set returncode if the process has exited
        p.poll()
    if p.returncode != 0:
        raise RuntimeError('Command %s failed: exit code: %s' % (command_list, p.returncode))


def install_system_dep():
    try:
        print("checking system dependencies...")
        if platform.system().startswith("Linux"):

            # python_packages are necessary as cmakeLists.txt (line 15~17) cannot find PythonInterp or PythonLibs from virtual env \

            # use sudo only if user is not root
            sudo_prefix = "" if os.geteuid() != 0 else "sudo "

            check_call(f'{sudo_prefix}apt-get install autoconf automake cmake curl g++ git graphviz libatlas3-base libtool make pkg-config subversion unzip wget zlib1g-dev '
                       'python3-dev python3-pip python3-tk python3-lxml python3-six'.split())

        elif platform.system() == "Darwin":
            run_custom_command(['bash', 'install_dependencies_osx.sh'], cwd=os.path.join(CWD, 'tools'))
        else:
            print("\npykaldi is only compatible with linux or OS X", file=sys.stderr)
            sys.exit(1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)


def install_clif_dep():

    """look for pyclif if not found try and install pyclif, if install fails then exit setup process"""
    try:
        pyclif_path = find_clif_dep()
        clif_matcher_path = find_clif_matcher()
        print("clif_dep found")
        print(f"{pyclif_path}")
        print(f"{clif_matcher_path}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            print("\nCould not find pyclif.\nattempting to install it..", file=sys.stderr)
            remove_directory(os.path.join(CWD, 'tools', 'protobuf'))
            remove_directory(os.path.join(CWD, 'tools', 'clif'))
            remove_directory(os.path.join(CWD, 'tools', 'clif_backend'))

            print("\ninstalling pyclif dependency (protobuf)...", file=sys.stderr)
            run_custom_command(["bash", "install_protobuf.sh"], cwd=os.path.join(CWD, 'tools'))

            print("\ninstalling pyclif...", file=sys.stderr)
            run_custom_command(["./install_clif.sh"], cwd=os.path.join(CWD, 'tools'))

            print("\nrecheck clif dep...", file=sys.stderr)
            pyclif_path = find_clif_dep()
            clif_matcher_path = find_clif_matcher()
        except (subprocess.CalledProcessError, FileNotFoundError):
            traceback.print_exc()
            sys.exit(1)
    return pyclif_path, clif_matcher_path


def find_clif_dep():
    pyclif_path = os.getenv("PYCLIF")
    if not pyclif_path:
        pyclif_path = os.path.join(sys.prefix, 'bin/pyclif')
    pyclif_path = os.path.abspath(pyclif_path)

    if not (os.path.isfile(pyclif_path) and os.access(pyclif_path, os.X_OK)):
        raise FileNotFoundError("Could not find pyclif. Please make sure PYCLIF was installed "
                                "under the current python environment or set PYCLIF environment variable.")
    return pyclif_path


def find_clif_matcher():
    clif_matcher_path = os.getenv('CLIF_MATCHER')
    if not clif_matcher_path:
        clif_matcher_path = os.path.join(sys.prefix, 'clang/bin/clif-matcher')
    clif_matcher_path = os.path.abspath(clif_matcher_path)

    if not (os.path.isfile(clif_matcher_path) and os.access(clif_matcher_path, os.X_OK)):
        raise FileNotFoundError("Could not find clif-matcher. Please make sure CLIF was installed "
                                "under the current python environment or set CLIF_MATCHER environment variable.")
    return clif_matcher_path


def install_kaldi():
    try:
        kaldi_dir, kaldi_mk_path = find_kaldi()
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\nCould not find pykaldi or kaldi version out of date.\nattempting to install it..", file=sys.stderr)
        try:
            remove_directory(os.path.join(CWD, 'tools', 'kaldi'))
            run_custom_command(["bash", "install_kaldi.sh"], cwd=os.path.join(CWD, 'tools'))
            kaldi_dir, kaldi_mk_path = find_kaldi()
        except Exception as e:
            print(f"\nattempt to install kaldi failed.. {repr(e)}", file=sys.stderr)
            sys.exit(1)
    return kaldi_dir, kaldi_mk_path


def find_kaldi():
    kaldi_dir = os.getenv('KALDI_DIR')
    if not kaldi_dir:
        kaldi_dir = os.path.join(CWD, "tools/kaldi")
    kaldi_dir = os.path.abspath(kaldi_dir)

    kaldi_mk_path = os.path.join(kaldi_dir, "src", "kaldi.mk")

    if not os.path.isfile(kaldi_mk_path):
        raise FileNotFoundError("Could not find Kaldi. Please install Kaldi under the tools "
                                "directory or set KALDI_DIR environment variable.")

    kaldi_head = check_output(['git', '-C', kaldi_dir, 'rev-parse', 'HEAD'])
    run_custom_command(['git', '-C', kaldi_dir, 'merge-base', '--is-ancestor', KALDI_MIN_REQUIRED, kaldi_head])

    return kaldi_dir, kaldi_mk_path


################################################################################
# Set minimum version requirements for external dependencies
################################################################################

KALDI_MIN_REQUIRED = '5dc5d41bb603ba935c6244c7b32788ea90b9cee3'

################################################################################
# Check variables / find programs
################################################################################

DEBUG = os.getenv('DEBUG', 'NO').upper() in ['ON', '1', 'YES', 'TRUE', 'Y']

if platform.system() == 'Darwin':
    run_macos_clang_setup()

install_system_dep()
BUILD_DIR = os.path.join(CWD, 'build')

PYCLIF, CLIF_MATCHER = install_clif_dep()
KALDI_DIR, KALDI_MK_PATH = install_kaldi()

CLANG = os.path.join(os.path.dirname(CLIF_MATCHER), "clang")
RESOURCE_DIR = check_output("echo '#include <limits.h>' | {} -xc -v - 2>&1 "
                            "| tr ' ' '\n' | grep -A1 resource-dir | tail -1".format(CLANG), shell=True)
CLIF_CXX_FLAGS = "-I{}/include".format(RESOURCE_DIR)

with open("Makefile", "w") as makefile:
    print("include {}".format(KALDI_MK_PATH), file=makefile)
    print("print-% : ; @echo $($*)", file=makefile)
CXX_FLAGS = check_output(['make', 'print-CXXFLAGS'])
LD_FLAGS = check_output(['make', 'print-LDFLAGS'])
LD_LIBS = check_output(['make', 'print-LDLIBS'])
CUDA = check_output(['make', 'print-CUDA']).upper() == 'TRUE'
if CUDA:
    CUDA_LD_FLAGS = check_output(['make', 'print-CUDA_LDFLAGS'])
    CUDA_LD_LIBS = check_output(['make', 'print-CUDA_LDLIBS'])
subprocess.check_call(["rm", "Makefile"])

TFRNNLM_LIB_PATH = os.path.join(KALDI_DIR, "src", "lib", "libkaldi-tensorflow-rnnlm.so")
KALDI_TFRNNLM = True if os.path.exists(TFRNNLM_LIB_PATH) else False
if KALDI_TFRNNLM:
    with open("Makefile", "w") as makefile:
        TF_DIR = os.path.join(KALDI_DIR, "tools", "tensorflow")
        print("TENSORFLOW = {}".format(TF_DIR), file=makefile)
        TFRNNLM_MK_PATH = os.path.join(KALDI_DIR, "src", "tfrnnlm", "Makefile")
        for line in open(TFRNNLM_MK_PATH):
            if line.startswith("include") or line.startswith("TENSORFLOW"):
                continue
            print(line, file=makefile, end='')
        print("print-% : ; @echo $($*)", file=makefile)
    TFRNNLM_CXX_FLAGS = check_output(['make', 'print-EXTRA_CXXFLAGS'])
    TF_LIB_DIR = os.path.join(KALDI_DIR, "tools", "tensorflow", "bazel-bin", "tensorflow")
    subprocess.check_call(["rm", "Makefile"])

if platform.system() == "Darwin":
    XCODE_TOOLCHAIN_DIR = "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain"
    COMMAND_LINE_TOOLCHAIN_DIR = "/Library/Developer/CommandLineTools"
    if os.path.isdir(XCODE_TOOLCHAIN_DIR):
        TOOLCHAIN_DIR = XCODE_TOOLCHAIN_DIR
    elif os.path.isdir(COMMAND_LINE_TOOLCHAIN_DIR):
        TOOLCHAIN_DIR = COMMAND_LINE_TOOLCHAIN_DIR
    else:
        print("\nCould not find toolchain directory!\nInstall xcode command "
              "line tools, e.g. xcode-select --install", file=sys.stderr)
        sys.exit(1)
    CXX_SYSTEM_INCLUDE_DIR = os.path.join(TOOLCHAIN_DIR, "usr/include/c++/v1")
    CLIF_CXX_FLAGS += " -isystem {}".format(CXX_SYSTEM_INCLUDE_DIR)
    LD_FLAGS += " -undefined dynamic_lookup"
elif platform.system() == "Linux":
    CXX_FLAGS += " -Wno-maybe-uninitialized"
    LD_FLAGS += " -Wl,--as-needed"
    if DEBUG:
        LD_FLAGS += " -Wl,--no-undefined"

MAKE_NUM_JOBS = os.getenv('MAKE_NUM_JOBS')
if not MAKE_NUM_JOBS:
    # This is the logic ninja uses to guess the number of parallel jobs.
    NPROC = int(check_output(['getconf', '_NPROCESSORS_ONLN']))
    if NPROC < 2:
        MAKE_NUM_JOBS = '2'
    elif NPROC == 2:
        MAKE_NUM_JOBS = '3'
    else:
        MAKE_NUM_JOBS = str(NPROC + 2)
MAKE_ARGS = ['-j', MAKE_NUM_JOBS]
try:
    import ninja

    CMAKE_GENERATOR = '-GNinja'
    MAKE = 'ninja'
    if DEBUG:
        MAKE_ARGS += ['-v']
except ImportError:
    CMAKE_GENERATOR = ''
    MAKE = 'make'
    if DEBUG:
        MAKE_ARGS += ['-d']

if DEBUG:
    print("#" * 50)
    print("CWD:", CWD)
    print("PYCLIF:", PYCLIF)
    print("CLIF_MATCHER:", CLIF_MATCHER)
    print("KALDI_DIR:", KALDI_DIR)
    print("CXX_FLAGS:", CXX_FLAGS)
    print("CLIF_CXX_FLAGS:", CLIF_CXX_FLAGS)
    print("LD_FLAGS:", LD_FLAGS)
    print("LD_LIBS:", LD_LIBS)
    print("BUILD_DIR:", BUILD_DIR)
    print("CUDA:", CUDA)
    if CUDA:
        print("CUDA_LD_FLAGS:", CUDA_LD_FLAGS)
        print("CUDA_LD_LIBS:", CUDA_LD_LIBS)
    print("MAKE:", MAKE, *MAKE_ARGS)
    print("#" * 50)

print("preprocess finished without major issues.")

################################################################################
# Use CMake to build Python extensions in parallel
################################################################################

class Extension(setuptools.extension.Extension):
    """Dummy extension class that only holds the name of the extension."""

    def __init__(self, name):
        setuptools.extension.Extension.__init__(self, name, [])
        self._needs_stub = False

    def __str__(self):
        return "Extension({})".format(self.name)


class build(distutils.command.build.build):
    def finalize_options(self):
        self.build_base = 'build'
        self.build_lib = 'build/lib'
        distutils.command.build.build.finalize_options(self)


class build_ext(setuptools.command.build_ext.build_ext):
    def run(self):
        old_inplace, self.inplace = self.inplace, 0

        import numpy as np
        CMAKE_ARGS = ['-DKALDI_DIR=' + KALDI_DIR, '-DPYCLIF=' + PYCLIF, '-DCLIF_MATCHER=' + CLIF_MATCHER, '-DCXX_FLAGS=' + CXX_FLAGS, '-DCLIF_CXX_FLAGS=' + CLIF_CXX_FLAGS, '-DLD_FLAGS=' + LD_FLAGS,
                      '-DLD_LIBS=' + LD_LIBS, '-DNUMPY_INC_DIR=' + np.get_include(), '-DCUDA=TRUE' if CUDA else '-DCUDA=FALSE', '-DTFRNNLM=TRUE' if KALDI_TFRNNLM else '-DTFRNNLM=FALSE',
                      '-DDEBUG=TRUE' if DEBUG else '-DDEBUG=FALSE']

        if CUDA:
            CMAKE_ARGS += ['-DCUDA_LD_FLAGS=' + CUDA_LD_FLAGS, '-DCUDA_LD_LIBS=' + CUDA_LD_LIBS]

        if KALDI_TFRNNLM:
            CMAKE_ARGS += ['-DTFRNNLM_CXX_FLAGS=' + TFRNNLM_CXX_FLAGS, '-DTF_LIB_DIR=' + TF_LIB_DIR]

        if CMAKE_GENERATOR:
            CMAKE_ARGS += [CMAKE_GENERATOR]

        if DEBUG:
            CMAKE_ARGS += ['-DCMAKE_VERBOSE_MAKEFILE:BOOL=ON']
        else:
            CMAKE_ARGS += ['-Wno-dev']

        if not os.path.exists(BUILD_DIR):
            os.makedirs(BUILD_DIR)

        try:
            subprocess.check_call(['cmake', '..'] + CMAKE_ARGS, cwd=BUILD_DIR)
            subprocess.check_call([MAKE] + MAKE_ARGS, cwd=BUILD_DIR)
        except subprocess.CalledProcessError as err:
            # We catch this exception to disable stack trace.
            print(str(err), file=sys.stderr)
            sys.exit(1)
        print()  # Add an empty line for cleaner output

        self.extensions = self.populate_extension_list()

        if DEBUG:
            for ext in self.extensions:
                print(ext)
            self.verbose = True

        self.inplace = old_inplace
        if old_inplace:
            self.copy_extensions_to_source()

    def populate_extension_list(self):
        extensions = []
        lib_dir = os.path.join(BUILD_DIR, "lib")
        for dirpath, _, filenames in os.walk(os.path.join(lib_dir, "kaldi")):

            lib_path = os.path.relpath(dirpath, lib_dir)

            if lib_path == ".":
                lib_path = "kaldi"

            for f in filenames:
                r, e = os.path.splitext(f)
                if e == ".so":
                    ext_name = "{}.{}".format(lib_path, r)
                    extensions.append(Extension(ext_name))
        return extensions

    def get_ext_filename(self, fullname):
        """Convert the name of an extension (eg. "foo.bar") into the name
        of the file from which it will be loaded (eg. "foo/bar.so"). This
        patch overrides platform specific extension suffix with ".so".
        """
        ext_path = fullname.split('.')
        ext_suffix = '.so'
        return os.path.join(*ext_path) + ext_suffix


class build_sphinx(Command):
    user_options = []
    description = "Builds documentation using sphinx."

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        try:
            import sphinx
            subprocess.check_call([MAKE, 'docs'], cwd=BUILD_DIR)
        except ImportError:
            print("Sphinx was not found. Install it using pip install sphinx.", file=sys.stderr)
            sys.exit(1)


class install_lib(setuptools.command.install_lib.install_lib):
    def install(self):
        self.build_dir = 'build/lib'
        setuptools.command.install_lib.install_lib.install(self)


class test_cuda(setuptools.command.test.test):
    def run_tests(self):
        from kaldi.cudamatrix import cuda_available
        if cuda_available():
            from kaldi.cudamatrix import CuDevice
            CuDevice.instantiate().set_debug_stride_mode(True)
            CuDevice.instantiate().select_gpu_id("yes")
            super(test_cuda, self).run_tests()
            CuDevice.instantiate().print_profile()
        else:
            print("CUDA not available. Running tests on CPU.")
            super(test_cuda, self).run_tests()


################################################################################
# Setup pykaldi
################################################################################

# We add a 'dummy' extension so that setuptools runs the build_ext step.
extensions = [Extension("kaldi")]

packages = find_packages(exclude=["tests.*", "tests"])

setup(name='pykaldi', version='0.1.2', description='A Python wrapper for Kaldi', author='Dogan Can, Victor Martinez', ext_modules=extensions,
      cmdclass={'build': build, 'build_ext': build_ext, 'build_sphinx': build_sphinx, 'install_lib': install_lib, 'test_cuda': test_cuda, }, packages=packages, package_data={},
      install_requires=['numpy', 'pyparsing'], setup_requires=['pytest-runner'], tests_require=['pytest'], zip_safe=False, test_suite='tests')
