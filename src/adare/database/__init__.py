from django.conf import settings
import django
import adare.django_settings.settings as dj_settings

settings.configure(default_settings=dj_settings, DEBUG=True)
django.setup()
