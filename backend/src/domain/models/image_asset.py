from pydantic import BaseModel


class ImageAsset(BaseModel):
    #: Stored file name, which image segments and B-roll refer to.
    file: str
    #: Name shown to the user.
    name: str
