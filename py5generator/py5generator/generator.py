"""
py5 Generator Code

One might wonder why I didn't implement this using module __getattr__ and
__dir__ functions [PEP 562](https://www.python.org/dev/peps/pep-0562/). Doing
so would simplify the code considerably. I did in fact try that but then found
that code completion didn't work correctly in Visual Studio Code. The reason
why it doesn't work is because the Python extension is implemented in
typescript, and typescript cannot parse a Python module the same way IPython
can. It seems to use heuristics of some kind. This in itself is interesting
because you can trick it if you need to.
"""
import sys
import re
import pkgutil
import shlex
from pathlib import Path
import shutil


###############################################################################
# PYJNIUS SETUP
###############################################################################


def jnius_setup(classpath):
    import jnius_config
    jnius_config.set_classpath(
        '.',
        '/home/jim/Projects/ITP/pythonprocessing/sam_processing4/core/library/*',
    )
    from jnius import autoclass, find_javaclass, with_metaclass  # noqa
    from jnius import MetaJavaClass, JavaClass, JavaStaticMethod  # noqa

    # TODO: do I really need this stuff now that autoclass works better???
    class Modifier(with_metaclass(MetaJavaClass, JavaClass)):
        __javaclass__ = 'java/lang/reflect/Modifier'

        isAbstract = JavaStaticMethod('(I)Z')
        isFinal = JavaStaticMethod('(I)Z')
        isInterface = JavaStaticMethod('(I)Z')
        isNative = JavaStaticMethod('(I)Z')
        isPrivate = JavaStaticMethod('(I)Z')
        isProtected = JavaStaticMethod('(I)Z')
        isPublic = JavaStaticMethod('(I)Z')
        isStatic = JavaStaticMethod('(I)Z')
        isStrict = JavaStaticMethod('(I)Z')
        isSynchronized = JavaStaticMethod('(I)Z')
        isTransient = JavaStaticMethod('(I)Z')
        isVolatile = JavaStaticMethod('(I)Z')

    def identify_hierarchy(cls, level, concrete=True):
        supercls = cls.getSuperclass()
        if supercls is not None:
            for sup, lvl in identify_hierarchy(supercls, level + 1, concrete=concrete):
                yield sup, lvl  # we could use yield from when we drop python2
        interfaces = cls.getInterfaces()
        for interface in interfaces or []:
            for sup, lvl in identify_hierarchy(interface, level + 1, concrete=concrete):
                yield sup, lvl
        # all object extends Object, so if this top interface in a hierarchy, yield Object
        if not concrete and cls.isInterface() and not interfaces:
            yield find_javaclass('java.lang.Object'), level + 1
        yield cls, level

    Py5Applet = autoclass('processing.core.Py5Applet',
                          include_protected=False, include_private=False)
    c = find_javaclass('processing.core.Py5Applet')
    class_hierachy = list(identify_hierarchy(c, 0, not c.isInterface()))

    methods = set()
    fields = set()
    static_fields = set()

    for cls, _ in class_hierachy:
        for method in cls.getDeclaredMethods():
            name = method.getName()
            modifiers = method.getModifiers()
            if not Modifier.isPublic(modifiers):
                continue
            methods.add(name)

        for field in cls.getDeclaredFields():
            name = field.getName()
            modifiers = field.getModifiers()
            if not Modifier.isPublic(modifiers):
                continue
            if Modifier.isStatic(modifiers):
                static_fields.add(name)
            else:
                fields.add(name)

    # any field names that are also method names must be removed
    fields -= methods
    static_fields -= methods

    return Py5Applet, methods, fields, static_fields


###############################################################################
# TEMPLATES
###############################################################################


METHOD_TEMPLATE = """
def {0}(*args):
    return _papplet.{1}(*args)"""

STATIC_METHOD_TEMPLATE = """
def {0}(*args):
    return Py5Applet.{1}(*args)"""

DYNAMIC_VAR_TEMPLATE = """
    global {0}
    {0} = _papplet.{1}"""


###############################################################################
# REFERENCE AND LOOKUPS
###############################################################################


PAPPLET_SKIP_METHODS = {
    # main sketch methods
    'settings', 'setup', 'draw',
    # key and mouse events
    'keyPressed', 'keyTyped', 'keyReleased',
    'mouseClicked', 'mouseDragged', 'mouseMoved', 'mouseEntered',
    'mouseExited', 'mousePressed', 'mouseReleased', 'mouseWheel',
    # exit method
    'exitActual',
    # builtin python functions
    'print', 'exec', 'exit', 'str', 'set', 'map', 'sort',
    # user should use Python instead
    'append', 'arrayCopy', 'arraycopy', 'concat', 'expand', 'reverse', 'shorten',
    'splice', 'subset', 'binary', 'boolean', 'byte', 'char', 'float', 'hex',
    'int', 'unbinary', 'unhex', 'join', 'match', 'matchAll', 'nf', 'nfc', 'nfp',
    'nfs', 'split', 'splitTokens', 'trim', 'debug', 'delay', 'equals',
    # user should use numpy instead
    'min', 'max', 'round', 'map', 'abs', 'pow', 'sqrt', 'ceil', 'floor', 'log',
    'exp', 'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'atan2', 'degrees',
    'radians', 'sq',
    # public methods that should be skipped
    'runSketch', 'main', 'handleDraw', 'handleSettings', 'usePy5Methods',
    'registerMethod', 'unregisterMethod',
    'showDepthWarning', 'showDepthWarningXYZ', 'showMethodWarning',
    'showVariationWarning', 'showMissingWarning',
    'checkAlpha', 'setSize',
    'getClass',
}

