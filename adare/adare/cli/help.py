from adare.console import console
from adare.breakpoint import BREAKPOINTS, resolve_breakpoints, BreakPoint


def print_breakpoint_info(bp: BreakPoint, index: int, prefix_whitespace_count: int = 3):
    console.print(f'[b][i]bp{index}[/i][/b]: [i]{bp.name}[/i]', highlight=False)
    console.print(' ' * prefix_whitespace_count + f'{bp.description}', highlight=False)
    if bp.usage:
        console.print('\n' + ' ' * prefix_whitespace_count + 'Possible Usages:', highlight=False, style='')

        for index, usage in enumerate(bp.usage):
            print_string = ' ' * 2 * prefix_whitespace_count + f'([b][cyan]{index + 1}[/cyan][/b]) {usage}'
            console.print(print_string, highlight=False)
    console.print('-' * 80, highlight=False)


def exec_help_breakpoints(arguments):
    if not arguments.breakpoint:
        console.print('Breakpoints are used within adare experiment run to pause the execution at a specific point in the experiment.', highlight=False)
        console.print('The following breakpoints are available:\n', highlight=False)
        # enumerate breakpoints
        for i, bp in enumerate(BREAKPOINTS):
            print_breakpoint_info(bp, i + 1)
    else:
        bp = resolve_breakpoints([arguments.breakpoint])
        if len(bp) == 0:
            console.print(f'No breakpoint {arguments.breakpoint} found.', highlight=False)
            exit(-1)
        else:
            for breakpoint_obj in bp:
                bp_index = BREAKPOINTS.index(breakpoint_obj) + 1
                print_breakpoint_info(breakpoint_obj, bp_index)

