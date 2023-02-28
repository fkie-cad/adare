from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # for admin side
    path('admin/', admin.site.urls),
]
