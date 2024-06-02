import threading
import time

from adare.backend.experiment.print import ExperimentFlowConsole

if __name__ == '__main__':
    event = threading.Event()
    flow_console = ExperimentFlowConsole(event)

    try:
        flow_console.start()
        flow_console.log_success(identifier='s1', message='Success message')
        flow_console.log_warning(identifier='w1', message='Warning message')
        flow_console.log_error(identifier='e1', message='Error message')
        flow_console.log_interrupted(identifier='i1', message='Interrupted message')
        flow_console.log_spinner(identifier='sp1', message='Spinner message')
        flow_console.log_success(identifier='s2', message='Run Part 1', level=1)
        time.sleep(3)
        flow_console.log_spinner(identifier='sp2', message='Spinner message 2', spinner='dots', spinner_style='bold orange', level=1)
        flow_console.log_spinner_done(identifier='sp1', status='success')
        time.sleep(3)
        flow_console.log_spinner_done(identifier='sp2', status='error')

        while True:
            time.sleep(0.01)
    except KeyboardInterrupt:
        event.set()
        print('KeyboardInterrupt')
    finally:
        flow_console.stop()
        print('Thread joined')
