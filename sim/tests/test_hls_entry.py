from pathlib import Path
import unittest,subprocess,sys,json,tempfile,hashlib,shutil,os
D=Path(__file__).resolve().parents[2];TMP=Path(os.environ.get('COIN_TEST_TEMP',tempfile.gettempdir()))/'hls_entry_tests';TMP.mkdir(parents=True,exist_ok=True)
class EntryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=TMP);self.base=Path(self.temp.name).resolve();assert self.base.is_relative_to(TMP.resolve());self.addCleanup(self.temp.cleanup)
 def call(self,*args,root=D,cwd=None):
  return subprocess.run([sys.executable,'-B',str(root/'build/scripts/hls/build.py'),*map(str,args)],cwd=cwd or self.base,capture_output=True,text=True,encoding='utf-8')
 def ok(self,p):self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)
 def test_check_from_unrelated_directory_uses_current_sources(self):
  p=self.ok(self.call('check'));self.assertEqual(p['source_count'],12);self.assertEqual(p['project_root'],str(D.resolve()));self.assertFalse(p['tool_invoked'])
 def test_prepare_copies_real_sources_and_uses_local_relative_config(self):
  out=self.base/'output with spaces';p=self.ok(self.call('prepare','--output',out,'--vitis',self.base/'must_not_run.bat'))
  self.assertFalse(p['tool_invoked']);self.assertEqual(p['working_directory'],str(out))
  cfg=(out/'hls.cfg').read_text(encoding='utf-8');self.assertIn('syn.file=source/network.cpp',cfg);self.assertNotIn('D:/FPGA_learning',cfg)
  for name in ('network.cpp','conv_engine.h','program.h'):
   self.assertEqual((out/'source'/name).read_bytes(),(D/'src/hls/inference_core'/name).read_bytes())
  self.assertEqual(p['command'][1:4],['-c','--mode','hls']);self.assertFalse((out/'work').exists())
 def test_output_inside_package_is_rejected_before_writing(self):
  out=D/'forbidden_hls_output';p=self.call('prepare','--output',out);self.assertNotEqual(p.returncode,0);self.assertIn('outside',p.stderr);self.assertFalse(out.exists())
 def test_existing_output_is_not_overwritten(self):
  out=self.base/'existing';out.mkdir();(out/'keep.txt').write_text('keep');p=self.call('prepare','--output',out);self.assertNotEqual(p.returncode,0);self.assertEqual((out/'keep.txt').read_text(),'keep')
 def fixture(self):
  root=self.base/'relocated package';root.mkdir()
  for rel in ('build/scripts/hls','build/config/hls','src/hls/inference_core'):
   shutil.copytree(D/rel,root/rel)
  target=root/'build/provenance';target.mkdir(parents=True);shutil.copy2(D/'build/provenance/hls_source_identity.json',target/'hls_source_identity.json');return root
 def test_relocated_package_with_spaces_is_independent(self):
  root=self.fixture();p=self.ok(self.call('check',root=root));self.assertEqual(p['project_root'],str(root));self.assertEqual(p['source_count'],12)
 def test_missing_header_fails_before_creating_output(self):
  root=self.fixture();(root/'src/hls/inference_core/program.h').unlink();out=self.base/'newout';p=self.call('prepare','--output',out,root=root);self.assertNotEqual(p.returncode,0);self.assertIn('program.h',p.stderr);self.assertFalse(out.exists())
 def test_changed_source_is_rejected_by_original_identity(self):
  root=self.fixture();p=root/'src/hls/inference_core/network.cpp';p.write_bytes(p.read_bytes()+b'\n// changed fixture\n');result=self.call('check',root=root);self.assertNotEqual(result.returncode,0);self.assertIn('network.cpp',result.stderr)
 def test_profile_entry_help_has_no_old_common_dependency(self):
  p=subprocess.run([sys.executable,'-B',str(D/'build/scripts/hls/instrument_profile.py'),'--help'],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr);self.assertIn('--source-ip',p.stdout)
class ProfileGuardTests(unittest.TestCase):
 def test_profile_refuses_nested_output_before_copying(self):
  import importlib.util
  from unittest.mock import patch
  sys.path.insert(0,str(D/'build/scripts/hls'))
  spec=importlib.util.spec_from_file_location('active_profile',D/'build/scripts/hls/instrument_profile.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  with tempfile.TemporaryDirectory(dir=TMP) as temp:
   base=Path(temp).resolve();assert base.is_relative_to(TMP.resolve())
   with patch.object(module.shutil,'copytree',side_effect=AssertionError('copy should not start')):
    with self.assertRaisesRegex(ValueError,'overlap'):
     module.instrument(64,source_ip=base,dest_ip=base/'nested',source_dir=D/'src/hls/inference_core',identity_path=base.parent/'identity.json')
 def test_profile_does_not_overwrite_existing_identity(self):
  import importlib.util
  from unittest.mock import patch
  sys.path.insert(0,str(D/'build/scripts/hls'))
  spec=importlib.util.spec_from_file_location('active_profile2',D/'build/scripts/hls/instrument_profile.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  with tempfile.TemporaryDirectory(dir=TMP) as temp:
   base=Path(temp).resolve();assert base.is_relative_to(TMP.resolve());identity=base/'identity.json';identity.write_text('keep')
   with patch.object(module.shutil,'copytree',side_effect=AssertionError('copy should not start')):
    with self.assertRaisesRegex(ValueError,'already exists'):
     module.instrument(64,source_ip=base/'input',dest_ip=base/'output',source_dir=D/'src/hls/inference_core',identity_path=identity)
   self.assertEqual(identity.read_text(),'keep')
 def test_profile_identity_cannot_replace_generated_component(self):
  import importlib.util
  from unittest.mock import patch
  sys.path.insert(0,str(D/'build/scripts/hls'))
  spec=importlib.util.spec_from_file_location('active_profile3',D/'build/scripts/hls/instrument_profile.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  with tempfile.TemporaryDirectory(dir=TMP) as temp:
   base=Path(temp).resolve();assert base.is_relative_to(TMP.resolve());src=base/'input';(src/'hdl/verilog').mkdir(parents=True);(src/'component.xml').write_text('<component/>');(src/'hdl/verilog/yolox_int8.v').write_text('module yolox_int8(); endmodule')
   with patch.object(module.shutil,'copytree',side_effect=AssertionError('copy should not start')):
    with self.assertRaisesRegex(ValueError,'[Ii]dentity'):
     module.instrument(64,source_ip=src,dest_ip=base/'output',source_dir=D/'src/hls/inference_core',identity_path=base/'output/component.xml')
if __name__=='__main__':unittest.main()

