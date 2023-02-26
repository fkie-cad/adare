from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.template import loader
from pathlib import Path

from adare.django_adareGUI.models import Experiment, OsInfo, Test


def index(request):
    template = loader.get_template('index.html')
    context = {
        'os_list': list(dict.fromkeys([os.os for os in OsInfo.objects.all()]))
    }
    return HttpResponse(template.render(context, request))


def getDistributions(request):
    os = request.GET.get('os', default=None)
    response_data = {}
    if os:
        os_obj = OsInfo.objects.filter(os=os)
        distributions = [
            os.distribution for os in os_obj
        ]
        response_data['distributions'] = list(dict.fromkeys(distributions))
    else:
        response_data['distributions'] = []
    return JsonResponse(response_data)

def getVersions(request):
    os = request.GET.get('os', default=None)
    dist = request.GET.get('dist', default=None)
    response_data = {}
    if os:
        os_obj = OsInfo.objects.filter(os=os, distribution=dist)
        versions = [
            os.version for os in os_obj
        ]
        response_data['versions'] = list(dict.fromkeys(versions))
    else:
        response_data['versions'] = []
    return JsonResponse(response_data)


def getExperiments(request):
    os = request.GET.get('os', default=None)
    dist = request.GET.get('dist', default=None)
    version = request.GET.get('version', default=None)
    filter_dict = {}
    if os:
        filter_dict['os'] = os
    if dist:
        filter_dict['distribution'] = dist
    if version:
        filter_dict['version'] = version

    response_data = {}
    os_objects = OsInfo.objects.filter(**filter_dict)
    exp = []
    for os_obj in os_objects:
        exp += Experiment.objects.filter(os_info=os_obj)

    exp2 = [{'name': e.name,
             'uuid': e.uuid,
             'timestamp_start': e.timestamp_start,
             'timestamp_end': e.timestamp_end,
             'os': e.os_info.os,
             'distribution': e.os_info.distribution,
             'version': e.os_info.version,
             # 'experiment_link':
    } for e in exp]
    response_data['data'] = exp2
    return JsonResponse(response_data)


def get_logfile_content(logfile_path: str or None):
    if not logfile_path:
        return None
    if Path(logfile_path).is_file():
        with open(logfile_path, mode='r') as f:
            return f.read()
    else:
        return None

def experiment(request):
    uuid = request.GET.get('uuid', default=None)
    exp = Experiment.objects.get(uuid=uuid)
    template = loader.get_template('experiment.html')
    duration = exp.timestamp_end - exp.timestamp_start

    STATUSNAME_COLOR_MAPPING = {
        'success': 'success',
        'failed': 'danger',
        'warning': 'warning',
        'not reached': 'gray-400'
    }
    STATUSNAME_SYMBOL_MAPPING = {
        'success': 'check-square',
        'failed': 'x-square',
        'warning': 'exclamation-square',
        'not reached': 'exclamation-square',
        #'not reached': 'question-square',
    }

    log_vg = get_logfile_content(exp.logfile_vagrant)
    log_parse_and_test = get_logfile_content(exp.logfile_parse_and_test)
    log_gui = get_logfile_content(exp.logfile_gui_automation)
    log_postsetup_installations = get_logfile_content(exp.logfile_postsetup_installations)
    log_installed_packages = get_logfile_content(exp.logfile_installed_packages)

    tests = []
    for t in exp.tests.all():
        test = {
            'name': t.name,
            'uuid': t.uuid,
            'description': t.description,
            'testfunction_name': t.testfunction.name,
            'testfunction_test_name': t.testfunction.test_name,
            'testfunction_test_description': t.testfunction.test_description,
            'parameters': [
                {
                    'parameter_name': p.parameter.name,
                    'parameter_dtype': p.parameter.dtype,
                    'value': p.value
                } for p in t.parameters.all()
            ],
            'result_status': t.result.status.name,
            'result_details': t.result.details,
            # 'result_details_bg_class':  'bg-dark' if not t.result.details else '',
            'result_color': STATUSNAME_COLOR_MAPPING[t.result.status.name],
            'result_symbol': STATUSNAME_SYMBOL_MAPPING[t.result.status.name],
            # 'tool_bg_class': 'bg-dark' if not t.tool else '',
            'tool_name': t.tool.name if t.tool else '',
            'tool_command': t.tool.command if t.tool else '',
        }
        tests.append(test)

    context = {
        'name': exp.name,
        'uuid': exp.uuid,
        'os': exp.os_info.os,
        'distribution': exp.os_info.distribution,
        'version': exp.os_info.version,
        'language': exp.os_info.language,
        'architecture': exp.os_info.architecture if exp.os_info.architecture else '-',
        'timestamp_start': exp.timestamp_start,
        'duration': duration,
        'status_color': STATUSNAME_COLOR_MAPPING[exp.status.name],
        'status_symbol': STATUSNAME_SYMBOL_MAPPING[exp.status.name],
        'status_vg_color': STATUSNAME_COLOR_MAPPING[exp.status_vagrant.name],
        'status_vg_symbol': STATUSNAME_SYMBOL_MAPPING[exp.status_vagrant.name],
        'status_gui_color': STATUSNAME_COLOR_MAPPING[exp.status_gui_automation.name],
        'status_gui_symbol': STATUSNAME_SYMBOL_MAPPING[exp.status_gui_automation.name],
        'status_parseandtest_color': STATUSNAME_COLOR_MAPPING[exp.status_parse_and_test.name],
        'status_parseandtest_symbol': STATUSNAME_SYMBOL_MAPPING[exp.status_parse_and_test.name],
        'logfile_vagrant': log_vg,
        'logfile_parse_and_test': log_parse_and_test,
        'logfile_gui_automation': log_gui,
        'logfile_postsetup_installations': log_postsetup_installations,
        'logfile_installed_packages': log_installed_packages,
        'logfile_mount_networkdrives': None,
        'tests': tests
    }
    return HttpResponse(template.render(context, request))
