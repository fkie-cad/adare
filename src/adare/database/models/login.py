from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime
from sqlalchemy.orm import relationship, backref, DeclarativeBase

class Base(DeclarativeBase):
    pass

class UserSession(Base):
    __tablename__ = 'user_session'
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True)
    token = Column(String)
    expirationdate = Column(DateTime)

    def __repr__(self):
        return f"<UserSession(username='{self.username}',token='{self.token}',expirationdate='{self.expirationdate}')>"
