from pathlib import Path
from tempfile import NamedTemporaryFile

from fs.iotools import RawWrapper
from fs.mode import Mode
from msgraphy import GraphApi
from msgraphy.client.graph_client import GraphResponse
from msgraphy.data.file import DriveItem, BaseItem
from msgraphy.domains.files import FilesGraphApi

_large_file_threshold = 4 * 1024 * 1024
_large_file_fragment_size = 327680
_large_file_fragment_target = _large_file_fragment_size * 25


class MSGraphyFile(RawWrapper):

    def __init__(self, api: GraphApi, parent_item: DriveItem, filename: str, mode: Mode):
        self.__api = api
        self.__parent_item = parent_item
        self.__filename = filename
        self.__file = NamedTemporaryFile()
        if mode.appending:
            response = self.__api.client.make_request(
                f"{self.__parent_item.get_api_reference()}:/{self.__filename}:/content",
                stream=True)
            if response.response.status_code < 300:
                for chunk in response.response.iter_content(chunk_size=8192):
                    self.__file.write(chunk)

        super(MSGraphyFile, self).__init__(self.__file, mode.to_platform())

    def close(self):
        if not self.closed:
            self.__file.flush()

            response = self._upload_file()
            response.response.raise_for_status()

            super(MSGraphyFile, self).close()

    def _upload_file(self) -> GraphResponse[DriveItem]:
        file = Path(self.__file.name)
        resource = f"{self.__parent_item.get_api_reference()}:/{self.__filename}:/createUploadSession"

        file_size = file.stat().st_size

        session_response = self.__api.client.make_request(url=resource, method="post", json=dict(fileSize=file_size))
        session_response_value = session_response.value
        upload_url = session_response_value['uploadUrl']

        with open(file, 'rb') as FILE:
            for pos in range(0, file_size, _large_file_fragment_target):
                data = FILE.read(_large_file_fragment_target)
                headers = {
                    "Content-Length": f"{len(data)}",
                    "Content-Range": f"bytes {pos}-{pos + len(data) - 1}/{file_size}",
                }
                session_response = self.__api.client.make_request(
                    url=upload_url,
                    method="put",
                    headers=headers,
                    data=data,
                    use_auth=False,
                    response_type=FilesGraphApi.MultiPartResponse,
                )

        return session_response
