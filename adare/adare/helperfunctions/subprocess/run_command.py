# external imports
from subprocess import Popen, PIPE
import os

# internal imports
from adare.helperFunctions.strings.replace import replace_multiple_strings

# configure logging
import logging
log = logging.getLogger(__name__)


def run_cmd(cmd: list, cwd: str, env: dict = None, quiet=False) -> int:
    env_vars = dict(os.environ.copy())
    if env:
        env_vars.update(env)

    proc = Popen(cmd, stdout=PIPE, stderr=PIPE, cwd=cwd, shell=False, env=env_vars)

    try:
        for line in proc.stdout:
            line = line.decode("utf-8", errors='ignore')
            line = replace_multiple_strings(line, ["\n", "\r"], " ")
            log.debug(line)
            if not quiet:
                print(line)
        for line in proc.stderr:
            line = line.decode("utf-8", errors='ignore')
            line = replace_multiple_strings(line, ["\n", "\r"], " ")
            log.error(line)
        proc.communicate()
    except KeyboardInterrupt:
        proc.kill()
    return proc.returncode


