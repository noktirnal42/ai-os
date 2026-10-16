"""Host CLI regressions with isolated command doubles; no VM disk is touched.
Run: python3 -m unittest discover -s emulation/tests -v
"""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

VM = Path(__file__).resolve().parents[1] / 'vm.sh'

class CLIContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aios cli ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.disk = self.root / 'disk.qcow2'
        self.disk.touch()
        self.pid = self.root / 'qemu.pid'
        self.trace = self.root / 'trace'
        self.env = dict(os.environ, PATH=f'{self.bin}:' + os.environ['PATH'],
                        ARTIFACTS_DIR=str(self.root), DISK_FILE=str(self.disk),
                        QEMU_PIDFILE=str(self.pid), TRACE=str(self.trace))
        self.stub('ps', 'printf "qemu-system-aarch64 -drive file=%s\\n" "$DISK_FILE"')
        self.stub('ssh', 'printf "%s\\n" "$@" >> "$TRACE"; exit "${SSH_RESULT:-0}"')
        self.stub('rsync', '''printf '%s\\n' "$@" >> "$TRACE"
python3 - "$@" <<'CHECK'
import shlex, sys
args = sys.argv[1:]
transport = shlex.split(args[args.index('-e') + 1])
assert transport[1:3] == ['-F', '/dev/null'], transport
assert transport[3] == '-i', transport
assert transport[4].endswith('/artifacts/dev_ed25519'), transport
CHECK''')
        self.stub('qemu-img', '''printf '%s\n' "$*" >> "$TRACE"
if [ "$2" = -l ]; then printf 'Snapshot list:\nID TAG VM_SIZE DATE\n1 clean 0 date\n'; fi''')

    def stub(self, name, body):
        target = self.bin / name
        target.write_text('#!/bin/sh\n' + body + '\n')
        target.chmod(0o755)

    def run_vm(self, *args):
        return subprocess.run([str(VM), *args], env=self.env, capture_output=True, text=True)

    def running(self):
        self.pid.write_text(str(os.getpid()))

    def test_boot_uses_daemon_mode_and_tcg_cpu(self):
        seed = self.root / 'seed.iso'
        seed.touch()
        self.env.update(SEED_ISO=str(seed), VM_ACCEL='tcg', TEST_PID=str(os.getpid()))
        self.stub('lsof', 'exit 1')
        self.stub('qemu-system-aarch64', 'printf "%s\\n" "$@" >> "$TRACE"; printf "%s" "$TEST_PID" > "$QEMU_PIDFILE"')
        result = self.run_vm('boot')
        self.assertEqual(result.returncode, 0, result.stderr)
        trace = self.trace.read_text()
        self.assertIn('-daemonize\n', trace)
        self.assertIn('-cpu\nmax\n', trace)

    def test_exec_propagates_guest_failure(self):
        self.running()
        self.env['SSH_RESULT'] = '37'
        result = self.run_vm('exec', 'exit 37')
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertIn('exit 37', self.trace.read_text())

    def test_exec_requires_command(self):
        self.assertEqual(self.run_vm('exec').returncode, 2)

    def test_stopped_exec_is_missing_prerequisite(self):
        self.assertEqual(self.run_vm('exec', 'true').returncode, 4)

    def test_push_addresses_guest_and_preserves_extra_files(self):
        self.running()
        result = self.run_vm('push', '/tmp/source file', '/ai/tmp/')
        self.assertEqual(result.returncode, 0, result.stderr)
        trace = self.trace.read_text()
        self.assertIn('ai@127.0.0.1:/ai/tmp/', trace)
        self.assertIn('/tmp/source file', trace)
        self.assertNotIn('--delete', trace)

    def test_pull_addresses_guest_as_source(self):
        self.running()
        result = self.run_vm('pull', '/ai/tmp/file', '/tmp/local file')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.trace.read_text().endswith('ai@127.0.0.1:/ai/tmp/file\n/tmp/local file\n'))

    def test_snapshot_creates_only(self):
        result = self.run_vm('snapshot', 'new-checkpoint')
        self.assertEqual(result.returncode, 0, result.stderr)
        trace = self.trace.read_text()
        self.assertIn('snapshot -c new-checkpoint', trace)
        self.assertNotIn('snapshot -a', trace)

    def test_rollback_restores_only(self):
        result = self.run_vm('rollback', 'clean')
        self.assertEqual(result.returncode, 0, result.stderr)
        trace = self.trace.read_text()
        self.assertIn('snapshot -a clean', trace)
        self.assertNotIn('snapshot -c', trace)

    def test_unknown_rollback_does_not_create_snapshot(self):
        self.assertEqual(self.run_vm('rollback', 'absent').returncode, 4)
        self.assertNotIn('snapshot -a', self.trace.read_text())
        self.assertNotIn('snapshot -c', self.trace.read_text())

    def test_duplicate_snapshot_is_refused(self):
        self.assertEqual(self.run_vm('snapshot', 'clean').returncode, 5)
        self.assertNotIn('snapshot -c', self.trace.read_text())

    def test_running_snapshot_is_refused(self):
        self.running()
        self.assertEqual(self.run_vm('snapshot', 'new').returncode, 5)
        self.assertFalse(self.trace.exists())

    def test_missing_disk_has_documented_exit(self):
        self.disk.unlink()
        self.assertEqual(self.run_vm('boot').returncode, 4)

    def test_invalid_tag_is_usage_error(self):
        self.assertEqual(self.run_vm('snapshot', '-bad').returncode, 2)

class ImageVerification(unittest.TestCase):
    stub = CLIContract.stub
    run_vm = CLIContract.run_vm
    def setUp(self):
        CLIContract.setUp(self)
        self.image = self.root / 'base.qcow2'
        self.env.update(BASE_IMAGE_FILE=str(self.image), IMAGE_URL='https://fixture.invalid/base.qcow2',
                        MODEL_DIR=str(self.root / 'models'))
        self.stub('curl', """out=''
while [ "$#" -gt 0 ]; do
  if [ "$1" = -o ]; then shift; out="$1"; fi
  url="$1"; shift
done
case "$url" in
  *.sha512) [ "${NO_CHECKSUM:-0}" = 0 ] || exit 22; printf '%s' "$FIXTURE_SHA" > "$out" ;;
  *) printf 'fixture-image' > "$out" ;;
esac""")
        self.env['FIXTURE_SHA'] = hashlib.sha512(b'fixture-image').hexdigest()

    def test_download_requires_checksum(self):
        self.env['NO_CHECKSUM'] = '1'
        self.assertNotEqual(self.run_vm('fetch').returncode, 0)
        self.assertFalse(self.image.exists())

    def test_download_rejects_mismatch(self):
        self.env['FIXTURE_SHA'] = '0' * 128
        self.assertNotEqual(self.run_vm('fetch').returncode, 0)
        self.assertFalse(self.image.exists())

    def test_verified_download_and_cache_recheck(self):
        result = self.run_vm('fetch')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.image.read_bytes(), b'fixture-image')
        self.assertEqual(self.run_vm('fetch').returncode, 0)
        self.image.write_bytes(b'corrupted')
        self.assertEqual(self.run_vm('fetch').returncode, 4)

    def test_rejects_malformed_checksum(self):
        self.env['FIXTURE_SHA'] = 'not-a-checksum'
        self.assertEqual(self.run_vm('fetch').returncode, 4)
        self.assertFalse(self.image.exists())

if __name__ == '__main__':
    unittest.main()
