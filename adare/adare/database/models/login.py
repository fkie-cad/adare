from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from . import Base


class Token(Base):
    __tablename__ = 'token'
    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String, unique=True)
    expiration = Column(DateTime, nullable=True, default=None,)


class UserSession(Base):
    __tablename__ = 'user_session'
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True)
    gitea_token_id = Column(Integer, ForeignKey('token.id'))
    gitea_token = relationship('Token', foreign_keys=[gitea_token_id])
    django_token_id = Column(Integer, ForeignKey('token.id'), )
    django_token = relationship('Token', foreign_keys=[django_token_id])
    gitea_refresh_token_id = Column(Integer, ForeignKey('token.id'), nullable=True, default=None,)
    gitea_refresh_token = relationship('Token', foreign_keys=[gitea_refresh_token_id])


