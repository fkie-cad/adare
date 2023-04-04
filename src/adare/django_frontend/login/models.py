from django.db import models


class UserSession(models.Model):
    username = models.CharField(max_length=100)
    token = models.CharField(max_length=64)
    expirationdate = models.DateTimeField()