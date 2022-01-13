from typing import Iterable
from dateutil import parser

from fs import ResourceType, tools
from fs.base import FS
from fs import errors
from fs.info import Info
from fs.mode import Mode
from fs.permissions import Permissions
from msgraphy import GraphApi
from msgraphy.auth.graph_auth import BasicAuth
from msgraphy.client.graph_client import GraphClient, RequestsGraphClient
from msgraphy.data import ApiIterable
from msgraphy.data.file import DriveItem

from msgraphyfs.file import MSGraphyFile


class MSGraphyFS(FS):

    def __init__(self, client: GraphClient, path: str, writeable: bool = False):
        super(MSGraphyFS, self).__init__()
        self.__client = client
        self.__api = GraphApi(client)
        self.__writeable = writeable

        if isinstance(path, DriveItem):
            self.__drive_item = path
        else:
            try:
                self.__drive_item = self.__api.files.parse_drive_item(path).value
            except Exception as e:
                raise errors.CreateFailed(f"Could not open {path}: {e}") from e

    def _clean_path(self, path):
        while len(path) > 0 and path[0] in ["/", "."]:
            path = path[1:]
        return path

    def _get_item_url(self, path):
        path = self._clean_path(path)

        url = self.__drive_item.get_api_reference()

        if path == "":
            return url
        else:
            return f"{url}:/{path}:"

    def _get_item(self, path: str) -> DriveItem:
        path = self._clean_path(path)
        if path == "":
            item = self.__drive_item
        else:
            url = self._get_item_url(path)
            response = self.__client.make_request(url, response_type=DriveItem)
            if response.response.status_code == 404:
                raise errors.ResourceNotFound(path)
            item = response.value
        return item

    def getinfo(self, path: str, namespaces: Iterable[str] = None) -> Info:
        """Get information about a resource on a filesystem.

        Arguments:
            path (str): A path to a resource on the filesystem.
            namespaces (list, optional): Info namespaces to query. The
                `"basic"` namespace is always included in the returned
                info, whatever the value of `namespaces` may be.

        Returns:
            ~fs.info.Info: resource information object.

        Raises:
            fs.errors.ResourceNotFound: If ``path`` does not exist.

        For more information regarding resource information, see :ref:`info`.

        """
        item = self._get_item(path)
        return Info(dict(
            basic=dict(
                name=item.name,
                is_dir=item.folder is not None,
            ),
            details=dict(
                created=item.created_date_time,
                modified=item.last_modified_date_time,
                size=item.size,
                type=ResourceType.file if item.file is not None else ResourceType.directory if item.folder is not None else ResourceType.unknown,
            ),
        ), to_datetime=lambda d: parser.parse(d) if d is not None else None)

    def listdir(self, path: str):
        """Get a list of the resource names in a directory.

        This method will return a list of the resources in a directory.
        A *resource* is a file, directory, or one of the other types
        defined in `~fs.enums.ResourceType`.

        Arguments:
            path (str): A path to a directory on the filesystem

        Returns:
            list: list of names, relative to ``path``.

        Raises:
            fs.errors.DirectoryExpected: If ``path`` is not a directory.
            fs.errors.ResourceNotFound: If ``path`` does not exist.

        """
        response_type = ApiIterable(self.__client, DriveItem)

        url = self._get_item_url(path)
        response = self.__client.make_request(f"{url}/children", response_type=response_type)
        item = response.value
        return [f"{item.name}" for item in item]

    def makedir(self, path: str, permissions: Permissions = None, recreate: bool = False):
        path = self._clean_path(path)
        if path == "":
            return self

        dir_paths = path.rsplit("/", 1)

        if len(dir_paths) == 1:
            item_path = ""
            name = dir_paths[0]
        else:
            item_path = dir_paths[0]
            name = dir_paths[1]

        url = self._get_item_url(item_path)

        body = {
            "name": name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "replace" if recreate else "fail",
        }
        response = self.__client.make_request(f"{url}/children", response_type=DriveItem, method="POST", json=body)
        if response.response.status_code == 409:
            raise errors.DirectoryExists(path)
        return MSGraphyFS(self.__client, response.value, writeable=self.__writeable)

    def makedirs(self, path: str, permissions: Permissions = None, recreate: bool = False):
        dir_paths = path.split("/")
        parent_fs = self
        for ix, dir_path in enumerate(dir_paths):
            if ix < len(dir_paths) - 1:
                _recreate = True
            else:
                _recreate = recreate
            parent_fs = parent_fs.makedir(dir_path, permissions, _recreate)
        return parent_fs

    def openbin(self, path: str, mode="r", buffering=-1, **options):
        _mode = Mode(mode)
        _mode.validate_bin()

        url = self._get_item_url(path)

        if _mode.reading:
            response = self.__client.make_request(f"{url}/content", stream=True)
            return response.response.raw

        try:
            file_info = self.getinfo(path)
        except errors.ResourceNotFound:
            file_info = None

        if _mode.exclusive and file_info:
            raise errors.FileExists(f"{path} already exists")

        return MSGraphyFile(self.__api, self.__drive_item, path, _mode)

    def remove(self, path):
        item = self._get_item(path)
        if item.file is None:
            raise errors.FileExpected(path)
        response = self.__client.make_request(item.get_api_reference(), method="DELETE")
        response.response.raise_for_status()

    def removedir(self, path, check_empty=True):
        item = self._get_item(path)
        if item.folder is None:
            raise errors.DirectoryExpected(path)
        if item.id == self.__drive_item.id:
            raise errors.RemoveRootError(path)
        if check_empty:
            children = self.listdir(path)
            if len(children) > 0:
                raise errors.DirectoryNotEmpty(path)

        response = self.__client.make_request(item.get_api_reference(), method="DELETE")
        response.response.raise_for_status()

    def setinfo(self):  # Set resource information
        pass

    def __repr__(self):
        return f"{self.__class__.__name__}()"


def get_default_client(writeable: bool = False) -> GraphClient:
    return RequestsGraphClient(BasicAuth(scopes='Files.ReadWrite.All' if writeable else 'Files.Read.All'))
