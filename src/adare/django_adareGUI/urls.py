from django.contrib import admin
from django.urls import path, include
import adare.django_adareGUI.views as views

urlpatterns = [
    # for admin side
    path('admin/', admin.site.urls),
]
