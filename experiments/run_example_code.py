import os
import shutil
from pathlib import Path
import textwrap

import py5_tools

from generator.docfiles import Documentation

PY5_API_EN = Path('/home/jim/Projects/ITP/pythonprocessing/py5development/py5_docs/Reference/api_en/')
DOC_DATA = Path('/home/jim/Projects/ITP/pythonprocessing/jdf-processing-py-site/data')
DEST_DIR = Path('/tmp/examples/')


def run_example(image, code):
    example_file = '/tmp/examples/' + image.replace('.png', '.py')
    print(example_file)
    extra_code = f"\nsave_frame('/tmp/examples/{image}')\nexit_sketch()\n"
    if py5_tools.run.SETUP_REGEX.match(code):
        extra_code = textwrap.indent(extra_code, prefix='    ')
    code += extra_code
    with open(example_file, 'w') as f:
        f.write(code)
    try:
        py5_tools.run_sketch(example_file, exit_if_error=True)
    except Exception as e:
        print(code)
        print(e)
        return False
    else:
        return True


cwd = os.getcwd()
if DEST_DIR.exists():
    shutil.rmtree(DEST_DIR)
DEST_DIR.mkdir(exist_ok=True)
shutil.copytree(DOC_DATA, DEST_DIR / 'data')
os.chdir(DEST_DIR)

for docfile in sorted(PY5_API_EN.glob('*.txt')):
    doc = Documentation(docfile)
    for image, code in doc.examples:
        if image:
            run_example(image, code)

os.chdir(cwd)