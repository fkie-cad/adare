"""django_webapp URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect

import adare.django_frontend.experiments.views as experiments_views
import adare.django_frontend.login.views as login_views

urlpatterns = [
    path('', lambda req: redirect('index/')),
    path('admin/', admin.site.urls),
    path('index/', experiments_views.index),
    path('get-distributions/', experiments_views.getDistributions, name='GetDistributions'),
    path('get-versions/', experiments_views.getVersions, name='GetVersions'),
    path('get-experiments/', experiments_views.getExperiments, name='GetExperiments'),
    path('experiment/', experiments_views.experiment),
    path('login/', login_views.LoginView.as_view()),
    path('logout/', login_views.LogoutView.as_view()),
    path('publish/', experiments_views.PublishView.as_view()),
    path('rm/', experiments_views.TestRemoveView.as_view()),
]