import os
import tempfile
import shutil
import unittest
import boto3
import pygit2
from moto import mock_aws

from storage.s3 import S3Storage
from storage.git_storer import S3GitStorer

BUCKET = 'test-bucket'
REGION = 'us-east-1'

@mock_aws
class TestS3GitStorerRoundTrip(unittest.TestCase):
    def setUp(self):
        client = boto3.client('s3', region_name=REGION)
        client.create_bucket(Bucket=BUCKET)
        self.tmpdirs = []

    def tearDown(self):
        for d in self.tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    def _mkdir(self):
        d = tempfile.mkdtemp(prefix='kerf-test-')
        self.tmpdirs.append(d)
        return d

    def _make_s3storage(self):
        return S3Storage(bucket=BUCKET, region=REGION, access_key_id='test', secret_access_key='test')

    def test_round_trip(self):
        src_dir = self._mkdir()
        repo = pygit2.init_repository(src_dir, bare=True)
        sig = pygit2.Signature('tester', 'tester@kerf.local')

        blob_oid = repo.create_blob(b'hello from S3GitStorer round-trip\n')
        tb = repo.TreeBuilder()
        tb.insert('README.md', blob_oid, pygit2.GIT_FILEMODE_BLOB)
        tree_oid = tb.write()
        commit_oid = repo.create_commit('refs/heads/main', sig, sig, 'initial commit', tree_oid, [])

        original_sha = str(commit_oid)

        s3 = self._make_s3storage()
        prefix = 'workspaces/test-ws/git'
        storer_push = S3GitStorer(s3, BUCKET, prefix)
        storer_push.push_from_local(src_dir)

        dst_dir = self._mkdir()
        storer_pull = S3GitStorer(s3, BUCKET, prefix)
        storer_pull.clone_to_local(dst_dir)

        cloned_repo = storer_pull.open_repo(dst_dir)
        cloned_commit = cloned_repo[original_sha]
        self.assertEqual(str(cloned_commit.id), original_sha)
        cloned_tree = cloned_commit.tree
        readme_entry = cloned_tree['README.md']
        cloned_blob = cloned_repo[readme_entry.id]
        self.assertEqual(cloned_blob.data, b'hello from S3GitStorer round-trip\n')

    def test_clone_empty_prefix_initializes_bare_repo(self):
        s3 = self._make_s3storage()
        dst_dir = self._mkdir()
        storer = S3GitStorer(s3, BUCKET, 'workspaces/empty-ws/git')
        storer.clone_to_local(dst_dir)
        repo = storer.open_repo(dst_dir)
        self.assertTrue(repo.is_bare)

if __name__ == '__main__':
    unittest.main()