PCONSTANT_OVERRIDES = {
    'WHITESPACE': r' \t\n\r\x0c\xa0',
    'ESC': r'\x1b',
    'RETURN': r'\r',
    'ENTER': r'\n',
    'DELETE': r'\x7f',
    'BACKSPACE': r'\x08',
    'TAB': r'\t'
}

DEPRECATED = {
    'firstMouse', 'mouseEvent', 'keyEvent', 'MACOSX'
}


###############################################################################
# UTIL FUNCTIONS
###############################################################################


def snake_case(name):
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name)
    return name.lower()


###############################################################################
# MAIN
###############################################################################


def generate_py5(dest_dir, dest_exist_ok=False, repo_dir=None, install_dir=None):
    """Generate the py5 library
    """

    print(f'generating py5 library...')
    search_dir = repo_dir or install_dir
    core_jars = list(search_dir.glob('**/core.jar'))
    if len(core_jars) != 1:
        if core_jars:
            print(f'more than one core.jar found in {search_dir}', file=sys.stderr)
        else:
            print(f'core.jar not found in {search_dir}', file=sys.stderr)
        return
    core_jar = core_jars[0]

    Py5Applet, methods, fields, static_fields = jnius_setup(core_jar)
    from jnius import MetaJavaClass, JavaClass, JavaStaticMethod  # noqa

    # code the static constants
    py5_constants = []
    for name in sorted(static_fields):
        if name in DEPRECATED:
            continue
        if name in PCONSTANT_OVERRIDES:
            py5_constants.append(f'{name} = {shlex.quote(PCONSTANT_OVERRIDES[name])}')
        else:
            val = getattr(Py5Applet, name)
            if isinstance(val, str):
                val = f"'{val}'"
            if name == 'javaVersion':
                val = round(val, 2)
            py5_constants.append(f'{name} = {val}')
    py5_constants_code = '\n'.join(py5_constants)

    # code the dynamic variables
    init_vars = []
    update_vars = []
    for name in sorted(fields):
        if name in DEPRECATED:
            continue
        snake_name = snake_case(name)
        init_vars.append(f'{snake_name} = None')
        update_vars.append(DYNAMIC_VAR_TEMPLATE.format(snake_name, name))
    py5_init_dynamic_var_code = '\n'.join(init_vars)
    py5_update_dynamic_var_code = ''.join(update_vars)[5:]

    # code the class and instance methods
    py5_functions = []
    for fname in sorted(methods):
        if fname in DEPRECATED or fname in PAPPLET_SKIP_METHODS:
            continue
        if isinstance(getattr(Py5Applet, fname), JavaStaticMethod):
            py5_functions.append(STATIC_METHOD_TEMPLATE.format(snake_case(fname), fname))
        else:
            py5_functions.append(METHOD_TEMPLATE.format(snake_case(fname), fname))
    py5_functions_code = '\n\n'.join(py5_functions)

    # complete the output template
    py5_template = pkgutil.get_data('py5generator', 'resources/templates/py5__init__.py').decode('utf-8')
    py5_code = py5_template.format(py5_constants_code,
                                   py5_init_dynamic_var_code,
                                   py5_update_dynamic_var_code,
                                   py5_functions_code)

    # build complete py5 module in destination directory
    # first validate the output directory
    print(f'writing py5 in {dest_dir}')
    if dest_dir.exists():
        if not dest_dir.is_dir():
            print(f'output destination {dest_dir} is not a directory.', file=sys.stderr)
            return
    else:
        dest_dir.mkdir(parents=True)
    output_dir = dest_dir / 'py5'
    if output_dir.exists():
        if dest_exist_ok:
            shutil.rmtree(output_dir)
        else:
            print(f'output destination {output_dir} already exists.', file=sys.stderr)
            return

    base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).absolute().parent))
    shutil.copytree(base_path / 'resources' / 'py5_module_framework' / '',
                    output_dir)
    for jar in core_jar.parent.glob('*.jar'):
        shutil.copy(jar, output_dir / 'py5' / 'jars')
    with open(output_dir / 'py5' / '__init__.py', 'w') as f:
        f.write(py5_code)

    print('done!')