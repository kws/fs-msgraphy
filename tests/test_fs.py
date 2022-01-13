import os
import unittest
from uuid import uuid4

from fs.test import FSTestCases
from msgraphyfs.fs import MSGraphyFS, get_default_client

try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass

TEST_URL = os.environ['MSGRAPHYFS_TEST_URL']


class TestMSGraphyFS(FSTestCases, unittest.TestCase):

    def make_fs(self):
        self.root_fs = MSGraphyFS(get_default_client(writeable=True), TEST_URL)
        self.filename = f"unittest-{uuid4().hex}"
        print("Creating test directory", self.filename)
        test_fs = self.root_fs.makedir(self.filename)
        return test_fs

    def destroy_fs(self, fs):

        print("Removing test directory", self.filename)
        self.root_fs.removedir(self.filename, check_empty=False)
