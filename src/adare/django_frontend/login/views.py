# django imports
from django.utils.timezone import make_aware
from rest_framework import status
from rest_framework import views
from rest_framework.response import Response

# external imports
import requests
import datetime

# internal imports
from adare.django_frontend.login.serializers import UserSessionSerializer
from adare.django_frontend.login.models import UserSession
from adare.config.server import WEBSERVER_URL
from adare.helperFunctions.django.orm import get_or_none


def is_logged_in(username: str) -> bool:
    """
    Checks if a user is logged in
    :param username:  username of the user
    :return:   True if user is logged in, False otherwise
    """
    user_session_instance = get_or_none(UserSession, username=username)
    if user_session_instance:
        if user_session_instance.expirationdate > make_aware(datetime.datetime.now()):
            return True
        else:
            user_session_instance.delete()
    return False


def get_actual_user_session() -> UserSession or None:
    queryset_usersession = UserSession.objects.all()
    if queryset_usersession.count() != 1:
        return None
    user_session = queryset_usersession.first()
    if not is_logged_in(user_session.username):
        return None
    return user_session


class LoginView(views.APIView):

    def post(self, request):
        request_data_keys = request.data.keys()
        if 'username' not in request_data_keys or 'password' not in request_data_keys:
            return Response(f'request is missing username and/or password')
        username = request.data['username']
        data = {
            'username': username,
            'password': request.data['password']
        }
        if is_logged_in(data['username']):
            # already logged in
            return Response(f'User {username} is already logged in')

        session = requests.session()
        req = session.post(f'{WEBSERVER_URL}/login/', data=data)
        response_data = req.json()
        if req.status_code == 200:
            # successful login
            token_cookie = response_data['token']
            expiry = datetime.datetime.strptime(response_data['expiry'], '%Y-%m-%dT%H:%M:%S.%fZ')
            expiration_date = make_aware(expiry)
            session_data = {
                'username': username,
                'token': token_cookie,
                'expirationdate': expiration_date,
            }
            serializer = UserSessionSerializer(data=session_data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(f'User {username} logged in successfully')
        else:
            # wrong credentials
            return Response(f'Wrong username or password. Try again')


class LogoutView(views.APIView):

    def post(self, request):
        username = request.data['username']
        if is_logged_in(username):
            user_session_instance = get_or_none(UserSession, username=username)
            user_session_instance.delete()
            return Response(f'user {username} successfully logged out')
        else:
            return Response(f'No user is logged in')