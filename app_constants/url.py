class BaseUrl:
    base_url: str = "/api/v1"

class Routes:
    user: str = f"{BaseUrl.base_url}/user"
    files: str = f"{BaseUrl.base_url}/files"
    folders: str = f"{BaseUrl.base_url}/folders"
    items: str = f"{BaseUrl.base_url}/items"


class UserAPI:
    login: str = "/login"
    create_user: str = "/create_user"
    profile: str = "/profile"
    share: str = "/shared/{share_token}"
    list_users: str = "/list_users"
    update_user: str = "/update_user/{user_id}"
    delete_user: str = "/delete_user/{user_id}"
    user_metadata: str = "/metadata"

class FilesAPI:
    upload: str = "/upload"
    share: str = "/{file_id}/share"
    preview: str = "/preview/{file_id}"

class FolderAPI:
    list_directory: str = "/list_directory"
    create: str = "/create"
    clean_directory: str = "/clean_directory"

class ItemsAPI:
    delete: str = "/delete"
    move: str = "/move"
    copy: str = "/copy"
    rename: str = "/rename"

