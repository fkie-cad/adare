from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.template import loader

from adare.django_adareGUI.models import Experiment, OsInfo


def index(request):
    template = loader.get_template('index.html')
    return HttpResponse(template.render())


def search(request):
    template = loader.get_template('search.html')
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
    } for e in exp]
    response_data['data'] = exp2
    return JsonResponse(response_data)