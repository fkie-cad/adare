# django imports
from django.conf import settings
import django

# internal imports
import adare.django_settings.settings as dj_settings


def django_setup():
    settings.configure(default_settings=dj_settings)
    django.setup()
