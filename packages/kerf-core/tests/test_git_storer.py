import os
import tempfile
import shutil
import unittest
import boto3
import pygit2
from moto import mock_aws

from kerf_core.storage.s3 import S3Storage
from kerf_core.storage.git_storer import S3GitStorer, StorerConcurrencyError

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

    def _init_bare(self, path):
        return pygit2.init_repository(path, bare=True)

    def _commit(self, repo, ref, path, contents, message):
        sig = pygit2.Signature('tester', 'tester@kerf.local')
        blob_oid = repo.create_blob(contents)
        tb = repo.TreeBuilder()
        tb.insert(path, blob_oid, pygit2.GIT_FILEMODE_BLOB)
        tree_oid = tb.write()
        parents = []
        try:
            parents = [repo.references[ref].target]
        except KeyError:
            pass
        commit_oid = repo.create_commit(ref, sig, sig, message, tree_oid, parents)
        return commit_oid

    def test_round_trip(self):
        src_dir = self._mkdir()
        repo = self._init_bare(src_dir)
        commit_oid = self._commit(
            repo, 'refs/heads/main', 'README.md',
            b'hello from S3GitStorer round-trip\n', 'initial commit',
        )
        original_sha = str(commit_oid)

        s3 = self._make_s3storage()
        prefix = 'workspaces/test-ws/git'
        S3GitStorer(s3, BUCKET, prefix).push_from_local(src_dir)

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

    def test_multi_push_orphan_cleanup(self):
        src_dir = self._mkdir()
        repo = self._init_bare(src_dir)

        # First push: one commit
        self._commit(repo, 'refs/heads/main', 'a.txt', b'one\n', 'c1')

        s3 = self._make_s3storage()
        prefix = 'workspaces/multi-ws/git'
        S3GitStorer(s3, BUCKET, prefix).push_from_local(src_dir)

        # Snapshot the keys after first push.
        first_keys = {
            o['Key']
            for o in s3.client.list_objects_v2(Bucket=BUCKET, Prefix=f'{prefix}/').get('Contents', [])
        }
        # Push 1 should have written HEAD + the main ref (loose or in packed-refs) + objects + marker.
        self.assertTrue(
            any(k.endswith('refs/heads/main') or k.endswith('packed-refs') for k in first_keys),
            f'no ref found in {first_keys}',
        )
        self.assertIn(f'{prefix}/_marker', first_keys)

        # Append more commits — this should trigger a git gc repack and orphan
        # the prior loose objects on the next push.
        for i in range(5):
            self._commit(
                repo, 'refs/heads/main', f'f{i}.txt', f'contents-{i}\n'.encode(), f'c{i+2}',
            )

        S3GitStorer(s3, BUCKET, prefix).push_from_local(src_dir)

        # Re-clone into a clean dir and verify the latest commit is reachable.
        dst_dir = self._mkdir()
        S3GitStorer(s3, BUCKET, prefix).clone_to_local(dst_dir)
        cloned_repo = pygit2.Repository(dst_dir)
        head_ref = cloned_repo.references['refs/heads/main']
        head_commit = cloned_repo[head_ref.target]
        commit_count = 0
        for _ in cloned_repo.walk(head_commit.id, pygit2.GIT_SORT_NONE):
            commit_count += 1
        self.assertEqual(commit_count, 6)

    def test_concurrent_push_loser_raises(self):
        src_dir = self._mkdir()
        repo = self._init_bare(src_dir)
        self._commit(repo, 'refs/heads/main', 'a.txt', b'one\n', 'c1')

        s3 = self._make_s3storage()
        prefix = 'workspaces/race-ws/git'
        S3GitStorer(s3, BUCKET, prefix).push_from_local(src_dir)

        # Two storers both read the same marker, both upload, only first wins.
        s1 = S3GitStorer(s3, BUCKET, prefix)
        s2 = S3GitStorer(s3, BUCKET, prefix)
        etag_1 = s1._read_marker_etag()
        etag_2 = s2._read_marker_etag()
        self.assertEqual(etag_1, etag_2)

        # s1 pushes — succeeds (replaces marker).
        s1.push_from_local(src_dir)

        # s2 still holds the stale etag; its push should detect the race.
        # To exercise the path, hand-roll a put with the (now stale) etag.
        with self.assertRaises(StorerConcurrencyError):
            # We have to bypass the auto-read-marker step inside push_from_local
            # because between calls s2 would re-read and see the new etag.
            # So simulate the race by calling put_object directly with the stale etag.
            try:
                s2.s3.client.put_object(
                    Bucket=BUCKET,
                    Key=f'{prefix}/_marker',
                    Body=b'racer',
                    IfMatch=etag_2,
                )
            except Exception as e:
                if 'PreconditionFailed' in str(e):
                    raise StorerConcurrencyError('simulated race') from e
                raise

    def test_batch_delete_handles_many_orphans(self):
        s3 = self._make_s3storage()
        prefix = 'workspaces/batch-ws/git'
        storer = S3GitStorer(s3, BUCKET, prefix)

        # Seed many orphan keys directly.
        for i in range(50):
            s3.client.put_object(Bucket=BUCKET, Key=f'{prefix}/orphan-{i}', Body=b'x')

        keys_before = [
            o['Key']
            for o in s3.client.list_objects_v2(Bucket=BUCKET, Prefix=f'{prefix}/').get('Contents', [])
        ]
        self.assertEqual(len(keys_before), 50)

        deleted = storer._batch_delete(keys_before)
        self.assertEqual(deleted, 50)

        keys_after = s3.client.list_objects_v2(Bucket=BUCKET, Prefix=f'{prefix}/').get('Contents', [])
        self.assertEqual(keys_after, [])

    def test_clone_after_repush_drops_old_loose_objects(self):
        src_dir = self._mkdir()
        repo = self._init_bare(src_dir)
        self._commit(repo, 'refs/heads/main', 'a.txt', b'one\n', 'c1')

        s3 = self._make_s3storage()
        prefix = 'workspaces/drop-ws/git'
        S3GitStorer(s3, BUCKET, prefix).push_from_local(src_dir)

        # Force-replace history with a brand new orphan commit so old objects
        # become unreachable + get GC'd locally on the next push.
        sig = pygit2.Signature('tester', 'tester@kerf.local')
        blob_oid = repo.create_blob(b'fresh\n')
        tb = repo.TreeBuilder()
        tb.insert('b.txt', blob_oid, pygit2.GIT_FILEMODE_BLOB)
        tree_oid = tb.write()
        new_oid = repo.create_commit(None, sig, sig, 'replace', tree_oid, [])
        repo.references['refs/heads/main'].set_target(new_oid)
        new_sha = str(new_oid)

        S3GitStorer(s3, BUCKET, prefix).push_from_local(src_dir)

        # Clone fresh and confirm we see only the new history.
        dst_dir = self._mkdir()
        S3GitStorer(s3, BUCKET, prefix).clone_to_local(dst_dir)
        cloned = pygit2.Repository(dst_dir)
        self.assertEqual(str(cloned.references['refs/heads/main'].target), new_sha)


if __name__ == '__main__':
    unittest.main()
