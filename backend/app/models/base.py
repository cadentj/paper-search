from sqlalchemy.orm import DeclarativeBase

# NOTE(cadentj): Subclasses of DeclarativeBase get their own registry / metadata,
# so we make a basic subclass that we use to register all our models.
class Base(DeclarativeBase):
    pass
