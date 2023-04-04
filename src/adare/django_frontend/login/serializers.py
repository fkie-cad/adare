# external imports
from rest_framework import serializers

# internal imports
from adare.django_frontend.login.models import UserSession


class UserSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSession
        fields = '__all__'
