import os
import shutil
from pathlib import Path
import textwrap

import py5_tools

from generator.docfiles import Documentation

PY5_API_EN = Path('py5_docs/Reference/api_en/').absolute()
DOC_DATA = Path('py5_docs/Reference/data')
DEST_DIR = Path('/tmp/examples/')


def run_example(image, code):
    example_file = DEST_DIR / image.replace('.png', '.py')
    print('*' * 20)
    print(example_file)
    if image == 'Sketch_curve_detail_0.png':
        # total hack
        code = code.replace('no_loop()', '')
        code = code.replace('\n\ndef draw_curves(y)', f"\n    save_frame('{DEST_DIR / image}')\n    exit_sketch()\n\ndef draw_curves(y)")
    elif image:
        extra_code = f"\nsave_frame('{DEST_DIR / image}')\nexit_sketch()\n"
        if py5_tools.run.SETUP_REGEX.search(code):
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