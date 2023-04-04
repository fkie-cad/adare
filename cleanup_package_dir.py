PACKAGE = r'adare'
PACKAGES_DIR = r'C:\\users\\kuelp\\appdata\\local\\programs\\python\\python310\\lib\\site-packages\\'

from pathlib import Path

import shutil

if __name__ == '__main__':
    package_dir = Path(PACKAGES_DIR)/PACKAGE
    if not package_dir.is_dir():
        print(f'package dir {package_dir} does not exist')
    for path in package_dir.rglob('~*'):
        shutil.rmtree(path.as_posix())
        print(f'{path} deleted')