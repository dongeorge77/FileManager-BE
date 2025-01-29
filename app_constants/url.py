class BaseUrl:
    base_url = "/api/v1"

class Routes:
    user: str = f"{BaseUrl.base_url}/user"
    files: str = f"{BaseUrl.base_url}/files"
    folders: str = f"{BaseUrl.base_url}/folders"
    items: str = f"{BaseUrl.base_url}/items"


class UserAPI:
    login: str = "/login"
    create_user: str = "/create_user"
    profile = "/profile"
    share = "/shared/{share_token}"

class FilesAPI:
    upload: str = "/upload"
    share: str = "/{file_id}/share"
    preview: str = "/preview/{file_id}"

class FolderAPI:
    list_directory: str = "/list_directory"
    create: str = "/create"

class ItemsAPI:
    delete: str = "/delete"
    move: str = "/move"
    copy: str = "/copy"
    rename: str = "/rename"

