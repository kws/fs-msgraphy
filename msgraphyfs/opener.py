from fs.opener import Opener
from fs.opener.errors import OpenerError
from .fs import MSGraphyFS, get_default_client

__all__ = ['MSGraphyFSOpener']


def test_client(url):
    import fs
    from fs import open_fs
    fs.opener.registry.install(MSGraphyFSOpener)

    return open_fs(url)


class MSGraphyFSOpener(Opener):
    protocols = ['o365']

    def open_fs(self, fs_url, parse_result, writeable, create, cwd):
        if parse_result.username:
            resource = f"{parse_result.username}@{parse_result.resource}"
        else:
            resource = parse_result.resource

        return MSGraphyFS(get_default_client(writeable), resource, writeable)
